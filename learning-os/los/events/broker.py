"""Broker port + in-process adapter.

The broker moves events *between* services. It is deliberately minimal and transport-agnostic (the
parent repo's ``EventBus`` ABC anticipated exactly this swap): ``publish`` fans an event out on the
subject ``<prefix>.<event.type>``; ``subscribe`` registers a durable consumer for one event type.

``InProcessBroker`` runs everything in one event loop — the default for dev and tests, and it also
records every published event so the Phase-0 exit test can assert ``ContentSaved`` was emitted
without standing up NATS.
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Awaitable, Callable

from los.domain_shared.envelope import Event

logger = logging.getLogger(__name__)

Handler = Callable[[Event], Awaitable[None]]


class Broker(ABC):
    """Transport for domain events. Implementations: :class:`InProcessBroker`, ``NatsBroker``."""

    @abstractmethod
    async def start(self) -> None: ...

    @abstractmethod
    async def close(self) -> None: ...

    @abstractmethod
    async def publish(self, event: Event) -> None: ...

    @abstractmethod
    async def subscribe(self, event_type: str, durable: str, handler: Handler) -> None: ...


class InProcessBroker(Broker):
    """Single-process asyncio fan-out. Used in dev/tests; keeps a ``published`` log for assertions."""

    def __init__(self, subject_prefix: str = "events") -> None:
        self._prefix = subject_prefix
        self._subscribers: dict[str, list[Handler]] = {}
        self.published: list[Event] = []

    async def start(self) -> None:  # nothing to connect
        return None

    async def close(self) -> None:
        self._subscribers.clear()

    async def publish(self, event: Event) -> None:
        self.published.append(event)
        subject = event.subject(self._prefix)
        handlers = list(self._subscribers.get(subject, ()))
        logger.info("emitted %s (stream=%s seq=%s) → %d subscriber(s)",
                    event.type, event.stream, event.seq, len(handlers))
        for handler in handlers:
            try:
                await handler(event)
            except Exception:  # a bad subscriber must never break the publisher
                logger.exception("in-process subscriber failed for %s", event.type)

    async def subscribe(self, event_type: str, durable: str, handler: Handler) -> None:
        subject = f"{self._prefix}.{event_type}"
        self._subscribers.setdefault(subject, []).append(handler)
        logger.debug("subscribed durable=%s to %s", durable, subject)

    # test helper
    def published_of_type(self, event_type: str) -> list[Event]:
        return [e for e in self.published if e.type == event_type]
