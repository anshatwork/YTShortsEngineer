"""The domain-event envelope — one shape for every event on the bus (CloudEvents-compatible).

Extends the parent repo's ``core/execution.eventbus.Event`` with the fields event sourcing needs:
``stream``/``seq`` (per-aggregate ordering), ``owner_id`` (tenant scope), ``version`` (schema
evolution + replay), and ``correlation_id``/``causation_id`` (cross-service tracing).

The envelope is transport-agnostic: the broker serialises ``to_json()`` onto a subject; the event
store persists the same shape into ``domain_events``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field

from los.domain_shared.ids import new_uuid


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Event(BaseModel):
    """An immutable domain event. ``seq`` is assigned by the event store on append (None until then)."""

    event_id: str = Field(default_factory=new_uuid)
    type: str
    version: int = 1
    stream: str                      # e.g. "content-<content_id>"
    seq: Optional[int] = None        # per-stream monotonic sequence, set by the event store
    owner_id: str
    occurred_at: datetime = Field(default_factory=_utcnow)
    correlation_id: str = Field(default_factory=new_uuid)
    causation_id: Optional[str] = None
    payload: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_json(self) -> str:
        return self.model_dump_json()

    @classmethod
    def from_json(cls, raw: str | bytes) -> "Event":
        return cls.model_validate_json(raw)

    def subject(self, prefix: str = "events") -> str:
        """Broker subject for this event: ``<prefix>.<type>`` (subjects == event types)."""
        return f"{prefix}.{self.type}"


def new_event(
    *,
    type: str,
    stream: str,
    owner_id: str,
    payload: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    version: int = 1,
    correlation_id: str | None = None,
    causation_id: str | None = None,
) -> Event:
    """Build a fresh event, defaulting ids/timestamps. Prefer this over constructing ``Event`` directly."""
    kwargs: dict[str, Any] = {
        "type": type,
        "stream": stream,
        "owner_id": owner_id,
        "payload": payload or {},
        "metadata": metadata or {},
        "version": version,
        "causation_id": causation_id,
    }
    if correlation_id is not None:
        kwargs["correlation_id"] = correlation_id
    return Event(**kwargs)
