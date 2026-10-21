"""Append-only event store + transactional outbox.

This is the system of record for events (the parent repo has an EventBus but *no* durable event log
— this is the genuinely new primitive Phase 0 adds). ``append`` does two writes in one transaction:
the immutable ``domain_events`` row (with a per-stream monotonic ``seq``) and an ``outbox`` row. A
separate relay (``los.events.outbox``) publishes outbox rows to the broker and marks them published
— so a crash between DB commit and broker publish never loses or duplicates an event.

Two backends, selected by ``EVENT_STORE_BACKEND`` (memory | postgres), mirroring the parent repo's
memory/supabase store idiom so the whole chain is testable without infra.
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Any, Optional

from los.domain_shared.envelope import Event

logger = logging.getLogger(__name__)


class EventStore(ABC):
    @abstractmethod
    async def start(self) -> None: ...

    @abstractmethod
    async def close(self) -> None: ...

    @abstractmethod
    async def append(self, event: Event) -> Event:
        """Persist the event (assigning ``seq``) and enqueue it in the outbox, atomically."""

    @abstractmethod
    async def read_stream(self, stream: str) -> list[Event]: ...

    @abstractmethod
    async def fetch_unpublished(self, limit: int = 100) -> list[Event]:
        """Outbox: events appended but not yet published to the broker (oldest first)."""

    @abstractmethod
    async def mark_published(self, event_ids: list[str]) -> None: ...


class MemoryEventStore(EventStore):
    def __init__(self) -> None:
        self._events: list[Event] = []
        self._seq_by_stream: dict[str, int] = {}
        self._unpublished: dict[str, Event] = {}
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def append(self, event: Event) -> Event:
        async with self._lock:
            seq = self._seq_by_stream.get(event.stream, 0) + 1
            self._seq_by_stream[event.stream] = seq
            stored = event.model_copy(update={"seq": seq})
            self._events.append(stored)
            self._unpublished[stored.event_id] = stored
            return stored

    async def read_stream(self, stream: str) -> list[Event]:
        return [e for e in self._events if e.stream == stream]

    async def fetch_unpublished(self, limit: int = 100) -> list[Event]:
        return sorted(self._unpublished.values(), key=lambda e: (e.occurred_at, e.seq or 0))[:limit]

    async def mark_published(self, event_ids: list[str]) -> None:
        for eid in event_ids:
            self._unpublished.pop(eid, None)

    # test helpers
    @property
    def all_events(self) -> list[Event]:
        return list(self._events)


class PostgresEventStore(EventStore):
    """asyncpg-backed. ``append`` runs both inserts in one transaction; ``seq`` is computed under a
    ``SELECT ... FOR UPDATE``-free ``coalesce(max(seq),0)+1`` guarded by the ``unique(stream, seq)``
    constraint (a concurrent race fails the insert and is retried by the caller)."""

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._pool: Any = None

    async def start(self) -> None:
        import asyncpg  # lazy

        self._pool = await asyncpg.create_pool(self._dsn, min_size=1, max_size=10)

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    async def append(self, event: Event) -> Event:
        assert self._pool is not None, "PostgresEventStore.start() not called"
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                seq: int = await conn.fetchval(
                    "SELECT coalesce(max(seq), 0) + 1 FROM domain_events WHERE stream = $1",
                    event.stream,
                )
                stored = event.model_copy(update={"seq": seq})
                await conn.execute(
                    """
                    INSERT INTO domain_events
                      (event_id, stream, seq, type, version, owner_id, occurred_at,
                       correlation_id, causation_id, payload, metadata)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
                    """,
                    stored.event_id, stored.stream, stored.seq, stored.type, stored.version,
                    stored.owner_id, stored.occurred_at, stored.correlation_id,
                    stored.causation_id, _json(stored.payload), _json(stored.metadata),
                )
                await conn.execute(
                    "INSERT INTO outbox (event_id, published) VALUES ($1, false)",
                    stored.event_id,
                )
                return stored

    async def read_stream(self, stream: str) -> list[Event]:
        assert self._pool is not None
        rows = await self._pool.fetch(
            "SELECT * FROM domain_events WHERE stream = $1 ORDER BY seq", stream
        )
        return [_row_to_event(r) for r in rows]

    async def fetch_unpublished(self, limit: int = 100) -> list[Event]:
        assert self._pool is not None
        rows = await self._pool.fetch(
            """
            SELECT e.* FROM outbox o JOIN domain_events e ON e.event_id = o.event_id
            WHERE o.published = false
            ORDER BY e.occurred_at, e.seq
            LIMIT $1
            """,
            limit,
        )
        return [_row_to_event(r) for r in rows]

    async def mark_published(self, event_ids: list[str]) -> None:
        assert self._pool is not None
        if not event_ids:
            return
        await self._pool.execute(
            "UPDATE outbox SET published = true, published_at = now() WHERE event_id = ANY($1::uuid[])",
            event_ids,
        )


def _json(value: dict[str, Any]) -> str:
    import json

    return json.dumps(value, separators=(",", ":"))


def _row_to_event(row: Any) -> Event:
    import json

    def _load(v: Any) -> dict:
        if v is None:
            return {}
        return v if isinstance(v, dict) else json.loads(v)

    return Event(
        event_id=str(row["event_id"]),
        stream=row["stream"],
        seq=row["seq"],
        type=row["type"],
        version=row["version"],
        owner_id=str(row["owner_id"]),
        occurred_at=row["occurred_at"],
        correlation_id=str(row["correlation_id"]),
        causation_id=str(row["causation_id"]) if row["causation_id"] else None,
        payload=_load(row["payload"]),
        metadata=_load(row["metadata"]),
    )
