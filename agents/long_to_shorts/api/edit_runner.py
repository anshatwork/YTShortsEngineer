"""
agents/long_to_shorts/api/edit_runner.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Background workers for the per-clip /edit endpoints.

Phase 1 implements TTS (Chatterbox). Phase 2 (sounds) and Phase 3 (split-screen)
will add `run_music_edit_job` and `run_split_screen_edit_job` alongside.

All workers share the same lifecycle:
    queued → running → done | failed
and write artifacts under ``<OUTPUT_DIR>/edits/<edit_job_id>/``.
"""

from __future__ import annotations

import logging
import os
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from agents.long_to_shorts.api.models import (
        MusicEditRequest,
        SplitScreenEditRequest,
        TTSEditRequest,
    )

# Module-level imports so unit tests can patch these symbols on this module
# directly. Keep this list lean — heavy deps (whisper, langgraph) stay inside
# functions to keep import cost low for routes that don't need them.
from tools.video_editing.audio_mixer import mix_background_music  # noqa: E402
from tools.video_editing.layout_engine import compose_video  # noqa: E402
from tools.youtube.downloader import download_video  # noqa: E402

logger = logging.getLogger(__name__)

# Make sure the project root is importable when this module is loaded by a
# worker thread (mirrors runner.py).
_PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


# ---------------------------------------------------------------------------
# Filesystem layout helpers
# ---------------------------------------------------------------------------

def _output_root() -> Path:
    """Resolve OUTPUT_DIR (env-overridable) to an absolute path."""
    return Path(os.getenv("OUTPUT_DIR", "output")).resolve()


def _edits_dir(edit_job_id: str) -> Path:
    d = _output_root() / "edits" / edit_job_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _to_static_url(path: str | Path) -> str:
    """Convert an absolute path under OUTPUT_DIR into a /static/... URL.

    Returns the original string if the path is outside OUTPUT_DIR — callers
    should handle this case but it should not happen in normal use.
    """
    p = Path(path).resolve()
    root = _output_root()
    try:
        rel = p.relative_to(root)
    except ValueError:
        return str(p)
    return "/static/" + rel.as_posix()


# ---------------------------------------------------------------------------
# TTS — audio generation (Phase 1)
# ---------------------------------------------------------------------------

def _generate_tts(text: str, voice_preset: str, output_path: Path) -> Path:
    """Render TTS to *output_path* using the Chatterbox provider.

    ChatterboxTTS internally falls back to pyttsx3 when CHATTERBOX_API_KEY is
    unset, and to a dummy file when pyttsx3 is unavailable. We trust that
    chain rather than re-implementing it here.
    """
    from tools.tts.chatterbox import ChatterboxTTS

    provider = ChatterboxTTS()
    provider.generate_audio(
        text=text,
        output_path=str(output_path),
        preset=voice_preset,
    )
    return output_path


def _render_audio_intro_video(
    audio_path: Path,
    duration: float,
    output_path: Path,
    *,
    width: int = 1080,
    height: int = 1920,
    fps: int = 60,
    bg_color: str = "black",
) -> Path:
    """Render a 9:16 video where a solid background plays the TTS audio.

    Used by the attach-to-clip mode: the resulting clip is concatenated
    (with crossfade) before the source clip so the TTS plays as a spoken intro.
    """
    import ffmpeg  # local import — keeps module load fast

    video = (
        ffmpeg
        .input(
            f"color=c={bg_color}:s={width}x{height}:d={duration}",
            f="lavfi",
        )
        .video
        .filter("format", "yuv420p")
    )
    audio = ffmpeg.input(str(audio_path)).audio
    (
        ffmpeg
        .output(
            video,
            audio,
            str(output_path),
            vcodec="libx264",
            acodec="aac",
            r=fps,
            video_bitrate="8000k",
            audio_bitrate="192k",
            pix_fmt="yuv420p",
            movflags="+faststart",
            shortest=None,  # stop at the shorter stream (the audio)
        )
        .overwrite_output()
        .run(capture_stdout=True, capture_stderr=True)
    )
    return output_path


