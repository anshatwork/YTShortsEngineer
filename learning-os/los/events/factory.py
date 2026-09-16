"""Factories that pick a broker / event-store backend from settings and cache a process singleton.

Same wrap-and-select idiom as the parent repo's ``_make_job_store()``: default to the in-memory
implementation; switch to the real one via ``BROKER_BACKEND`` / ``EVENT_STORE_BACKEND``.
"""

from __future__ import annotations

import logging

from los.config import Settings, get_settings
from los.events.broker import Broker, InProcessBroker
from los.events.event_store import EventStore, MemoryEventStore, PostgresEventStore

logger = logging.getLogger(__name__)

_broker: Broker | None = None
_store: EventStore | None = None


def make_broker(settings: Settings | None = None) -> Broker:
    s = settings or get_settings()
    if s.broker_backend == "nats":
        from los.events.nats_broker import NatsBroker

        logger.info("broker backend = nats (%s)", s.nats_url)
        return NatsBroker(s.nats_url, s.nats_stream, s.event_subject_prefix)
    logger.info("broker backend = memory")
    return InProcessBroker(s.event_subject_prefix)


def make_event_store(settings: Settings | None = None) -> EventStore:
    s = settings or get_settings()
    if s.event_store_backend == "postgres":
        logger.info("event store backend = postgres")
        return PostgresEventStore(s.pg_dsn)
    logger.info("event store backend = memory")
    return MemoryEventStore()


def get_broker() -> Broker:
    global _broker
    if _broker is None:
        _broker = make_broker()
    return _broker


def get_event_store() -> EventStore:
    global _store
    if _store is None:
        _store = make_event_store()
    return _store


def reset_singletons() -> None:
    """Test helper — drop cached broker/store so a new backend takes effect."""
    global _broker, _store
    _broker = None
    _store = None
