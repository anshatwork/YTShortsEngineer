"""
core/cache/index.py
~~~~~~~~~~~~~~~~~~~~
The cache index: metadata + small JSON values, keyed by content-addressable key.

Two backends behind one interface:

  * :class:`SqliteCacheIndex` — default for local dev / tests. A single WAL-mode
    SQLite file under ``CACHE_DIR``; survives restarts, zero external deps.
  * :class:`SupabaseCacheIndex` — production. Shared ``cache_entries`` table so the
    index is consistent across distributed workers (chosen design).

Selection: ``CACHE_INDEX_BACKEND`` env, defaulting to ``supabase`` when
``JOB_STORE=supabase`` (production runs already set that) else ``sqlite``.

JSON-valued operations (probe metadata, transcript segments, LLM responses) store
their value inline. Blob operations store a ``blob_ref`` pointing into the
:class:`~core.cache.blobstore.BlobStore`.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from core.cache.keys import canonical_json

logger = logging.getLogger(__name__)

_TABLE = "cache_entries"


@dataclass
class CacheEntry:
    key: str
    operation: str
    version: int
    kind: str                     # "json" | "blob"
    value: Optional[Any] = None   # json kind
    blob_ref: Optional[str] = None  # blob kind
    ext: Optional[str] = None
    size: int = 0
    hit_count: int = 0
    expires_at: Optional[float] = None  # epoch seconds; None = permanent


class CacheIndex(ABC):
    @abstractmethod
    def get(self, key: str) -> Optional[CacheEntry]:
        """Return a live (non-expired) entry and bump its hit stats, else None."""

    @abstractmethod
    def put(self, entry: CacheEntry) -> None:
        ...

    @abstractmethod
    def delete(self, key: str) -> None:
        ...


def _is_expired(expires_at: Optional[float]) -> bool:
    return expires_at is not None and time.time() >= expires_at


# ---------------------------------------------------------------------------
# SQLite backend (dev/test default)
# ---------------------------------------------------------------------------

class SqliteCacheIndex(CacheIndex):
    def __init__(self, db_path: str | Path) -> None:
        self._path = str(db_path)
        Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path, timeout=15, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {_TABLE} (
                    key         TEXT PRIMARY KEY,
                    operation   TEXT NOT NULL,
                    version     INTEGER NOT NULL,
                    kind        TEXT NOT NULL,
                    value       TEXT,
                    blob_ref    TEXT,
                    ext         TEXT,
                    size        INTEGER NOT NULL DEFAULT 0,
                    hit_count   INTEGER NOT NULL DEFAULT 0,
                    created_at  REAL NOT NULL,
                    accessed_at REAL NOT NULL,
                    expires_at  REAL
                );
                """
            )

    def get(self, key: str) -> Optional[CacheEntry]:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                f"SELECT * FROM {_TABLE} WHERE key = ?", (key,)
            ).fetchone()
            if row is None:
                return None
            if _is_expired(row["expires_at"]):
                conn.execute(f"DELETE FROM {_TABLE} WHERE key = ?", (key,))
                return None
            conn.execute(
                f"UPDATE {_TABLE} SET hit_count = hit_count + 1, accessed_at = ? WHERE key = ?",
                (time.time(), key),
            )
            value = row["value"]
            return CacheEntry(
                key=row["key"],
                operation=row["operation"],
                version=row["version"],
                kind=row["kind"],
                value=json.loads(value) if value is not None else None,
                blob_ref=row["blob_ref"],
                ext=row["ext"],
                size=row["size"],
                hit_count=row["hit_count"] + 1,
                expires_at=row["expires_at"],
            )

    def put(self, entry: CacheEntry) -> None:
        now = time.time()
        value_json = canonical_json(entry.value) if entry.value is not None else None
        with self._lock, self._connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {_TABLE}
                    (key, operation, version, kind, value, blob_ref, ext, size,
                     hit_count, created_at, accessed_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value=excluded.value, blob_ref=excluded.blob_ref,
                    ext=excluded.ext, size=excluded.size,
                    accessed_at=excluded.accessed_at, expires_at=excluded.expires_at;
                """,
                (
                    entry.key, entry.operation, entry.version, entry.kind,
                    value_json, entry.blob_ref, entry.ext, entry.size,
                    now, now, entry.expires_at,
                ),
            )

    def delete(self, key: str) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(f"DELETE FROM {_TABLE} WHERE key = ?", (key,))


# ---------------------------------------------------------------------------
# Supabase backend (production)
# ---------------------------------------------------------------------------

class SupabaseCacheIndex(CacheIndex):
    def __init__(self) -> None:
        from agents.long_to_shorts.api.supabase_client import get_worker_client
        self._client_factory = get_worker_client

    def _client(self):
        return self._client_factory()

    def get(self, key: str) -> Optional[CacheEntry]:
        res = (
            self._client().table(_TABLE)
            .select("*").eq("key", key).limit(1).execute()
        )
        rows = res.data or []
        if not rows:
            return None
        row = rows[0]
        expires_at = row.get("expires_at")
        # expires_at stored as ISO string when present
        exp_epoch = _iso_to_epoch(expires_at) if expires_at else None
        if _is_expired(exp_epoch):
            self.delete(key)
            return None
        # Best-effort hit accounting (non-fatal if it races).
        try:
            self._client().table(_TABLE).update(
                {"hit_count": (row.get("hit_count") or 0) + 1}
            ).eq("key", key).execute()
        except Exception:  # noqa: BLE001
            pass
        return CacheEntry(
            key=row["key"],
            operation=row["operation"],
            version=row["version"],
            kind=row["kind"],
            value=row.get("value"),
            blob_ref=row.get("blob_ref"),
            ext=row.get("ext"),
            size=row.get("size") or 0,
            hit_count=(row.get("hit_count") or 0) + 1,
            expires_at=exp_epoch,
        )

    def put(self, entry: CacheEntry) -> None:
        row: dict[str, Any] = {
            "key": entry.key,
            "operation": entry.operation,
            "version": entry.version,
            "kind": entry.kind,
            "value": entry.value,
            "blob_ref": entry.blob_ref,
            "ext": entry.ext,
            "size": entry.size,
        }
        if entry.expires_at is not None:
            row["expires_at"] = _epoch_to_iso(entry.expires_at)
        self._client().table(_TABLE).upsert(row).execute()

    def delete(self, key: str) -> None:
        self._client().table(_TABLE).delete().eq("key", key).execute()


def _iso_to_epoch(value: str) -> float:
    from datetime import datetime, timezone
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def _epoch_to_iso(epoch: float) -> str:
    from datetime import datetime, timezone
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def make_cache_index(cache_dir: str | Path) -> CacheIndex:
    default = "supabase" if os.getenv("JOB_STORE", "memory").lower() == "supabase" else "sqlite"
    backend = os.getenv("CACHE_INDEX_BACKEND", default).lower()
    if backend == "supabase":
        try:
            return SupabaseCacheIndex()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Supabase cache index unavailable (%s); falling back to sqlite.", exc)
    return SqliteCacheIndex(Path(cache_dir) / "index.sqlite")


__all__ = [
    "CacheEntry", "CacheIndex", "SqliteCacheIndex", "SupabaseCacheIndex",
    "make_cache_index",
]
