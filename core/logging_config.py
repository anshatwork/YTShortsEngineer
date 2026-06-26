"""
core/logging_config.py
~~~~~~~~~~~~~~~~~~~~~~~~
Central logging configuration for the whole project (API + CLI).

Goals (see plan): make issues easy to analyse by
  * stamping **job + node context** on every log record, so the single
    ``logs/app.log`` and the console are greppable by job;
  * writing a **per-job log file** ``logs/jobs/<job_id>.log`` that captures the
    complete lifecycle of one run (nodes, LLM, ffmpeg, cache) with no
    cross-talk between concurrent jobs — a self-contained artifact you can read
    or paste when debugging;
  * **quieting third-party request noise** (httpx / supabase / anthropic …) to
    WARNING so the application signal stands out.

Usage
-----
    from core.logging_config import configure_logging, job_log_context

    configure_logging()                       # once, at process start

    with job_log_context(job_id):             # around a single job run
        ...                                   # all logs now carry [job:<id>|<node>]

The node context is set by ``agents/long_to_shorts/_logging_utils.node_stage``.
"""

from __future__ import annotations

import contextvars
import logging
import logging.handlers
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

# ---------------------------------------------------------------------------
# Context variables — thread/task-local correlation keys
# ---------------------------------------------------------------------------
# Jobs run in worker threads (see api/app.py). contextvars are isolated per
# thread, so a value set inside a job's thread is visible to every call made on
# that thread (node_stage, LLM, ffmpeg, cache, httpx) and to nobody else.
current_job_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "current_job_id", default="-"
)
current_node: contextvars.ContextVar[str] = contextvars.ContextVar(
    "current_node", default="-"
)

_LOG_DIR = Path(os.getenv("LOG_DIR", "logs"))
_JOB_LOG_DIR = _LOG_DIR / "jobs"

_LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] [job:%(job_id)s|%(node)s] %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# App loggers we always want at LOG_LEVEL (default INFO).
_APP_LOGGERS = ("agents", "tools", "core", "longtoshorts.access")

# Noisy third-party loggers quieted to WARNING by default. Each is overridable
# via LOG_LEVEL_<UPPERCASE-WITH-UNDERSCORES>, e.g. LOG_LEVEL_HTTPX=INFO.
_NOISY_LOGGERS = (
    "httpx",
    "httpcore",
    "anthropic",
    "supabase",
    "postgrest",
    "storage3",
    "urllib3",
    "hpack",
    "openai",
)

# Marker so we don't add duplicate handlers if configure_logging() runs twice.
_CONFIGURED_FLAG = "_ytshorts_logging_configured"


class ContextFilter(logging.Filter):
    """Stamp every record with the current job/node so the formatter can print
    them even for logs emitted outside our own code (httpx, ffmpeg-python …)."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.job_id = current_job_id.get()
        record.node = current_node.get()
        return True


def _level_from_env(var: str, default: int) -> int:
    raw = os.getenv(var)
    if not raw:
        return default
    return getattr(logging, raw.strip().upper(), default)


def configure_logging() -> None:
    """Configure root logging once. Idempotent — safe to call from both the API
    lifespan and CLI entrypoints."""
    root = logging.getLogger()
    if getattr(root, _CONFIGURED_FLAG, False):
        return

    _LOG_DIR.mkdir(parents=True, exist_ok=True)

    app_level = _level_from_env("LOG_LEVEL", logging.INFO)
    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)
    ctx_filter = ContextFilter()

    # Root captures everything; per-logger levels below do the gating. Setting
    # root to the lowest of the levels we care about keeps records flowing.
    root.setLevel(logging.DEBUG)

    # Console handler (stdout).
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    console.addFilter(ctx_filter)
    root.addHandler(console)

    # Rotating shared file — all jobs, bounded size.
    app_file = logging.handlers.RotatingFileHandler(
        _LOG_DIR / "app.log",
        maxBytes=int(os.getenv("LOG_MAX_BYTES", str(10 * 1024 * 1024))),
        backupCount=int(os.getenv("LOG_BACKUP_COUNT", "5")),
        encoding="utf-8",
    )
    app_file.setFormatter(formatter)
    app_file.addFilter(ctx_filter)
    root.addHandler(app_file)

    # App loggers at LOG_LEVEL, propagating to the root handlers above.
    for name in _APP_LOGGERS:
        lg = logging.getLogger(name)
        lg.setLevel(app_level)
        lg.propagate = True

    # Quiet third-party request noise (overridable per library).
    for name in _NOISY_LOGGERS:
        lvl = _level_from_env(f"LOG_LEVEL_{name.upper().replace('.', '_')}", logging.WARNING)
        logging.getLogger(name).setLevel(lvl)

    setattr(root, _CONFIGURED_FLAG, True)


@contextmanager
def job_log_context(job_id: str) -> Iterator[None]:
    """Bind *job_id* to the logging context and tee all of this job's records
    into ``logs/jobs/<job_id>.log`` for the duration of the block.

    The per-job handler lives on the root logger but filters on the
    contextvar-stamped ``job_id``, so when several jobs run concurrently each
    file contains only its own thread's records.
    """
    # Make sure base config exists even if a runner is invoked directly.
    configure_logging()

    token = current_job_id.set(job_id or "-")

    handler: logging.Handler | None = None
    if job_id:
        try:
            _JOB_LOG_DIR.mkdir(parents=True, exist_ok=True)
            handler = logging.FileHandler(
                _JOB_LOG_DIR / f"{job_id}.log", encoding="utf-8"
            )
            handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT))
            handler.addFilter(ContextFilter())
            handler.addFilter(_JobIdFilter(job_id))
            logging.getLogger().addHandler(handler)
        except Exception:  # never let logging setup break a job
            handler = None

    try:
        yield
    finally:
        if handler is not None:
            try:
                logging.getLogger().removeHandler(handler)
                handler.close()
            except Exception:
                pass
        current_job_id.reset(token)


class _JobIdFilter(logging.Filter):
    """Pass only records whose stamped ``job_id`` matches this job."""

    def __init__(self, job_id: str):
        super().__init__()
        self._job_id = job_id

    def filter(self, record: logging.LogRecord) -> bool:
        return getattr(record, "job_id", "-") == self._job_id


def job_log_scope(func):
    """Decorator for background runner entrypoints whose **first positional
    argument is the job id**. Runs the wrapped function inside
    ``job_log_context(<first arg>)`` so the whole run is correlated and teed to
    ``logs/jobs/<id>.log``.
    """
    import functools

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        job_id = str(args[0]) if args else "-"
        with job_log_context(job_id):
            return func(*args, **kwargs)

    return wrapper


__all__ = [
    "configure_logging",
    "job_log_context",
    "job_log_scope",
    "current_job_id",
    "current_node",
    "ContextFilter",
]
