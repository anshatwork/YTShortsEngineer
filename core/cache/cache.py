"""
core/cache/cache.py
~~~~~~~~~~~~~~~~~~~~
The unified artifact cache — one entry point for both "avoid duplicate work"
(Part 2) and "skip if a valid output already exists" (Part 3 idempotency).

It composes a :class:`~core.cache.index.CacheIndex` (metadata + small JSON
values) with a :class:`~core.cache.blobstore.BlobStore` (large media). Callers
never touch either directly; they use:

  * :meth:`get_or_compute_json` — memoize an expensive pure-ish computation whose
    result is JSON (probe metadata, transcript segments, LLM responses).
  * :meth:`materialize_blob` — ensure a deterministic output path holds the
    artifact for a key, using the content-addressable store as a cross-job cache
    (e.g. ffmpeg clip extraction). On hit it copies CAS→dest; on miss it runs the
    producer (which writes to dest) then ingests dest into the CAS.

Everything is gated by ``CACHE_ENABLED`` (default on). When disabled the cache is
a transparent pass-through, so it is always safe to wrap a call site.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from core.cache.blobstore import BlobStore, make_blob_store
from core.cache.index import CacheEntry, CacheIndex, make_cache_index
from core.cache.keys import hash_file, make_key

logger = logging.getLogger(__name__)


def _cache_enabled() -> bool:
    return os.getenv("CACHE_ENABLED", "1").lower() in ("1", "true", "yes")


def _cache_dir() -> Path:
    return Path(os.getenv("CACHE_DIR", "cache")).resolve()


@dataclass
class BlobResult:
    """Outcome of :meth:`ArtifactCache.materialize_blob`."""

    path: Path
    key: str
    hit: bool


class ArtifactCache:
    def __init__(self, index: CacheIndex, blobs: BlobStore) -> None:
        self._index = index
        self._blobs = blobs

    # -- JSON-valued memoization -------------------------------------------

    def get_or_compute_json(
        self,
        operation: str,
        version: int,
        inputs: Any,
        compute: Callable[[], Any],
        *,
        ttl_seconds: Optional[int] = None,
    ) -> Any:
        """Return the cached JSON value for (operation, version, inputs) or compute,
        store, and return it. ``compute`` must return a JSON-serializable value."""
        if not _cache_enabled():
            return compute()

        key = make_key(operation, version, inputs)
        try:
            entry = self._index.get(key)
        except Exception as exc:  # noqa: BLE001 — cache must never break the pipeline
            logger.warning("cache get failed for %s (%s); computing.", operation, exc)
            entry = None

        if entry is not None and entry.kind == "json":
            logger.info("cache HIT  %s (key=%s…)", operation, key[:12])
            return entry.value

        logger.info("cache MISS %s (key=%s…)", operation, key[:12])
        value = compute()
        try:
            self._index.put(CacheEntry(
                key=key, operation=operation, version=version, kind="json",
                value=value,
                expires_at=(time.time() + ttl_seconds) if ttl_seconds else None,
            ))
        except Exception as exc:  # noqa: BLE001
            logger.warning("cache put failed for %s (%s); continuing.", operation, exc)
        return value

    # -- blob (large media) materialization --------------------------------

    def materialize_blob(
        self,
        operation: str,
        version: int,
        inputs: Any,
        dest_path: str | Path,
        producer: Callable[[Path], None],
        *,
        ext: str,
        ttl_seconds: Optional[int] = None,
    ) -> BlobResult:
        """Ensure *dest_path* holds the artifact for (operation, version, inputs).

        On a cache hit the stored blob is copied to *dest_path*. On a miss
        *producer(dest_path)* is invoked to create the file, which is then
        ingested into the content-addressable store for future reuse (including
        across jobs and — once on object storage — across machines).
        """
        dest = Path(dest_path)
        if not _cache_enabled():
            if not dest.exists():
                dest.parent.mkdir(parents=True, exist_ok=True)
                producer(dest)
            return BlobResult(path=dest, key="", hit=False)

        key = make_key(operation, version, inputs)
        try:
            entry = self._index.get(key)
        except Exception as exc:  # noqa: BLE001
            logger.warning("cache get failed for %s (%s); producing.", operation, exc)
            entry = None

        if (
            entry is not None and entry.kind == "blob" and entry.blob_ref
            and self._blobs.exists(entry.blob_ref)
        ):
            logger.info("cache HIT  %s (key=%s…) → %s", operation, key[:12], dest.name)
            if not dest.exists():
                self._blobs.copy_to(entry.blob_ref, dest)
            return BlobResult(path=dest, key=key, hit=True)

        logger.info("cache MISS %s (key=%s…) → producing %s", operation, key[:12], dest.name)
        dest.parent.mkdir(parents=True, exist_ok=True)
        producer(dest)
        try:
            content_hash = hash_file(dest)
            ref = self._blobs.ingest(dest, content_hash=content_hash, ext=ext)
            self._index.put(CacheEntry(
                key=key, operation=operation, version=version, kind="blob",
                blob_ref=ref, ext=ext, size=dest.stat().st_size,
                expires_at=(time.time() + ttl_seconds) if ttl_seconds else None,
            ))
        except Exception as exc:  # noqa: BLE001
            logger.warning("cache ingest failed for %s (%s); output still produced.", operation, exc)
        return BlobResult(path=dest, key=key, hit=False)


# ---------------------------------------------------------------------------
# Process-global singleton
# ---------------------------------------------------------------------------

_cache: Optional[ArtifactCache] = None
_cache_lock = threading.Lock()


def get_cache() -> ArtifactCache:
    """Return the process-wide artifact cache (created on first use)."""
    global _cache
    if _cache is None:
        with _cache_lock:
            if _cache is None:
                cache_dir = _cache_dir()
                _cache = ArtifactCache(
                    index=make_cache_index(cache_dir),
                    blobs=make_blob_store(cache_dir),
                )
    return _cache


__all__ = ["ArtifactCache", "BlobResult", "get_cache"]
