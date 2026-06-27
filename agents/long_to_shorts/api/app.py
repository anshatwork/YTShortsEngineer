"""
agents/long_to_shorts/api/app.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
FastAPI application factory for the Long-to-Shorts API.

Startup / shutdown
------------------
A ThreadPoolExecutor (max 2 workers) is created on startup and stored on
`app.state.executor` so any route handler can access it via the `Request`
object.  It is shut down gracefully when the server exits.

Usage
-----
    # Directly (via server.py)
    python agents/long_to_shorts/api/server.py

    # Or with uvicorn directly
    uvicorn agents.long_to_shorts.api.app:app --reload --port 8000
"""

from __future__ import annotations

import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path

# Load .env before anything reads env vars (e.g. AUTH_DISABLED, JOB_STORE).
# Needed because start.bat / uvicorn-direct invocations bypass server.py's
# dotenv loader. Project root = …/YTShortsEnginer.
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[3] / ".env")
except ImportError:
    pass

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

logger = logging.getLogger(__name__)
_access_logger = logging.getLogger("longtoshorts.access")

_WORKER_THREADS = 2  # concurrent pipeline jobs


# ---------------------------------------------------------------------------
# Lifespan — startup / shutdown
# ---------------------------------------------------------------------------

def _configure_project_loggers() -> None:
    """Install the central, context-aware logging configuration.

    See ``core.logging_config.configure_logging``: root console + rotating
    ``logs/app.log`` handlers with a ``[job:<id>|<node>]`` formatter, app
    loggers at LOG_LEVEL, and third-party request noise quieted to WARNING.
    Idempotent, so it coexists with uvicorn's own handlers.
    """
    from core.logging_config import configure_logging

    configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Wire the execution layer on startup; tear it down on exit.

    - Capture the running event loop on the event bus so worker threads can
      push real-time progress events to SSE subscribers (see core.execution).
    - Expose the task queue + event bus on app.state for route handlers.
    """
    import asyncio
    from core.execution import get_event_bus, get_task_queue

    _configure_project_loggers()
    logger.info("LongToShorts API starting — %d worker thread(s)", _WORKER_THREADS)

    event_bus = get_event_bus()
    if hasattr(event_bus, "bind_loop"):
        event_bus.bind_loop(asyncio.get_running_loop())
    app.state.event_bus = event_bus

    task_queue = get_task_queue()
    app.state.task_queue = task_queue
    # Backwards-compat: existing routes still reference app.state.executor.
    app.state.executor = ThreadPoolExecutor(max_workers=_WORKER_THREADS)

    # Self-warming music cache: refresh once on startup, then on a timer. The
    # actual work runs on the task queue (off the event loop); this coroutine
    # just paces it. See tools/assets/refresh.refresh_music_cache.
    music_refresh_task = asyncio.create_task(_music_cache_refresh_loop(task_queue))

    # Self-warming trending pool: same pattern — crawl on startup, then on a
    # timer, so /discover/suggestions always has a fresh pool to personalize.
    trending_crawler_task = asyncio.create_task(_trending_crawler_loop(task_queue))

    try:
        yield
    finally:
        logger.info("LongToShorts API shutting down — waiting for running jobs …")
        music_refresh_task.cancel()
        trending_crawler_task.cancel()
        for _task in (music_refresh_task, trending_crawler_task):
            try:
                await _task
            except asyncio.CancelledError:
                pass
        app.state.executor.shutdown(wait=True)
        task_queue.shutdown(wait=True)
        logger.info("Shutdown complete.")


async def _music_cache_refresh_loop(task_queue) -> None:
    """Enqueue a music-cache refresh on startup and every N hours thereafter."""
    import asyncio

    from tools.assets.refresh import refresh_music_cache

    try:
        hours = max(1, int(os.getenv("MUSIC_CACHE_REFRESH_HOURS", "24")))
    except ValueError:
        hours = 24

    while True:
        try:
            task_queue.enqueue(refresh_music_cache)
        except RuntimeError as exc:
            # Benign during teardown (e.g. test TestClients sharing a queue
            # singleton that was already shut down). Not worth a traceback.
            logger.debug("skipped music cache refresh enqueue: %s", exc)
        except Exception:  # noqa: BLE001 — never let the loop die on a transient error
            logger.exception("failed to enqueue music cache refresh")
        await asyncio.sleep(hours * 3600)


async def _trending_crawler_loop(task_queue) -> None:
    """Enqueue a trending-pool crawl on startup and every N hours thereafter."""
    import asyncio

    from agents.long_to_shorts.trending_crawler import crawl_trending_pool

    try:
        hours = max(1, int(os.getenv("TRENDING_CRAWLER_HOURS", "6")))
    except ValueError:
        hours = 6

    while True:
        try:
            task_queue.enqueue(crawl_trending_pool)
        except RuntimeError as exc:
            # Benign during teardown (shared queue singleton already shut down).
            logger.debug("skipped trending crawl enqueue: %s", exc)
        except Exception:  # noqa: BLE001 — never let the loop die on a transient error
            logger.exception("failed to enqueue trending crawl")
        await asyncio.sleep(hours * 3600)


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

# In production (ENVIRONMENT=production) the interactive API docs are disabled so
# the full schema/endpoint surface isn't exposed publicly. Set ENVIRONMENT to
# anything else (or leave unset) during development to get /docs + /redoc.
_IS_PRODUCTION = os.getenv("ENVIRONMENT", "development").lower() == "production"

app = FastAPI(
    title="LongToShorts API",
    description=(
        "HTTP interface for the Long-to-Shorts LangGraph clipping pipeline.\n\n"
        "Submit a YouTube URL or local video path and let the agent extract "
        "the best moments as 9:16 short clips."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None if _IS_PRODUCTION else "/docs",
    redoc_url=None if _IS_PRODUCTION else "/redoc",
    openapi_url=None if _IS_PRODUCTION else "/openapi.json",
)

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
# Origins come from FRONTEND_URL (comma-separated). In development it defaults to
# the local frontend so things work out of the box. In production FRONTEND_URL is
# REQUIRED — we refuse to fall back to "*" because that, combined with
# allow_credentials, would let any site make authenticated requests.
_raw_origins = os.getenv("FRONTEND_URL", "").strip()
if _raw_origins:
    _cors_origins = [o.strip().rstrip("/") for o in _raw_origins.split(",") if o.strip()]
elif _IS_PRODUCTION:
    raise RuntimeError(
        "FRONTEND_URL must be set in production (comma-separated allowed origins); "
        "refusing to start with a wildcard CORS policy."
    )
else:
    _cors_origins = ["http://localhost:3000", "http://127.0.0.1:3000"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    # Only the methods/headers the frontend actually uses — not a blanket "*".
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def _log_requests(request: Request, call_next):
    """Log every HTTP request as `METHOD PATH -> STATUS (Xms)`.

    Polling endpoints can be noisy; we keep the line short and let log-level
    filtering handle volume. INFO for 2xx/3xx, WARNING for 4xx, ERROR for 5xx.
    """
    t0 = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        elapsed_ms = (time.perf_counter() - t0) * 1000
        _access_logger.exception(
            "%s %s -> 500 (%.1fms)  unhandled exception",
            request.method, request.url.path, elapsed_ms,
        )
        raise
    elapsed_ms = (time.perf_counter() - t0) * 1000
    status_code = response.status_code
    log_fn = (
        _access_logger.error if status_code >= 500
        else _access_logger.warning if status_code >= 400
        else _access_logger.info
    )
    log_fn(
        "%s %s -> %d (%.1fms)",
        request.method, request.url.path, status_code, elapsed_ms,
    )
    return response

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

from agents.long_to_shorts.api.routes import router  # noqa: E402
from agents.long_to_shorts.api.edit_routes import router as edit_router  # noqa: E402
from agents.long_to_shorts.api.youtube_routes import router as youtube_router  # noqa: E402
from agents.long_to_shorts.api.discover_routes import router as discover_router  # noqa: E402
from agents.long_to_shorts.api.music_routes import router as music_router  # noqa: E402
from agents.long_to_shorts.api.events_routes import router as events_router  # noqa: E402
from agents.long_to_shorts.api.llm_routes import router as llm_router  # noqa: E402
from agents.long_to_shorts.api.billing_routes import router as billing_router  # noqa: E402

app.include_router(router, prefix="/api/v1", tags=["Long-to-Shorts"])
app.include_router(edit_router, prefix="/api/v1/edit", tags=["Edit"])
app.include_router(youtube_router, prefix="/api/v1/youtube", tags=["YouTube"])
app.include_router(discover_router, prefix="/api/v1/discover", tags=["Discover"])
app.include_router(music_router, prefix="/api/v1/music", tags=["Music"])
app.include_router(llm_router, prefix="/api/v1/llm", tags=["LLM (BYOK)"])
app.include_router(billing_router, prefix="/api/v1/billing", tags=["Billing"])
# SSE streams (real-time progress). Full paths live on the router, mounted at /api/v1.
app.include_router(events_router, prefix="/api/v1", tags=["Events"])

# ---------------------------------------------------------------------------
# Static files — serve produced artifacts (clips + edit outputs) to the frontend
# ---------------------------------------------------------------------------

_OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "output")).resolve()
_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(_OUTPUT_DIR)), name="static")

# Cached music library — browsable/previewable trending tracks (see music_routes).
# StaticFiles honours HTTP range requests, so <audio> seeking works. This is the
# single serving touch-point: a later S3/MinIO swap replaces MusicTrack.preview_url
# with a blob-store URL (BLOB_STORE_BACKEND), leaving the frontend contract intact.
_MUSIC_LIBRARY_DIR = (Path(os.getenv("ASSET_CACHE_DIR", "assets")) / "audio_cache").resolve()
_MUSIC_LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/library", StaticFiles(directory=str(_MUSIC_LIBRARY_DIR)), name="library")


# ---------------------------------------------------------------------------
# Health check (outside versioned prefix — for load-balancers / k8s probes)
# ---------------------------------------------------------------------------

@app.get("/health", tags=["Meta"])
async def health() -> dict:
    """Simple liveness probe."""
    return {"status": "ok", "service": "long-to-shorts-api"}


__all__ = ["app"]
