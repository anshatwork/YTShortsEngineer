"""
agents/long_to_shorts/api/event_store.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Transparent decorator that turns every store ``update()`` into a real-time event.

This is the *single emission seam* for Part 1 (event-driven updates): rather than
scattering ``bus.emit(...)`` through the runners and nodes, we wrap the job / edit /
upload stores so that immediately after a successful DB write they publish the
updated record on the resource's channel (``job:<id>`` etc.). The SSE endpoints in
``events_routes.py`` subscribe to those channels.

Because the wrapper delegates everything else via ``__getattr__``, it is a drop-in
replacement for the underlying store — routes and runners are unchanged. Emission
is best-effort and never affects the store's return value or raises.
"""

from __future__ import annotations

import logging
from typing import Any

from core.execution.eventbus import Event, get_event_bus

logger = logging.getLogger(__name__)


class EventEmittingStore:
    """Wrap a store so ``update()`` publishes the updated record to the event bus."""

    def __init__(self, inner: Any, *, channel_prefix: str, id_attr: str) -> None:
        self._inner = inner
        self._channel_prefix = channel_prefix
        self._id_attr = id_attr

    def __getattr__(self, name: str) -> Any:
        # Delegate everything we don't override (create/get/list/...).
        return getattr(self._inner, name)

    def update(self, *args: Any, **kwargs: Any) -> Any:
        result = self._inner.update(*args, **kwargs)
        if result is not None:
            resource_id = args[0] if args else kwargs.get(self._id_attr)
            if resource_id is not None:
                self._emit(str(resource_id), result)
        return result

    def _emit(self, resource_id: str, record: Any) -> None:
        try:
            payload = record.model_dump(mode="json")
            updated_at = payload.get("updated_at")
            event = Event(
                type="update",
                channel=f"{self._channel_prefix}:{resource_id}",
                data=payload,
                id=str(updated_at) if updated_at else str(resource_id),
            )
            get_event_bus().emit(event.channel, event)
        except Exception as exc:  # noqa: BLE001 — never let eventing break a write
            logger.debug("event emit failed (%s:%s): %s", self._channel_prefix, resource_id, exc)


__all__ = ["EventEmittingStore"]
