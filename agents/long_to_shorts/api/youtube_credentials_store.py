"""
agents/long_to_shorts/api/youtube_credentials_store.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Per-user store for connected-YouTube OAuth credentials.

Backend is selected by the JOB_STORE environment variable (matching the rest of
the API):

  JOB_STORE=supabase  →  SupabaseYouTubeCredentialsStore  (youtube_credentials table)
  JOB_STORE=memory    →  _MemoryYouTubeCredentialsStore   (default; dev only)

A "record" is a plain dict with the keys:
    refresh_token, access_token, token_expiry (datetime|None),
    channel_id, channel_title, scopes (str|None)

Writes always go through the service-role client (workers + route handlers),
so the refresh token never travels through a user JWT.
"""

from __future__ import annotations

import os
import threading
from copy import deepcopy
from typing import Dict, Optional


class _MemoryYouTubeCredentialsStore:
    """Thread-safe in-memory credentials store (development / testing)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._creds: Dict[str, dict] = {}

    def get(self, user_id: str) -> Optional[dict]:
        with self._lock:
            rec = self._creds.get(user_id)
            return deepcopy(rec) if rec else None

    def upsert(self, user_id: str, **fields) -> dict:
        with self._lock:
            rec = self._creds.get(user_id, {})
            # Only overwrite keys that were explicitly provided (non-None).
            for key, value in fields.items():
                if value is not None:
                    rec[key] = value
            self._creds[user_id] = rec
            return deepcopy(rec)

    def delete(self, user_id: str) -> bool:
        with self._lock:
            return self._creds.pop(user_id, None) is not None


def _make_credentials_store():
    backend = os.getenv("JOB_STORE", "memory").lower()
    if backend == "supabase":
        from agents.long_to_shorts.api.db.youtube_credentials_store import (
            supabase_youtube_credentials_store,
        )
        return supabase_youtube_credentials_store
    return _MemoryYouTubeCredentialsStore()


youtube_credentials_store = _make_credentials_store()

__all__ = ["youtube_credentials_store"]
