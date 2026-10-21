"""Env-driven settings for the Learning OS.

Deliberately reads ``os.getenv`` directly (dual-read resilience, matching the parent repo's
``core/config`` philosophy): every service works even if a central settings object fails to build,
and every backend defaults to an in-memory implementation so the stack boots with zero infra.
"""

from __future__ import annotations

import os
from functools import lru_cache


def _get(name: str, default: str = "") -> str:
    return os.getenv(name, default)


def _flag(name: str, default: bool = False) -> bool:
    return _get(name, "1" if default else "0").strip().lower() in {"1", "true", "yes", "on"}


class Settings:
    """Snapshot of process environment. Cheap to build; call :func:`get_settings` for a cached one."""

    # Backends
    broker_backend: str = "memory"
    event_store_backend: str = "memory"
    content_store_backend: str = "memory"

    # NATS JetStream
    nats_url: str = "nats://localhost:4222"
    nats_stream: str = "LEARNING_OS"
    event_subject_prefix: str = "events"

    # Postgres
    pg_dsn: str = "postgresql://los:los@localhost:5432/learning_os"

    # Auth
    auth_disabled: bool = True
    supabase_jwt_secret: str = ""
    dev_owner_id: str = "00000000-0000-0000-0000-000000000001"

    # Service wiring
    ingestion_url: str = "http://localhost:8081"

    # Outbox
    outbox_poll_seconds: float = 1.0

    def __init__(self) -> None:
        self.broker_backend = _get("BROKER_BACKEND", "memory").lower()
        self.event_store_backend = _get("EVENT_STORE_BACKEND", "memory").lower()
        self.content_store_backend = _get("CONTENT_STORE_BACKEND", "memory").lower()

        self.nats_url = _get("NATS_URL", "nats://localhost:4222")
        self.nats_stream = _get("NATS_STREAM", "LEARNING_OS")
        self.event_subject_prefix = _get("EVENT_SUBJECT_PREFIX", "events")

        self.pg_dsn = _get("PG_DSN", "postgresql://los:los@localhost:5432/learning_os")

        self.auth_disabled = _flag("AUTH_DISABLED", True)
        self.supabase_jwt_secret = _get("SUPABASE_JWT_SECRET", "")
        self.dev_owner_id = _get("DEV_OWNER_ID", "00000000-0000-0000-0000-000000000001")

        self.ingestion_url = _get("INGESTION_URL", "http://localhost:8081")

        try:
            self.outbox_poll_seconds = float(_get("OUTBOX_POLL_SECONDS", "1.0"))
        except ValueError:
            self.outbox_poll_seconds = 1.0


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    """Test helper — drop the cached settings after mutating the environment."""
    get_settings.cache_clear()
