"""
tools/video_editing/audio_mixer.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Pure utilities for mixing additional audio (background music, narration)
underneath an existing video's audio track.

Designed so both the per-clip /edit/add-music endpoint (Phase 2) and the
short-edit job (Phase 4) call the same primitive.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Optional, Sequence

logger = logging.getLogger(__name__)


def _resolve_ffmpeg_bin() -> str:
    """Find an ffmpeg executable.

    Prefers the imageio-ffmpeg bundled binary so the call works on systems
    without ffmpeg on PATH (same approach the rest of the project takes).
    """
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:  # noqa: BLE001 — fall back to PATH if imageio is missing
        return "ffmpeg"


def mix_background_music(
    video_path: str | Path,
    music_path: str | Path,
    output_path: str | Path,
    volume_db: float = -18.0,
) -> Path:
    """Mix *music_path* under the audio track of *video_path*.

    The music is looped (or trimmed) to match the video's duration. The video
    stream is copied without re-encoding; only audio is re-encoded.

    Args:
        video_path:  Source video with its own audio track.
        music_path:  Background music file (mp3/wav/ogg/etc).
        output_path: Where to write the mixed mp4. Parent dir is created.
        volume_db:   Music gain relative to source audio (negative = quieter).
                     -18 dB is a sensible default for narration-friendly mix.

    Returns:
        The output_path as a Path (so callers can chain).

    Raises:
        FileNotFoundError: if video_path or music_path does not exist.
        subprocess.CalledProcessError: if ffmpeg exits non-zero.
    """
    video = Path(video_path)
    music = Path(music_path)
    out = Path(output_path)

    if not video.exists():
        raise FileNotFoundError(f"video_path not found: {video}")
    if not music.exists():
        raise FileNotFoundError(f"music_path not found: {music}")
    out.parent.mkdir(parents=True, exist_ok=True)

    filter_complex = (
        # Apply music volume, then mix with source audio. duration=first cuts
        # the result to the source-video length, so the loop doesn't extend
        # the clip when the music is shorter than the video.
        f"[1:a]volume={volume_db}dB[m];"
        f"[0:a][m]amix=inputs=2:duration=first:dropout_transition=0[a]"
    )

    cmd: Sequence[str] = [
        _resolve_ffmpeg_bin(),
        "-y",
        "-i", str(video),
        "-stream_loop", "-1", "-i", str(music),
        "-filter_complex", filter_complex,
        "-map", "0:v",
        "-map", "[a]",
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        "-movflags", "+faststart",
        "-shortest",
        str(out),
    ]

    logger.info("Mixing music (vol=%.1f dB): %s + %s -> %s",
                volume_db, video.name, music.name, out.name)
    result = subprocess.run(
        cmd, check=False, capture_output=True, text=True,
    )
    if result.returncode != 0:
        logger.error("ffmpeg mix failed: %s", result.stderr[-400:])
        raise subprocess.CalledProcessError(
            result.returncode, cmd, output=result.stdout, stderr=result.stderr,
        )
    return out


def probe_duration(path: str | Path) -> float:
    """Return the duration in seconds of an audio or video file.

    Uses ffmpeg-python's probe (which the rest of the project already depends on).
    imageio-ffmpeg only bundles `ffmpeg.exe`, not `ffprobe`, so we can't naively
    derive ffprobe from the bundled binary.
    """
    import ffmpeg  # ffmpeg-python
    info = ffmpeg.probe(str(path))
    return float(info["format"]["duration"])


__all__ = ["mix_background_music", "probe_duration"]
