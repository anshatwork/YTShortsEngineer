"""
core/execution/eventbus.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Process-wide publish/subscribe bus for real-time pipeline progress.

Why this exists
---------------
The frontend used to poll ``GET /jobs/{id}`` every few seconds. Instead, the
backend now *pushes* progress: every store ``update()`` publishes a typed
:class:`Event`, and the SSE endpoints (``events_routes.py``) subscribe to the
relevant channel and stream those events to the browser.

Threading model
---------------
Pipeline work runs in worker threads (the ``ThreadPoolExecutor``), but
subscribers live on the FastAPI asyncio event loop. Publishers therefore call
:meth:`EventBus.emit`, which hands the event to the loop via
``loop.call_soon_threadsafe`` (safe from any thread, including the loop itself).
The loop is captured once at app startup with :meth:`InProcessEventBus.bind_loop`.

Backends
--------
:class:`InProcessEventBus` is the default — fan-out within one process. A
``RedisEventBus`` implementing the same interface can be added later for
cross-machine fan-out and selected via ``EVENT_BUS_BACKEND=redis``; nothing
that publishes or subscribes needs to change.
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, Optional, Set

logger = logging.getLogger(__name__)

# Per-subscriber queue cap. Progress events are tiny and subscribers (SSE
# streams) drain them immediately; the bound just protects against a wedged
# client leaking memory. On overflow we drop the oldest event.
_QUEUE_MAXSIZE = 256


@dataclass
class Event:
    """A single progress event delivered to subscribers of one channel."""

    type: str            # "update" | "snapshot" | "heartbeat" | "deleted"
    channel: str         # e.g. "job:<uuid>", "edit:<uuid>", "upload:<uuid>"
    data: Dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: f"{time.time():.6f}")


class EventBus(ABC):
    """Abstract pub/sub interface. Implementations must be thread-safe to emit."""

    @abstractmethod
    def emit(self, channel: str, event: Event) -> None:
        """Publish *event* to *channel*. Safe to call from any thread."""

    @abstractmethod
    def subscribe(self, channel: str) -> "Subscription":
        """Return an async-iterable subscription scoped to *channel*."""


class Subscription:
    """Async-iterable view over one channel; unregisters itself on close."""

    def __init__(self, bus: "InProcessEventBus", channel: str, queue: "asyncio.Queue[Event]"):
        self._bus = bus
        self._channel = channel
        self._queue = queue

    async def __aiter__(self) -> AsyncIterator[Event]:
        try:
            while True:
                yield await self._queue.get()
        finally:
            self.close()

    async def get(self, timeout: Optional[float] = None) -> Optional[Event]:
        """Await the next event. Returns None on *timeout* (used for heartbeats)."""
        if timeout is None:
            return await self._queue.get()
        try:
            return await asyncio.wait_for(self._queue.get(), timeout)
        except asyncio.TimeoutError:
            return None

    def close(self) -> None:
        self._bus._unregister(self._channel, self._queue)


class InProcessEventBus(EventBus):
    """Default bus: in-memory fan-out to per-subscriber asyncio queues."""

    def __init__(self) -> None:
        self._subs: Dict[str, Set["asyncio.Queue[Event]"]] = {}
        self._lock = threading.Lock()
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    # -- loop binding (called once from the app lifespan) -------------------

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    # -- publish ------------------------------------------------------------

    def emit(self, channel: str, event: Event) -> None:
        loop = self._loop
        if loop is None:
            # No event loop bound (CLI run / tests without server) → nobody can
            # be subscribed, so dropping the event is correct, not a loss.
            return
        try:
            loop.call_soon_threadsafe(self._deliver, channel, event)
        except RuntimeError:
            # Loop is closed (shutdown in progress) — safe to ignore.
            pass

    def _deliver(self, channel: str, event: Event) -> None:
        """Runs on the loop thread: push to every queue subscribed to *channel*."""
        with self._lock:
            queues = list(self._subs.get(channel, ()))
        for q in queues:
            if q.full():
                try:
                    q.get_nowait()  # drop oldest to make room
                except asyncio.QueueEmpty:
                    pass
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                logger.debug("eventbus: dropped event on full queue (%s)", channel)

    # -- subscribe ----------------------------------------------------------

    def subscribe(self, channel: str) -> Subscription:
        queue: "asyncio.Queue[Event]" = asyncio.Queue(maxsize=_QUEUE_MAXSIZE)
        with self._lock:
            self._subs.setdefault(channel, set()).add(queue)
        return Subscription(self, channel, queue)

    def _unregister(self, channel: str, queue: "asyncio.Queue[Event]") -> None:
        with self._lock:
            subs = self._subs.get(channel)
            if subs:
                subs.discard(queue)
                if not subs:
                    self._subs.pop(channel, None)

    # -- introspection (tests / metrics) ------------------------------------

    def subscriber_count(self, channel: str) -> int:
        with self._lock:
            return len(self._subs.get(channel, ()))


# ---------------------------------------------------------------------------
# Process-global singleton
# ---------------------------------------------------------------------------

_bus: Optional[EventBus] = None
_bus_lock = threading.Lock()


def _make_bus() -> EventBus:
    backend = os.getenv("EVENT_BUS_BACKEND", "memory").lower()
    if backend == "redis":
        # Placeholder for the production swap — same interface.
        # from core.execution.eventbus_redis import RedisEventBus
        # return RedisEventBus(os.environ["REDIS_URL"])
        logger.warning("EVENT_BUS_BACKEND=redis not yet implemented; using in-process bus.")
    return InProcessEventBus()


def get_event_bus() -> EventBus:
    """Return the process-wide event bus (created on first use)."""
    global _bus
    if _bus is None:
        with _bus_lock:
            if _bus is None:
                _bus = _make_bus()
    return _bus


__all__ = ["Event", "EventBus", "InProcessEventBus", "Subscription", "get_event_bus"]
