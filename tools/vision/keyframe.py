"""
tools/vision/keyframe.py
~~~~~~~~~~~~~~~~~~~~~~~~~~
Extract one representative frame per scene, cached in the content-addressable
store so the (potentially expensive) seek+decode happens exactly once per
(asset, timestamp).

Reuses ``core/cache.materialize_blob`` exactly like ``clipping_logic`` caches clip
extraction: on a hit the JPEG is copied out of the CAS; on a miss ffmpeg produces
it and it is ingested. Returns the on-disk path (or None on failure —
degrade-not-fail).
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from core.cache import get_cache
from core.cache.keys import file_signature

logger = logging.getLogger(__name__)

_KEYFRAME_CACHE_VERSION = 1


def _ffmpeg_bin() -> str:
    return os.getenv("FFMPEG_BINARY") or shutil.which("ffmpeg") or "ffmpeg"


def _grab_frame(video_path: str, t_s: float, dest: Path) -> None:
    """ffmpeg: seek to *t_s* and write a single JPEG to *dest*. Raises on failure."""
    cmd = [
        _ffmpeg_bin(), "-hide_banner", "-loglevel", "error",
        "-ss", f"{max(0.0, t_s):.3f}", "-i", video_path,
        "-frames:v", "1", "-q:v", "3", "-y", str(dest),
    ]
    subprocess.run(cmd, check=True, capture_output=True, timeout=120)


def extract_keyframe(
    video_path: str,
    t_s: float,
    dest_path: str | Path,
) -> Optional[str]:
    """Materialize a keyframe JPEG at *t_s* into *dest_path* (CAS-backed).

    Returns the path as a string, or None if extraction failed.
    """
    dest = Path(dest_path)
    inputs = {"src": file_signature(video_path), "t": round(float(t_s), 3)}
    try:
        result = get_cache().materialize_blob(
            "kg_keyframe", _KEYFRAME_CACHE_VERSION, inputs, dest,
            lambda d: _grab_frame(video_path, t_s, d), ext=".jpg",
        )
        return str(result.path)
    except Exception as exc:  # noqa: BLE001 — degrade: skip this keyframe
        logger.info("keyframe extract failed (%s @ %.2fs): %s", video_path, t_s, exc)
        return None


__all__ = ["extract_keyframe"]