def _probe_duration(path: Path) -> float:
    import ffmpeg
    info = ffmpeg.probe(str(path))
    return float(info["format"]["duration"])


# ---------------------------------------------------------------------------
# Worker — TTS edit job
# ---------------------------------------------------------------------------

def run_tts_edit_job(edit_job_id: str, request: "TTSEditRequest") -> None:
    """Execute a single TTS edit job and persist the result.

    Two modes:
      * standalone (``attach_to_clip_id`` is None): produces ``narration.mp3``
      * attach (``attach_to_clip_id`` set): produces ``<clip_id>_with_intro.mp4``
        — the source clip with a TTS voice-over intro prepended via crossfade.
    """
    from agents.long_to_shorts.api.edit_job_store import edit_job_store

    edit_job_store.update(edit_job_id, status="running")
    logger.info("[edit:%s] tts started — preset=%s attach=%s",
                edit_job_id, request.voice_preset, request.attach_to_clip_id)

    try:
        out_dir = _edits_dir(edit_job_id)

        # ----- Standalone TTS -----
        if not request.attach_to_clip_id:
            audio_out = out_dir / "narration.mp3"
            _generate_tts(request.text, request.voice_preset, audio_out)
            edit_job_store.update(
                edit_job_id,
                status="done",
                output_path=str(audio_out),
                output_url=_to_static_url(audio_out),
            )
            logger.info("[edit:%s] tts done — %s", edit_job_id, audio_out)
            return

        # ----- Attach mode: TTS → intro video → crossfade to source clip -----
        from agents.long_to_shorts.api.job_store import job_store

        if not request.parent_job_id:
            raise ValueError(
                "attach_to_clip_id requires parent_job_id to resolve the source clip."
            )

        source_clip = job_store.get_clip(
            request.parent_job_id, request.attach_to_clip_id
        )
        if source_clip is None or not source_clip.path:
            raise ValueError(
                f"Clip '{request.attach_to_clip_id}' not found under job "
                f"'{request.parent_job_id}', or it has no file path."
            )
        source_path = Path(source_clip.path)
        if not source_path.exists():
            raise FileNotFoundError(f"Source clip file missing: {source_path}")

        # 1. Generate TTS audio
        tts_audio = out_dir / "intro_narration.mp3"
        _generate_tts(request.text, request.voice_preset, tts_audio)
        tts_duration = _probe_duration(tts_audio)
        logger.info(
            "[edit:%s] tts audio rendered (%.2fs) — building intro video",
            edit_job_id, tts_duration,
        )

        # 2. Build intro video matching the clip's vertical layout
        with tempfile.TemporaryDirectory() as tmpdir:
            intro_video = Path(tmpdir) / "intro.mp4"
            _render_audio_intro_video(tts_audio, tts_duration, intro_video)

            # 3. Crossfade intro into source clip — reuse the helper used by
            #    the long-to-shorts intro_attach node so the transition style
            #    matches the rest of the pipeline.
            from agents.long_to_shorts import intro_attach_node as ian

            final_out = out_dir / f"{request.attach_to_clip_id}_with_intro.mp4"
            # Temporarily override the intro duration in the helper module so
            # the xfade offset matches the TTS audio length.
            original_intro_dur = ian._INTRO_DURATION
            ian._INTRO_DURATION = tts_duration
            try:
                ian._concat_with_xfade(
                    str(intro_video), str(source_path), str(final_out)
                )
            finally:
                ian._INTRO_DURATION = original_intro_dur

        edit_job_store.update(
            edit_job_id,
            status="done",
            output_path=str(final_out),
            output_url=_to_static_url(final_out),
        )
        logger.info("[edit:%s] tts attach done — %s", edit_job_id, final_out)

    except Exception as exc:  # noqa: BLE001
        logger.exception("[edit:%s] tts failed: %s", edit_job_id, exc)
        edit_job_store.update(edit_job_id, status="failed", error=str(exc))


# ---------------------------------------------------------------------------
# Music — background music mixer (Phase 2)
# ---------------------------------------------------------------------------

