"""
agents/long_to_shorts/api/asset_store.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Asset registry store selector (memory | supabase), mirroring job_store.py.

    from agents.long_to_shorts.api.asset_store import asset_store
"""

from __future__ import annotations

import os
import threading
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from agents.long_to_shorts.api.models import AssetRecord


class _MemoryAssetStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._rows: Dict[str, dict] = {}

    def register(self, *, user_id: str, media_type: str, uri: str,
                 filename: Optional[str] = None, title: Optional[str] = None) -> AssetRecord:
        now = datetime.now(tz=timezone.utc)
        asset_id = str(uuid.uuid4())
        rec = {
            "asset_id": asset_id, "user_id": user_id, "media_type": media_type,
            "uri": uri, "filename": filename, "title": title,
            "content_hash": None, "status": "registered",
            "created_at": now, "updated_at": now,
        }
        with self._lock:
            self._rows[asset_id] = rec
        return AssetRecord(**rec)

    def set_status(self, asset_id: str, *, status: str, content_hash: Optional[str] = None) -> None:
        with self._lock:
            rec = self._rows.get(asset_id)
            if rec:
                rec["status"] = status
                rec["updated_at"] = datetime.now(tz=timezone.utc)
                if content_hash is not None:
                    rec["content_hash"] = content_hash

    def get(self, asset_id: str) -> Optional[AssetRecord]:
        with self._lock:
            rec = self._rows.get(asset_id)
            return AssetRecord(**rec) if rec else None

    def get_for_user(self, asset_id: str, user_id: str) -> Optional[AssetRecord]:
        with self._lock:
            rec = self._rows.get(asset_id)
            return AssetRecord(**rec) if rec and rec["user_id"] == user_id else None

    def list_for_user(self, user_id: str, *, limit: int = 100, offset: int = 0) -> List[AssetRecord]:
        with self._lock:
            rows = [r for r in self._rows.values() if r["user_id"] == user_id]
        rows.sort(key=lambda r: r["created_at"], reverse=True)
        return [AssetRecord(**r) for r in rows[offset:offset + limit]]


def _make_asset_store():
    backend = os.getenv("JOB_STORE", "memory").lower()
    if backend == "supabase":
        from agents.long_to_shorts.api.db.asset_store import supabase_asset_store
        return supabase_asset_store
    return _MemoryAssetStore()


asset_store = _make_asset_store()

__all__ = ["asset_store"]
