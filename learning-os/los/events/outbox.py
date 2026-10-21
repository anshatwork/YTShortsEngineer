"""Outbox relay — drains the event store's outbox to the broker.

Runs as a background task inside a service (started on FastAPI startup). Each tick pulls a batch of
unpublished events, publishes them to the broker, and marks them published. Publish failures are
left unpublished for the next tick (at-least-once). This decouples the DB commit from the broker so
neither a broker outage nor a crash between the two loses an event.
"""

from __future__ import annotations

import asyncio
import logging

from los.events.broker import Broker
from los.events.event_store import EventStore

logger = logging.getLogger(__name__)


class OutboxRelay:
    def __init__(self, store: EventStore, broker: Broker, poll_seconds: float = 1.0,
                 batch: int = 100) -> None:
        self._store = store
        self._broker = broker
        self._poll = poll_seconds
        self._batch = batch
        self._task: asyncio.Task | None = None
        self._stopping = asyncio.Event()

    async def run_once(self) -> int:
        """Publish one batch of pending events. Returns the number published."""
        pending = await self._store.fetch_unpublished(self._batch)
        published: list[str] = []
        for event in pending:
            try:
                await self._broker.publish(event)
                published.append(event.event_id)
            except Exception:
                logger.exception("outbox publish failed for %s; will retry", event.event_id)
                break  # preserve ordering — stop at the first failure
        if published:
            await self._store.mark_published(published)
        return len(published)

    async def _run_forever(self) -> None:
        logger.info("outbox relay started (poll=%.2fs)", self._poll)
        while not self._stopping.is_set():
            try:
                n = await self.run_once()
            except Exception:
                logger.exception("outbox relay tick failed")
                n = 0
            if n == 0:
                try:
                    await asyncio.wait_for(self._stopping.wait(), timeout=self._poll)
                except asyncio.TimeoutError:
                    pass

    def start(self) -> None:
        if self._task is None:
            self._stopping.clear()
            self._task = asyncio.create_task(self._run_forever())

    async def stop(self) -> None:
        self._stopping.set()
        if self._task is not None:
            await self._task
            self._task = None