def _resolve_uploaded_music(upload_id: str) -> Path:
    """Resolve an upload_id (returned by /edit/uploads) to a filesystem path."""
    base = Path(os.getenv("UPLOAD_DIR", "assets/uploads")).resolve()
    path = base / upload_id
    if not path.exists():
        raise FileNotFoundError(f"Unknown upload_id: {upload_id}")
    return path


def _fetch_music_for_theme(theme: str) -> Optional[Path]:
    """Fetch background music via the 4-tier AudioFetcher.

    Accepts the AudioTheme value (e.g. ``"professional"``). Returns the path
    of a usable audio file, or None when all tiers failed (the caller should
    surface this as a failure — we don't silently produce a music-less mix).
    """
    from core.audio_themes import AudioTheme
    from tools.audio_api import AudioFetcher

    theme_enum = AudioTheme.validate(theme)
    if theme_enum is None:
        raise ValueError(
            f"Unknown audio theme '{theme}'. Valid values: "
            f"{AudioTheme.list_values()}"
        )

    fetcher = AudioFetcher()
    path = fetcher.fetch_audio_for_theme(theme_enum)
    return Path(path) if path else None


def run_music_edit_job(edit_job_id: str, request: "MusicEditRequest") -> None:
    """Execute a music-mix edit job and persist the result.

    Resolves the source clip via job_store, fetches/uses a music file, mixes
    it under the clip's audio with `mix_background_music`, and writes the
    result to ``output/edits/{edit_job_id}/{clip_id}_with_music.mp4``.
    """
    from agents.long_to_shorts.api.edit_job_store import edit_job_store
    from agents.long_to_shorts.api.job_store import job_store

    edit_job_store.update(edit_job_id, status="running")
    logger.info(
        "[edit:%s] music started — theme=%s upload=%s path=%s vol=%.1f dB",
        edit_job_id, request.theme, request.music_upload_id,
        request.music_path, request.volume_db,
    )

    try:
        out_dir = _edits_dir(edit_job_id)

        # 1. Resolve source clip path
        source_clip = job_store.get_clip(request.parent_job_id, request.clip_id)
        if source_clip is None or not source_clip.path:
            raise ValueError(
                f"Clip '{request.clip_id}' not found under job "
                f"'{request.parent_job_id}', or it has no file path."
            )
        source_path = Path(source_clip.path)
        if not source_path.exists():
            raise FileNotFoundError(f"Source clip file missing: {source_path}")

        # 2. Resolve music source — precedence: explicit path > upload > theme
        if request.music_path:
            music_path: Optional[Path] = Path(request.music_path)
            if not music_path.exists():
                raise FileNotFoundError(f"music_path not found: {music_path}")
            logger.info("[edit:%s] using explicit music_path", edit_job_id)
        elif request.music_upload_id:
            music_path = _resolve_uploaded_music(request.music_upload_id)
            logger.info("[edit:%s] using uploaded music %s", edit_job_id, music_path)
        elif request.theme:
            music_path = _fetch_music_for_theme(request.theme)
            if music_path is None:
                raise RuntimeError(
                    f"All audio tiers failed for theme '{request.theme}'. "
                    "Set PIXABAY_API_KEY/FREESOUND_API_KEY or supply music_path."
                )
            logger.info("[edit:%s] fetched music for theme %s -> %s",
                        edit_job_id, request.theme, music_path)
        else:
            raise ValueError(
                "One of {theme, music_path, music_upload_id} must be provided."
            )

        # 3. Mix
        out_path = out_dir / f"{request.clip_id}_with_music.mp4"
        mix_background_music(
            source_path, music_path, out_path, volume_db=request.volume_db,
        )

        edit_job_store.update(
            edit_job_id,
            status="done",
            output_path=str(out_path),
            output_url=_to_static_url(out_path),
        )
        logger.info("[edit:%s] music mix done — %s", edit_job_id, out_path)

    except Exception as exc:  # noqa: BLE001
        logger.exception("[edit:%s] music failed: %s", edit_job_id, exc)
        edit_job_store.update(edit_job_id, status="failed", error=str(exc))


