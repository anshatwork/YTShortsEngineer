"""
core/cache/blobstore.py
~~~~~~~~~~~~~~~~~~~~~~~~~
Content-addressable blob storage for large artifacts (clips, audio).

The :class:`BlobStore` interface hides *where* bytes live so the rest of the
system never hard-codes the filesystem. :class:`LocalBlobStore` keeps blobs under
``CACHE_DIR/cas/<hash[:2]>/<hash><ext>`` — the sharded layout avoids one giant
directory. An ``S3BlobStore`` implementing the same four methods is the documented
production swap (selected via ``BLOB_STORE_BACKEND=s3``); CAS keys are global, so
cache hits work across machines the moment blobs live in object storage.

A blob *ref* is an opaque string the store understands (for local it is the
relative CAS path). Callers persist the ref in the cache index and pass it back to
``open`` / ``copy_to`` / ``exists`` / ``url``.
"""

from __future__ import annotations

import logging
import os
import shutil
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class BlobStore(ABC):
    @abstractmethod
    def ingest(self, src_path: str | Path, *, content_hash: str, ext: str) -> str:
        """Copy a local file into the store; return its opaque blob ref."""

    @abstractmethod
    def exists(self, ref: str) -> bool:
        ...

    @abstractmethod
    def copy_to(self, ref: str, dest_path: str | Path) -> None:
        """Materialize a stored blob to a local path (for serving / ffmpeg input)."""

    @abstractmethod
    def url(self, ref: str) -> Optional[str]:
        """Return a directly-servable URL for the blob, or None if not applicable."""


class LocalBlobStore(BlobStore):
    """Default store: sharded CAS directory on the local filesystem."""

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root).resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def _ref_path(self, ref: str) -> Path:
        return self._root / ref

    def ingest(self, src_path: str | Path, *, content_hash: str, ext: str) -> str:
        ext = ext if ext.startswith(".") or ext == "" else f".{ext}"
        ref = f"{content_hash[:2]}/{content_hash}{ext}"
        dest = self._ref_path(ref)
        if not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            # Copy (not move) so the caller's deterministic output path survives.
            tmp = dest.with_suffix(dest.suffix + ".part")
            shutil.copy2(src_path, tmp)
            os.replace(tmp, dest)  # atomic publish
        return ref

    def exists(self, ref: str) -> bool:
        return self._ref_path(ref).exists()

    def copy_to(self, ref: str, dest_path: str | Path) -> None:
        dest = Path(dest_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".part")
        shutil.copy2(self._ref_path(ref), tmp)
        os.replace(tmp, dest)

    def url(self, ref: str) -> Optional[str]:
        # Local CAS is not mounted under /static (the pipeline materializes blobs
        # into OUTPUT_DIR, which IS served). No direct URL.
        return None


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def make_blob_store(cache_dir: str | Path) -> BlobStore:
    backend = os.getenv("BLOB_STORE_BACKEND", "local").lower()
    if backend == "s3":
        try:
            from core.cache.blobstore_s3 import s3_store_from_env

            return s3_store_from_env()
        except Exception as exc:  # noqa: BLE001 — never let a misconfig break startup
            logger.error(
                "BLOB_STORE_BACKEND=s3 but S3 store could not be constructed (%s); "
                "falling back to LocalBlobStore.", exc,
            )
    return LocalBlobStore(Path(cache_dir) / "cas")


__all__ = ["BlobStore", "LocalBlobStore", "make_blob_store"]
