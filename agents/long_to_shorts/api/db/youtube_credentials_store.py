"""
agents/long_to_shorts/api/db/youtube_credentials_store.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Supabase-backed implementation of the YouTube credentials store.

Mirrors the in-memory store interface (get / upsert / delete). All access uses
the service-role client (bypasses RLS) — the refresh token is never exposed to
a user session.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from agents.long_to_shorts.api.supabase_client import get_worker_client

logger = logging.getLogger(__name__)

_TABLE = "youtube_credentials"


def _parse_expiry(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    return None


def _row_to_record(row: Dict[str, Any]) -> dict:
    return {
        "refresh_token": row.get("refresh_token"),
        "access_token": row.get("access_token"),
        "token_expiry": _parse_expiry(row.get("token_expiry")),
        "channel_id": row.get("channel_id"),
        "channel_title": row.get("channel_title"),
        "scopes": row.get("scopes"),
    }


class SupabaseYouTubeCredentialsStore:
    """Service-role-backed credentials store keyed by user_id."""

    def get(self, user_id: str) -> Optional[dict]:
        client = get_worker_client()
        result = (
            client.table(_TABLE)
            .select("*")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        data = result.data
        if not data:
            return None
        return _row_to_record(data[0])

    def upsert(self, user_id: str, **fields) -> dict:
        row: Dict[str, Any] = {"user_id": user_id}
        for key, value in fields.items():
            if value is None:
                continue
            if key == "token_expiry" and isinstance(value, datetime):
                value = value.astimezone(timezone.utc).isoformat()
            row[key] = value
        client = get_worker_client()
        result = (
            client.table(_TABLE)
            .upsert(row, on_conflict="user_id")
            .execute()
        )
        data = result.data
        return _row_to_record(data[0]) if data else _row_to_record(row)

    def delete(self, user_id: str) -> bool:
        client = get_worker_client()
        result = (
            client.table(_TABLE)
            .delete()
            .eq("user_id", user_id)
            .execute()
        )
        return bool(result.data)


supabase_youtube_credentials_store = SupabaseYouTubeCredentialsStore()

__all__ = ["SupabaseYouTubeCredentialsStore", "supabase_youtube_credentials_store"]
