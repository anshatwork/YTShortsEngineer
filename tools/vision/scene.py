"""
tools/vision/scene.py
~~~~~~~~~~~~~~~~~~~~~~~
Minimal shot/scene detection for the ingestion pipeline.

Uses ffmpeg's built-in scene-change score (``select='gt(scene,threshold)'`` +
``showinfo``) and parses cut timestamps from stderr — no extra dependency
(PySceneDetect can be swapped in behind the same function later). Always
**degrades, not fails**: if ffmpeg is unavailable or errors, or the video has no
detected cuts, it returns a single scene spanning the whole asset so downstream
keyframe/embedding stages still have something to work with.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
from typing import List, Tuple

logger = logging.getLogger(__name__)

_PTS_RE = re.compile(r"pts_time:([0-9.]+)")


def _ffmpeg_bin() -> str:
    return os.getenv("FFMPEG_BINARY") or shutil.which("ffmpeg") or "ffmpeg"


def probe_duration(video_path: str) -> float:
    """Return the media duration in seconds (0.0 if it can't be probed)."""
    try:
        import ffmpeg  # ffmpeg-python, already used in tools/thumbnail.py

        meta = ffmpeg.probe(video_path)
        return float(meta["format"]["duration"])
    except Exception as exc:  # noqa: BLE001
        logger.debug("probe_duration failed for %s: %s", video_path, exc)
        return 0.0


def detect_scenes(
    video_path: str,
    *,
    threshold: float = 0.4,
    min_scene_seconds: float = 2.0,
    max_scenes: int = 200,
) -> List[Tuple[float, float]]:
    """Return a list of ``(start_s, end_s)`` scene intervals for *video_path*.

    Never raises: on any failure returns ``[(0.0, duration)]``.
    """
    duration = probe_duration(video_path)
    fallback = [(0.0, duration or 0.0)]

    ffmpeg_bin = _ffmpeg_bin()
    if shutil.which(ffmpeg_bin) is None and not os.path.isabs(ffmpeg_bin):
        logger.info("ffmpeg not found; scene detection degraded to a single scene.")
        return fallback

    cmd = [
        ffmpeg_bin, "-hide_banner", "-i", video_path,
        "-filter:v", f"select='gt(scene,{threshold})',showinfo",
        "-f", "null", "-",
    ]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=int(os.getenv("KG_SCENE_TIMEOUT", "900")),
        )
    except Exception as exc:  # noqa: BLE001 — timeout / OSError
        logger.info("scene detection failed (%s); single-scene fallback.", exc)
        return fallback

    cuts = sorted({float(m) for m in _PTS_RE.findall(proc.stderr or "")})
    if not cuts:
        return fallback

    # Build intervals: [0, c0], [c0, c1], ..., [cn, duration]
    boundaries = [0.0] + cuts + ([duration] if duration else [cuts[-1] + min_scene_seconds])
    scenes: List[Tuple[float, float]] = []
    for start, end in zip(boundaries, boundaries[1:]):
        if end - start >= min_scene_seconds:
            scenes.append((round(start, 3), round(end, 3)))
        if len(scenes) >= max_scenes:
            break
    return scenes or fallback


__all__ = ["detect_scenes", "probe_duration"]
