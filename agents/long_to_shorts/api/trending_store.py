"""
agents/long_to_shorts/api/trending_store.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Trending-suggestions store — in-memory implementation + backend selector.

Mirrors the job_store pattern: the active backend depends on the JOB_STORE
environment variable (the same switch the job store uses, so both align):

  JOB_STORE=supabase  →  SupabaseTrendingStore  (requires SUPABASE_* env vars)
  JOB_STORE=memory    →  _MemoryTrendingStore   (default; no external deps)

Usage
-----
    from agents.long_to_shorts.api.trending_store import trending_store

    trending_store.upsert_videos(videos, topic="ai")
    pool = trending_store.list_pool()
    trending_store.set_last_seen(user_id)

The in-memory store self-warms via the startup crawl and resets on restart.
"""

from __future__ import annotations

import os
import threading
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from agents.long_to_shorts.api.models import DiscoverVideo


class _MemoryTrendingStore:
    """Thread-safe in-memory trending store (development / testing)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # video_id -> (video, discovered_at, topic)
        self._pool: Dict[str, Tuple[DiscoverVideo, datetime, str]] = {}
        self._last_seen: Dict[str, datetime] = {}

    def upsert_videos(self, videos: List[DiscoverVideo], topic: str) -> int:
        now = datetime.now(tz=timezone.utc)
        with self._lock:
            for v in videos:
                existing = self._pool.get(v.video_id)
                # Preserve the original discovered_at on update.
                discovered = existing[1] if existing else now
                self._pool[v.video_id] = (v, discovered, topic)
        return len(videos)

    def list_pool(
        self, limit: int = 200
    ) -> List[Tuple[DiscoverVideo, datetime, str]]:
        with self._lock:
            items = list(self._pool.values())
        items.sort(key=lambda t: t[1], reverse=True)
        return items[:limit]

    def prune(self, keep_days: int = 14) -> None:
        cutoff = datetime.now(tz=timezone.utc) - timedelta(days=keep_days)
        with self._lock:
            self._pool = {
                vid: tpl for vid, tpl in self._pool.items() if tpl[1] >= cutoff
            }

    def get_last_seen(self, user_id: str) -> Optional[datetime]:
        with self._lock:
            return self._last_seen.get(user_id)

    def set_last_seen(self, user_id: str) -> None:
        with self._lock:
            self._last_seen[user_id] = datetime.now(tz=timezone.utc)


def _make_trending_store():
    backend = os.getenv("JOB_STORE", "memory").lower()
    if backend == "supabase":
        from agents.long_to_shorts.api.db.trending_store import supabase_trending_store
        return supabase_trending_store
    return _MemoryTrendingStore()


trending_store = _make_trending_store()

__all__ = ["trending_store"]
