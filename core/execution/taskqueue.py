"""
core/execution/taskqueue.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Abstraction over background-task submission.

Routes used to call ``request.app.state.executor.submit(run_job, ...)`` directly,
hard-coupling the API to an in-process ``ThreadPoolExecutor``. They now call
``get_task_queue().enqueue(run_job, job_id)``. The default
:class:`ThreadPoolTaskQueue` preserves today's behavior; a ``CeleryTaskQueue`` or
``TemporalTaskQueue`` implementing the same interface can be dropped in later to
move work onto distributed workers — without touching any route or runner.

For that swap to be lossless, enqueued callables must be **self-contained**: they
should take only ids/primitives and load everything else from the shared stores
(the full ``JobRequest`` is already persisted), never closures over in-memory
state. ``run_job(job_id)`` is refactored to honor this contract.
"""

from __future__ import annotations

import logging
import os
import threading
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


class TaskQueue(ABC):
    """Submit a callable to run in the background. Fire-and-forget."""

    @abstractmethod
    def enqueue(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        ...

    def shutdown(self, *, wait: bool = True) -> None:  # pragma: no cover - default no-op
        """Release resources on app shutdown. Overridden where relevant."""


class ThreadPoolTaskQueue(TaskQueue):
    """Default queue: wraps a ``ThreadPoolExecutor`` (single process)."""

    def __init__(self, max_workers: int = 2) -> None:
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._max_workers = max_workers
        logger.info("ThreadPoolTaskQueue ready — %d worker thread(s)", max_workers)

    def enqueue(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        future = self._executor.submit(func, *args, **kwargs)

        def _log_failure(fut) -> None:
            exc = fut.exception()
            if exc is not None:
                logger.exception("task %s raised: %s", getattr(func, "__name__", func), exc)

        future.add_done_callback(_log_failure)

    def shutdown(self, *, wait: bool = True) -> None:
        self._executor.shutdown(wait=wait)


# ---------------------------------------------------------------------------
# Process-global singleton
# ---------------------------------------------------------------------------

_queue: Optional[TaskQueue] = None
_queue_lock = threading.Lock()


def _make_queue() -> TaskQueue:
    backend = os.getenv("TASK_QUEUE_BACKEND", "threadpool").lower()
    workers = int(os.getenv("WORKER_THREADS", "2"))
    if backend in ("celery", "temporal", "rq"):
        logger.warning(
            "TASK_QUEUE_BACKEND=%s not yet implemented; using ThreadPoolTaskQueue.",
            backend,
        )
    return ThreadPoolTaskQueue(max_workers=workers)


def get_task_queue() -> TaskQueue:
    """Return the process-wide task queue (created on first use)."""
    global _queue
    if _queue is None:
        with _queue_lock:
            if _queue is None:
                _queue = _make_queue()
    return _queue


__all__ = ["TaskQueue", "ThreadPoolTaskQueue", "get_task_queue"]
