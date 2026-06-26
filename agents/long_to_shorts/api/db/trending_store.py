"""
agents/long_to_shorts/api/db/trending_store.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Supabase-backed implementation of the trending-suggestions store.

Two tables back this store (see supabase/migrations/006_trending.sql):

  trending_pool          — global pool of currently-trending videos the crawler
                           keeps warm (written via the service-role key).
  user_suggestion_state  — per-user `last_seen_at` marker driving the unread badge.

Implements the same surface as the in-memory _MemoryTrendingStore so routes and
the crawler require no changes beyond which store is imported.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

from agents.long_to_shorts.api.db.mappers import (
    row_to_trending_video,
    trending_video_to_insert,
)
from agents.long_to_shorts.api.models import DiscoverVideo
from agents.long_to_shorts.api.supabase_client import get_worker_client

logger = logging.getLogger(__name__)

_POOL_TABLE = "trending_pool"
_STATE_TABLE = "user_suggestion_state"


def _parse_dt(value) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    return datetime.now(tz=timezone.utc)


class SupabaseTrendingStore:
    """Supabase-backed trending store; all writes use the service-role key."""

    # ------------------------------------------------------------------
    # Pool (global)
    # ------------------------------------------------------------------

    def upsert_videos(self, videos: List[DiscoverVideo], topic: str) -> int:
        """Upsert pooled videos keyed on video_id (dedupe). Preserves the
        original discovered_at on conflict (we don't write that column)."""
        if not videos:
            return 0
        rows = [trending_video_to_insert(v, topic) for v in videos]
        client = get_worker_client()
        client.table(_POOL_TABLE).upsert(rows, on_conflict="video_id").execute()
        return len(rows)

    def list_pool(
        self, limit: int = 200
    ) -> List[Tuple[DiscoverVideo, datetime, str]]:
        """Most-recently-discovered videos first."""
        client = get_worker_client()
        result = (
            client.table(_POOL_TABLE)
            .select("*")
            .order("discovered_at", desc=True)
            .limit(limit)
            .execute()
        )
        out: List[Tuple[DiscoverVideo, datetime, str]] = []
        for row in result.data or []:
            try:
                video = row_to_trending_video(row)
            except Exception as exc:  # noqa: BLE001 — skip a malformed row, keep the rest
                logger.warning("skipping malformed trending_pool row: %s", exc)
                continue
            out.append((video, _parse_dt(row.get("discovered_at")), row.get("topic") or ""))
        return out

    def prune(self, keep_days: int = 14) -> None:
        cutoff = datetime.now(tz=timezone.utc) - timedelta(days=keep_days)
        client = get_worker_client()
        client.table(_POOL_TABLE).delete().lt(
            "discovered_at", cutoff.isoformat()
        ).execute()

    # ------------------------------------------------------------------
    # Per-user last-seen
    # ------------------------------------------------------------------

    def get_last_seen(self, user_id: str) -> Optional[datetime]:
        client = get_worker_client()
        result = (
            client.table(_STATE_TABLE)
            .select("last_seen_at")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        data = result.data
        if not data or not data[0].get("last_seen_at"):
            return None
        return _parse_dt(data[0]["last_seen_at"])

    def set_last_seen(self, user_id: str) -> None:
        now = datetime.now(tz=timezone.utc)
        client = get_worker_client()
        client.table(_STATE_TABLE).upsert(
            {"user_id": user_id, "last_seen_at": now.isoformat()},
            on_conflict="user_id",
        ).execute()


supabase_trending_store = SupabaseTrendingStore()

__all__ = ["SupabaseTrendingStore", "supabase_trending_store"]
