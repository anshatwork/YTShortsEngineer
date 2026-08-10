"""
core/inference/gpu.py
~~~~~~~~~~~~~~~~~~~~~~
Single-GPU model residency management for local inference (Phase 2).

On one Ollama server the risk is VRAM: alternating between model tiers reloads
weights (thrash), and a model left resident after a burst holds VRAM other apps
want. This manager:

  * **warms** a model (preload) so the first real request isn't cold;
  * tracks the **currently-resident** model and counts **thrash** (tier switches)
    as a metric;
  * **evicts** the resident model after an idle timeout to free VRAM.

It is deliberately provider-agnostic: the actual "load"/"unload" calls are
injected as ``warm_fn``/``evict_fn`` callables, so ``core`` never imports the
Ollama client. The concrete binding lives in ``tools/llm/warm.py``.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Optional

from core.inference.metrics import get_metrics

logger = logging.getLogger(__name__)

WarmFn = Callable[[str], None]
EvictFn = Callable[[str], None]


class GpuModelManager:
    """Tracks the resident model, counts thrash, and evicts on idle."""

    def __init__(
        self,
        *,
        warm_fn: WarmFn,
        evict_fn: EvictFn,
        idle_timeout_s: float = 300.0,
        poll_interval_s: float = 30.0,
    ) -> None:
        self._warm_fn = warm_fn
        self._evict_fn = evict_fn
        self._idle_timeout = idle_timeout_s
        self._poll = poll_interval_s
        self._lock = threading.Lock()
        self._current: Optional[str] = None
        self._last_use = time.monotonic()
        self._thread: Optional[threading.Thread] = None
        self._stopping = threading.Event()
        self._metrics = get_metrics()

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stopping.clear()
        self._thread = threading.Thread(target=self._idle_loop, name="gpu-idle", daemon=True)
        self._thread.start()
        logger.info("GpuModelManager started — idle_timeout=%.0fs", self._idle_timeout)

    def stop(self) -> None:
        self._stopping.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    # -- warm / use --------------------------------------------------------

    def warm(self, model: str) -> None:
        """Preload *model* (best-effort). Marks it resident."""
        try:
            self._warm_fn(model)
            with self._lock:
                self._current = model
                self._last_use = time.monotonic()
            logger.info("warmed model %s", model)
        except Exception as exc:  # noqa: BLE001 — warming is best-effort
            logger.warning("model warm failed for %s: %s", model, exc)

    def note_use(self, model: str) -> None:
        """Record that *model* just served a request; count a tier switch."""
        with self._lock:
            if self._current is not None and self._current != model:
                self._metrics.incr("model_switches")
                logger.debug("model switch %s -> %s", self._current, model)
            self._current = model
            self._last_use = time.monotonic()

    # -- idle eviction -----------------------------------------------------

    def _idle_loop(self) -> None:
        while not self._stopping.wait(self._poll):
            with self._lock:
                current = self._current
                idle = time.monotonic() - self._last_use
            if current and idle >= self._idle_timeout:
                try:
                    self._evict_fn(current)
                    logger.info("evicted idle model %s after %.0fs", current, idle)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("model evict failed for %s: %s", current, exc)
                finally:
                    with self._lock:
                        # Only clear if nothing used it while we were evicting.
                        if self._current == current and (time.monotonic() - self._last_use) >= self._idle_timeout:
                            self._current = None

    # -- introspection -----------------------------------------------------

    def resident_model(self) -> Optional[str]:
        with self._lock:
            return self._current


__all__ = ["GpuModelManager", "WarmFn", "EvictFn"]
