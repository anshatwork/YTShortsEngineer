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
    """Make our INFO logs visible under uvicorn.

    Uvicorn configures handlers on its own loggers (`uvicorn`, `uvicorn.access`,
    `uvicorn.error`) but leaves the root logger at WARNING with no handlers.
    Without this, every `[job:abc] analyze_video START` line we emit gets
    dropped on the floor. Setting these loggers to INFO and letting them
    propagate makes them flow into uvicorn's stderr handler.
    """
    for name in ("agents", "agents.long_to_shorts", "longtoshorts.access"):
        lg = logging.getLogger(name)
        lg.setLevel(logging.INFO)
        lg.propagate = True
    # Ensure the root logger has at least one handler so propagated records
    # actually print when uvicorn isn't the one running us (e.g. TestClient).
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create thread-pool on startup; shut it down on exit."""
    _configure_project_loggers()
    logger.info("LongToShorts API starting — %d worker thread(s)", _WORKER_THREADS)
    app.state.executor = ThreadPoolExecutor(max_workers=_WORKER_THREADS)
    try:
        yield
    finally:
        logger.info("LongToShorts API shutting down — waiting for running jobs …")
        app.state.executor.shutdown(wait=True)
        logger.info("Shutdown complete.")


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="LongToShorts API",
    description=(
        "HTTP interface for the Long-to-Shorts LangGraph clipping pipeline.\n\n"
        "Submit a YouTube URL or local video path and let the agent extract "
        "the best moments as 9:16 short clips."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
# Default: allow any origin so local dev works out of the box.
# Production: set FRONTEND_URL (e.g. https://your-app.vercel.app) to restrict
# the allowed origins list to only the frontend domain.
_raw_origins = os.getenv("FRONTEND_URL", "*")
_cors_origins = (
    [o.strip() for o in _raw_origins.split(",")]
    if _raw_origins != "*"
    else ["*"]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
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

app.include_router(router, prefix="/api/v1", tags=["Long-to-Shorts"])
app.include_router(edit_router, prefix="/api/v1/edit", tags=["Edit"])
app.include_router(youtube_router, prefix="/api/v1/youtube", tags=["YouTube"])

# ---------------------------------------------------------------------------
# Static files — serve produced artifacts (clips + edit outputs) to the frontend
# ---------------------------------------------------------------------------

_OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "output")).resolve()
_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(_OUTPUT_DIR)), name="static")


# ---------------------------------------------------------------------------
# Health check (outside versioned prefix — for load-balancers / k8s probes)
# ---------------------------------------------------------------------------

@app.get("/health", tags=["Meta"])
async def health() -> dict:
    """Simple liveness probe."""
    return {"status": "ok", "service": "long-to-shorts-api"}


__all__ = ["app"]
