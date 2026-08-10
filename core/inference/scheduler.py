"""
core/inference/scheduler.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
A generic, priority-aware background executor — the single choke point through
which every LLM call is scheduled so the local Ollama GPU is never overloaded.

Why here (and why generic)
--------------------------
On a single-GPU Ollama box, inference is the bottleneck: concurrent model loads
thrash VRAM and OOM. This scheduler serialises inference (``max_concurrency`` =
1 by default) and drains work **by priority** so human-facing (CRITICAL) work
always preempts background (indexing/KG) work waiting in the queue.

It is deliberately LLM-agnostic: it schedules opaque ``Callable[[], T]`` jobs.
That keeps ``core`` free of any upward import — the LLM-specific client that
builds prompts, checks the cache, and routes models lives in
``tools/llm/inference.py`` (``tools → core`` is the allowed direction) and simply
submits closures here.

Threading model
---------------
Callers ``submit(fn, priority=...)`` from worker threads (the pipeline task
queue) and block on the returned ``Future``. A small pool of scheduler worker
threads pulls the highest-priority ready job and runs it. A ``TASK_QUEUE`` style
swap (Celery/Ray) can replace this later behind the same ``submit`` interface.
"""

from __future__ import annotations

import itertools
import logging
import os
import queue
import threading
import time
from concurrent.futures import Future
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Callable, Dict, List, Optional, TypeVar

from core.inference.metrics import get_metrics

logger = logging.getLogger(__name__)

T = TypeVar("T")


class Priority(IntEnum):
    """Lower value = drained first (min-heap ordering)."""

    CRITICAL = 0      # human is blocked on this (approval-gate generation/eval)
    INTERACTIVE = 1   # user is waiting (metadata regen, single-clip re-score)
    BACKGROUND = 2    # nobody is waiting (indexing, KG ingestion, crawlers)


class InferenceCancelled(Exception):
    """Raised into a Future whose job was cancelled before/while scheduled."""


@dataclass(order=True)
class _QueuedJob:
    priority: int
    seq: int
    fn: Callable[[], Any] = field(compare=False)
    future: "Future" = field(compare=False)
    group: Optional[str] = field(compare=False, default=None)
    cancel: threading.Event = field(compare=False, default_factory=threading.Event)