# ---------------------------------------------------------------------------
# Split-screen — vertical 9:16 composition (Phase 3)
# ---------------------------------------------------------------------------

def _resolve_uploaded_path(upload_id: str) -> Path:
    """Resolve any upload_id (audio or video) to its filesystem path."""
    base = Path(os.getenv("UPLOAD_DIR", "assets/uploads")).resolve()
    path = base / upload_id
    if not path.exists():
        raise FileNotFoundError(f"Unknown upload_id: {upload_id}")
    return path


def _resolve_background(
    request: "SplitScreenEditRequest", work_dir: Path,
) -> Path:
    """Resolve the request's background source to a local filesystem path.

    Downloads YouTube URLs into ``work_dir`` so the file is co-located with
    the run's artifacts and easy to clean up.
    """
    if request.background_default:
        env_path = os.getenv("BACKGROUND_VIDEO_PATH")
        if not env_path:
            raise ValueError(
                "background_default=true but BACKGROUND_VIDEO_PATH env var is not set."
            )
        p = Path(env_path)
        if not p.exists():
            raise FileNotFoundError(f"Default background not found: {p}")
        return p

    if request.background_path:
        p = Path(request.background_path)
        if not p.exists():
            raise FileNotFoundError(f"background_path not found: {p}")
        return p

    if request.background_upload_id:
        return _resolve_uploaded_path(request.background_upload_id)

    if request.background_url:
        out = work_dir / "background.mp4"
        download_video(request.background_url, str(out))
        return out

    raise ValueError(
        "One of {background_default, background_path, background_upload_id, "
        "background_url} must be provided."
    )


def run_split_screen_edit_job(
    edit_job_id: str, request: "SplitScreenEditRequest",
) -> None:
    """Compose a 9:16 split-screen with the source clip on top and the
    resolved background on the bottom. Reuses ``compose_video``.

    Output: ``output/edits/{edit_job_id}/{clip_id}_split.mp4``.
    """
    from agents.long_to_shorts.api.edit_job_store import edit_job_store
    from agents.long_to_shorts.api.job_store import job_store

    edit_job_store.update(edit_job_id, status="running")
    logger.info(
        "[edit:%s] split-screen started — audio_mode=%s default=%s url=%s upload=%s path=%s",
        edit_job_id, request.audio_mode, request.background_default,
        request.background_url, request.background_upload_id, request.background_path,
    )

    try:
        out_dir = _edits_dir(edit_job_id)

        # 1. Resolve source clip
        source_clip = job_store.get_clip(request.parent_job_id, request.clip_id)
        if source_clip is None or not source_clip.path:
            raise ValueError(
                f"Clip '{request.clip_id}' not found under job "
                f"'{request.parent_job_id}', or it has no file path."
            )
        source_path = Path(source_clip.path)
        if not source_path.exists():
            raise FileNotFoundError(f"Source clip file missing: {source_path}")

        # 2. Resolve background (may download via yt-dlp)
        background_path = _resolve_background(request, out_dir)
        logger.info("[edit:%s] background resolved to %s",
                    edit_job_id, background_path)

        # 3. Compose split-screen — source on top, background on bottom
        out_path = out_dir / f"{request.clip_id}_split.mp4"
        compose_video(
            fetched_video_path=str(source_path),
            background_video_path=str(background_path),
            voiceover_path=None,         # not used in this audio_mode
            caption_clips=[],            # no burned captions in this edit
            output_path=str(out_path),
            audio_mode=request.audio_mode,
            video_mode="split_screen",
        )

        edit_job_store.update(
            edit_job_id,
            status="done",
            output_path=str(out_path),
            output_url=_to_static_url(out_path),
        )
        logger.info("[edit:%s] split-screen done — %s", edit_job_id, out_path)

    except Exception as exc:  # noqa: BLE001
        logger.exception("[edit:%s] split-screen failed: %s", edit_job_id, exc)
        edit_job_store.update(edit_job_id, status="failed", error=str(exc))


__all__ = [
    "run_tts_edit_job",
    "run_music_edit_job",
    "run_split_screen_edit_job",
    "_to_static_url",
    "_edits_dir",
]
