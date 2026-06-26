"""
tools/assets/store.py
~~~~~~~~~~~~~~~~~~~~~~
On-disk cache + lightweight metadata index for discovered assets.

Layout::

    <ASSET_CACHE_DIR>/audio_cache/<bucket>/        # MUSIC (reuses legacy dir)
    <ASSET_CACHE_DIR>/cache/<asset_type>/<bucket>/ # everything else
        index.json                                 # cache_key -> metadata
        <files...>                                 # downloaded asset bytes

For MUSIC the bucket is the AudioTheme value, so this transparently reuses the
existing ``assets/audio_cache/<theme>/`` files the project already ships and the
``/edit/add-music`` endpoint already relies on. Pre-existing files that predate
the index (no ``index.json`` entry) are still surfaced by :meth:`get` as
minimal "local" assets, so warm caches keep working after the refactor.

LRU-by-size eviction is lifted from the old ``AudioFetcher.cleanup_cache``.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import time
from pathlib import Path
from typing import List

from tools.assets.models import Asset, AssetType

logger = logging.getLogger(__name__)

_INDEX_NAME = "index.json"
_AUDIO_EXTS = (".mp3", ".wav", ".ogg", ".m4a")
# Buckets holding user-curated tracks — never LRU-evicted (like ``user_`` files).
_PROTECTED_BUCKETS = ("songs",)


class AssetStore:
    """File-backed asset cache with a per-bucket JSON metadata index."""

    def __init__(self) -> None:
        self.base_dir = Path(os.getenv("ASSET_CACHE_DIR", "assets"))
        self.max_cache_size_mb = int(os.getenv("AUDIO_CACHE_MAX_SIZE_MB", "500"))

    # -- paths -------------------------------------------------------------

    def _type_dir(self, asset_type: AssetType) -> Path:
        # MUSIC reuses the legacy assets/audio_cache location for continuity.
        if asset_type == AssetType.MUSIC:
            return self.base_dir / "audio_cache"
        return self.base_dir / "cache" / asset_type.value

    def _bucket_dir(self, asset_type: AssetType, bucket: str) -> Path:
        return self._type_dir(asset_type) / bucket

    def _index_path(self, asset_type: AssetType, bucket: str) -> Path:
        return self._bucket_dir(asset_type, bucket) / _INDEX_NAME

    # -- index io ----------------------------------------------------------

    def _read_index(self, asset_type: AssetType, bucket: str) -> dict:
        path = self._index_path(asset_type, bucket)
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001 — a corrupt index shouldn't be fatal
            logger.warning("could not read asset index %s: %s", path, exc)
            return {}

    def _write_index(self, asset_type: AssetType, bucket: str, index: dict) -> None:
        path = self._index_path(asset_type, bucket)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(index, indent=2), encoding="utf-8")

    # -- public api --------------------------------------------------------

    def get(self, asset_type: AssetType, bucket: str) -> List[Asset]:
        """Return cached assets for a bucket whose files still exist on disk.

        Includes both indexed assets and any un-indexed pre-existing files
        (legacy / pre-seeded caches), so the layer is backward compatible.
        """
        bucket_dir = self._bucket_dir(asset_type, bucket)
        if not bucket_dir.is_dir():
            return []

        index = self._read_index(asset_type, bucket)
        assets: List[Asset] = []
        indexed_paths = set()

        for entry in index.values():
            try:
                asset = Asset.from_index(entry)
            except Exception:  # noqa: BLE001 — skip malformed entries
                continue
            if asset.local_path and Path(asset.local_path).exists():
                assets.append(asset)
                indexed_paths.add(str(Path(asset.local_path).resolve()))

        # Surface un-indexed files (e.g. files shipped in the repo before the
        # index existed) as minimal local assets, using mtime as freshness.
        for f in sorted(bucket_dir.iterdir()):
            if f.name == _INDEX_NAME or f.suffix.lower() not in _AUDIO_EXTS:
                continue
            if str(f.resolve()) in indexed_paths:
                continue
            assets.append(
                Asset(
                    asset_type=asset_type,
                    source="local",
                    source_id=f.name,
                    title=f.stem,
                    url="",
                    local_path=str(f),
                    theme=bucket,
                    discovered_at=f.stat().st_mtime,
                )
            )
        return assets

    def is_fresh(
        self,
        asset_type: AssetType,
        bucket: str,
        ttl_seconds: float,
        min_pool: int,
    ) -> bool:
        """True when the bucket has >= min_pool assets and the newest is within TTL."""
        assets = self.get(asset_type, bucket)
        if len(assets) < min_pool:
            return False
        newest = max((a.discovered_at for a in assets), default=0.0)
        return (time.time() - newest) <= ttl_seconds

    def put(self, asset: Asset) -> Asset:
        """Move/record a downloaded asset into the cache and index it.

        ``asset.local_path`` must point at an existing (typically temp) file.
        The file is moved into the bucket dir; the index is updated keyed by
        ``cache_key`` (dedupe). Returns the asset with its final ``local_path``
        and ``discovered_at`` set.
        """
        if not asset.local_path or not Path(asset.local_path).exists():
            raise ValueError(f"put() requires an existing local_path; got {asset.local_path!r}")

        bucket = asset.theme or "default"
        bucket_dir = self._bucket_dir(asset.asset_type, bucket)
        bucket_dir.mkdir(parents=True, exist_ok=True)

        src = Path(asset.local_path)
        dest = bucket_dir / src.name
        if src.resolve() != dest.resolve():
            shutil.move(str(src), str(dest))
        asset.local_path = str(dest)
        if not asset.discovered_at:
            asset.discovered_at = time.time()

        index = self._read_index(asset.asset_type, bucket)
        index[asset.cache_key] = asset.to_index()
        self._write_index(asset.asset_type, bucket, index)
        logger.info("cached asset %s -> %s", asset.cache_key, dest)
        return asset

    def delete(self, asset_type: AssetType, bucket: str, cache_key: str) -> bool:
        """Remove a cached asset's file and its index entry. Returns True if removed.

        Used to let users delete tracks they added (see /api/v1/music/tracks DELETE).
        """
        index = self._read_index(asset_type, bucket)
        entry = index.get(cache_key)
        removed = False

        if entry:
            local_path = entry.get("local_path")
            if local_path:
                try:
                    Path(local_path).unlink(missing_ok=True)
                    removed = True
                except OSError as exc:  # noqa: BLE001 — index cleanup still proceeds
                    logger.warning("could not unlink %s: %s", local_path, exc)
            del index[cache_key]
            self._write_index(asset_type, bucket, index)
            removed = True

        return removed

    def cleanup(self, asset_type: AssetType) -> None:
        """Evict oldest files (by mtime) when the type's cache exceeds the size cap.

        User-curated tracks are never LRU-evicted: ``user_*`` uploads and anything in a
        protected bucket (e.g. ``songs``), so they can't be silently deleted to make
        room for fresh discoveries.
        """
        type_dir = self._type_dir(asset_type)
        if not type_dir.is_dir():
            return
        try:
            files = [
                (f, f.stat().st_size, f.stat().st_mtime)
                for f in type_dir.rglob("*")
                if f.is_file()
                and f.suffix.lower() in _AUDIO_EXTS
                and not f.name.startswith("user_")
                and f.parent.name not in _PROTECTED_BUCKETS
            ]
            total_mb = sum(sz for _, sz, _ in files) / (1024 * 1024)
            if total_mb <= self.max_cache_size_mb:
                return
            logger.info(
                "asset cache for %s (%.1fMB) exceeds %dMB cap, evicting...",
                asset_type.value, total_mb, self.max_cache_size_mb,
            )
            for f, sz, _ in sorted(files, key=lambda x: x[2]):  # oldest first
                if total_mb <= self.max_cache_size_mb:
                    break
                f.unlink(missing_ok=True)
                total_mb -= sz / (1024 * 1024)
                logger.info("evicted %s", f.name)
        except Exception as exc:  # noqa: BLE001
            logger.error("asset cache cleanup failed: %s", exc)


__all__ = ["AssetStore"]