class InferenceScheduler:
    """Priority-ordered, bounded-concurrency executor for inference jobs."""

    def __init__(self, *, max_concurrency: int = 1, queue_maxsize: int = 256) -> None:
        self._max_concurrency = max(1, max_concurrency)
        self._queue: "queue.PriorityQueue[_QueuedJob]" = queue.PriorityQueue(
            maxsize=max(0, queue_maxsize)
        )
        self._seq = itertools.count()
        self._workers: List[threading.Thread] = []
        self._started = False
        self._stopping = threading.Event()
        self._lock = threading.Lock()
        # group_id -> live jobs still queued/running, for bulk cancellation.
        self._groups: Dict[str, List[_QueuedJob]] = {}
        self._metrics = get_metrics()
        self._metrics.bind_queue_depth(self._queue.qsize)

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> None:
        with self._lock:
            if self._started:
                return
            self._stopping.clear()
            for i in range(self._max_concurrency):
                t = threading.Thread(
                    target=self._run_worker, name=f"inference-worker-{i}", daemon=True
                )
                t.start()
                self._workers.append(t)
            self._started = True
        logger.info(
            "InferenceScheduler started — %d worker(s), queue max=%s",
            self._max_concurrency, self._queue.maxsize or "∞",
        )

    def stop(self, *, wait: bool = True, timeout: float = 5.0) -> None:
        if not self._started:
            return
        self._stopping.set()
        # Wake each worker with a sentinel poison job.
        for _ in self._workers:
            poison = _QueuedJob(priority=Priority.CRITICAL, seq=next(self._seq),
                                fn=lambda: None, future=Future())
            try:
                self._queue.put_nowait(poison)
            except queue.Full:
                pass
        if wait:
            for t in self._workers:
                t.join(timeout=timeout)
        with self._lock:
            self._workers.clear()
            self._started = False
        logger.info("InferenceScheduler stopped.")

    # -- submit ------------------------------------------------------------

    def submit(
        self,
        fn: Callable[[], T],
        *,
        priority: Priority = Priority.INTERACTIVE,
        group: Optional[str] = None,
    ) -> "Future":
        """Schedule *fn* and return a Future for its result.

        Blocks if the queue is full (backpressure). Auto-starts the scheduler on
        first use so CLI/test callers don't have to.
        """
        if not self._started:
            self.start()
        job = _QueuedJob(
            priority=int(priority), seq=next(self._seq), fn=fn,
            future=Future(), group=group,
        )
        if group:
            with self._lock:
                self._groups.setdefault(group, []).append(job)
        self._metrics.record_submit()
        self._queue.put(job)  # blocks when full → backpressure
        return job.future

    def cancel_group(self, group: str) -> int:
        """Cancel every still-pending job in *group*. Returns how many were flagged."""
        with self._lock:
            jobs = list(self._groups.get(group, ()))
        n = 0
        for job in jobs:
            if not job.future.done():
                job.cancel.set()
                n += 1
        return n

    # -- worker ------------------------------------------------------------

    def _run_worker(self) -> None:
        while not self._stopping.is_set():
            try:
                job = self._queue.get(timeout=1.0)
            except queue.Empty:
                continue
            try:
                if self._stopping.is_set():
                    if not job.future.done():
                        job.future.set_exception(InferenceCancelled("scheduler stopping"))
                    continue
                if job.cancel.is_set():
                    self._metrics.record_cancelled()
                    if not job.future.done():
                        job.future.set_exception(InferenceCancelled("job cancelled"))
                    continue
                self._execute(job)
            finally:
                self._queue.task_done()
                self._untrack(job)

    def _execute(self, job: _QueuedJob) -> None:
        self._metrics.running_delta(1)
        t0 = time.perf_counter()
        try:
            result = job.fn()
        except Exception as exc:  # noqa: BLE001 — surface to the caller's Future
            self._metrics.running_delta(-1)
            if not job.future.done():
                job.future.set_exception(exc)
            return
        self._metrics.running_delta(-1)
        if not job.future.done():
            job.future.set_result(result)
        logger.debug("inference job done in %.2fs (prio=%d)", time.perf_counter() - t0, job.priority)

    def _untrack(self, job: _QueuedJob) -> None:
        if not job.group:
            return
        with self._lock:
            jobs = self._groups.get(job.group)
            if not jobs:
                return
            try:
                jobs.remove(job)
            except ValueError:
                pass
            if not jobs:
                self._groups.pop(job.group, None)

    # -- introspection -----------------------------------------------------

    def queue_depth(self) -> int:
        return self._queue.qsize()

    def metrics(self) -> Dict[str, Any]:
        return self._metrics.snapshot()


# ---------------------------------------------------------------------------
# Process-global singleton
# ---------------------------------------------------------------------------

_scheduler: Optional[InferenceScheduler] = None
_scheduler_lock = threading.Lock()


def get_scheduler() -> InferenceScheduler:
    """Return the process-wide inference scheduler (created on first use)."""
    global _scheduler
    if _scheduler is None:
        with _scheduler_lock:
            if _scheduler is None:
                _scheduler = InferenceScheduler(
                    max_concurrency=int(os.getenv("INFERENCE_MAX_CONCURRENCY", "1")),
                    queue_maxsize=int(os.getenv("INFERENCE_QUEUE_MAXSIZE", "256")),
                )
    return _scheduler


__all__ = [
    "InferenceScheduler",
    "Priority",
    "InferenceCancelled",
    "get_scheduler",
]
