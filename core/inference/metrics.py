"""
core/inference/metrics.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~
Process-wide observability for the inference scheduler.

The scheduler (queue depth, running, latency) and the LLM client (cache hits,
retries, per-model utilisation) both update one thread-safe :class:`Metrics`
singleton. ``GET /api/v1/publishing/metrics`` renders :meth:`Metrics.snapshot`.

Kept in ``core`` (stdlib only) so it never imports upward — the LLM-specific
client lives in ``tools/llm`` and updates this from there.
"""

from __future__ import annotations

import threading
from collections import Counter, deque
from typing import Any, Deque, Dict, Optional, Tuple


class Metrics:
    """Thread-safe counters + a rolling latency window for inference work."""

    # Keep the last N completed-call latencies for percentile estimation. Small
    # and bounded — this is a live gauge, not a time-series database.
    _LATENCY_WINDOW = 500

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: Counter = Counter()
        self._running = 0
        self._latencies: Deque[float] = deque(maxlen=self._LATENCY_WINDOW)
        self._per_model: Counter = Counter()
        # Injected by the scheduler at snapshot time (it owns the live queue).
        self._queue_depth_fn = None  # type: Optional[Any]

    # -- counters ----------------------------------------------------------

    def incr(self, name: str, n: int = 1) -> None:
        with self._lock:
            self._counters[name] += n

    def record_cache_hit(self) -> None:
        self.incr("cache_hits")

    def record_cache_miss(self) -> None:
        self.incr("cache_misses")

    def record_retry(self) -> None:
        self.incr("retries")

    def record_cancelled(self) -> None:
        self.incr("cancelled")

    # -- in-flight gauge ---------------------------------------------------

    def running_delta(self, delta: int) -> None:
        with self._lock:
            self._running = max(0, self._running + delta)

    # -- completions -------------------------------------------------------

    def record_completion(self, *, model: str, latency_s: float, ok: bool) -> None:
        with self._lock:
            self._counters["completed" if ok else "failed"] += 1
            if ok:
                self._latencies.append(latency_s)
                self._per_model[model] += 1

    def record_submit(self) -> None:
        self.incr("submitted")

    # -- queue depth binding (scheduler owns the queue) --------------------

    def bind_queue_depth(self, fn: Any) -> None:
        self._queue_depth_fn = fn

    # -- read model --------------------------------------------------------

    def _percentiles(self, values: Deque[float]) -> Tuple[float, float]:
        if not values:
            return 0.0, 0.0
        ordered = sorted(values)
        n = len(ordered)

        def _pct(p: float) -> float:
            idx = min(n - 1, int(round((p / 100.0) * (n - 1))))
            return round(ordered[idx], 3)

        return _pct(50), _pct(95)

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            counters = dict(self._counters)
            running = self._running
            p50, p95 = self._percentiles(self._latencies)
            per_model = dict(self._per_model)
            latency_n = len(self._latencies)
        hits = counters.get("cache_hits", 0)
        misses = counters.get("cache_misses", 0)
        total_cache = hits + misses
        hit_rate = round(hits / total_cache, 3) if total_cache else 0.0
        queue_depth = None
        if self._queue_depth_fn is not None:
            try:
                queue_depth = int(self._queue_depth_fn())
            except Exception:  # noqa: BLE001 — metrics must never raise
                queue_depth = None
        return {
            "submitted": counters.get("submitted", 0),
            "completed": counters.get("completed", 0),
            "failed": counters.get("failed", 0),
            "retries": counters.get("retries", 0),
            "cancelled": counters.get("cancelled", 0),
            "running": running,
            "queue_depth": queue_depth,
            "waiting": queue_depth,  # alias for the brief's "waiting jobs"
            "cache_hits": hits,
            "cache_misses": misses,
            "cache_hit_rate": hit_rate,
            "model_switches": counters.get("model_switches", 0),
            "latency_p50_s": p50,
            "latency_p95_s": p95,
            "latency_samples": latency_n,
            "model_utilization": per_model,
        }

    def reset(self) -> None:
        """Test helper — clear all counters/gauges."""
        with self._lock:
            self._counters.clear()
            self._per_model.clear()
            self._latencies.clear()
            self._running = 0


_metrics: Optional[Metrics] = None
_metrics_lock = threading.Lock()


def get_metrics() -> Metrics:
    global _metrics
    if _metrics is None:
        with _metrics_lock:
            if _metrics is None:
                _metrics = Metrics()
    return _metrics


__all__ = ["Metrics", "get_metrics"]
