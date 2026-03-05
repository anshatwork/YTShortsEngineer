"""
agents/long_to_shorts/subtitles_node.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
SubtitlesNode – transcribe each extracted clip with Whisper and burn styled
subtitles into the video.

For every clip in generated_clips:
  1.  Runs OpenAI Whisper on the clip file to get segment-level timestamps.
  2.  Writes a temporary .srt file from the Whisper output.
  3.  Burns the subtitles into the video using ffmpeg's `subtitles` filter
      with a YouTube-standard style (bottom-centre, white text, dark outline).
  4.  Writes the result to  <OUTPUT_DIR>/clips/<clip_id>_sub.mp4  and
      updates clip["path"] to the new path.
  5.  Cleans up the temporary .srt file.

Clips without a valid path are skipped unchanged.

Configuration via environment variables (all optional):
    ADD_SUBTITLES              – "1"/"true" to enable (default: disabled)
    SUBTITLES_WHISPER_MODEL    – Whisper model size (default: "base")
    SUBTITLES_FONT_SIZE        – integer, subtitle font size (default: 40)
    SUBTITLES_FONT_COLOR       – ASS hex color for primary text (default: &HFFFFFF – white)
    SUBTITLES_OUTLINE_COLOR    – ASS hex color for outline (default: &H000000 – black)
    SUBTITLES_OUTLINE_WIDTH    – integer, outline width in pixels (default: 2)
    SUBTITLES_MAX_CHARS_LINE   – max chars per subtitle line (default: 42)
"""

import logging
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional

import ffmpeg  # ffmpeg-python

from agents.state import ClipObject, LongToShortsState

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants / config
# ---------------------------------------------------------------------------

_WHISPER_MODEL: str    = os.getenv("SUBTITLES_WHISPER_MODEL", "base")
_FONT_SIZE: int        = int(os.getenv("SUBTITLES_FONT_SIZE", "40"))
_FONT_COLOR: str       = os.getenv("SUBTITLES_FONT_COLOR", "&HFFFFFF")
_OUTLINE_COLOR: str    = os.getenv("SUBTITLES_OUTLINE_COLOR", "&H000000")
_OUTLINE_WIDTH: int    = int(os.getenv("SUBTITLES_OUTLINE_WIDTH", "2"))
_MAX_CHARS_LINE: int   = int(os.getenv("SUBTITLES_MAX_CHARS_LINE", "42"))
_MAX_WORKERS: int      = 2   # Whisper is CPU-heavy; limit parallelism

_FPS: int             = 60
_VIDEO_CODEC: str     = "libx264"
_AUDIO_CODEC: str     = "aac"
_VIDEO_BITRATE: str   = "8000k"
_AUDIO_BITRATE: str   = "192k"


# ---------------------------------------------------------------------------
# SRT helpers
# ---------------------------------------------------------------------------

def _seconds_to_srt_ts(seconds: float) -> str:
    """Convert a float seconds value to SRT timestamp format HH:MM:SS,mmm."""
    seconds = max(0.0, seconds)
    hours   = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs    = int(seconds % 60)
    millis  = int(round((seconds - int(seconds)) * 1000))
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _wrap_subtitle_line(text: str, max_chars: int = _MAX_CHARS_LINE) -> str:
    """
    Insert a single newline into *text* if it exceeds *max_chars*, splitting
    at the nearest word boundary near the middle.  Returns the text unchanged
    if it is already short enough.
    """
    text = text.strip()
    if len(text) <= max_chars:
        return text

    mid = len(text) // 2
    # Search for a space near the middle to split on
    left  = text.rfind(" ", 0, mid)
    right = text.find(" ", mid)

    if left == -1 and right == -1:
        return text  # no spaces — can't wrap

    if left == -1:
        split_at = right
    elif right == -1:
        split_at = left
    else:
        split_at = left if (mid - left) <= (right - mid) else right

    return text[:split_at] + "\n" + text[split_at + 1:]


def _build_srt(segments: List[Dict]) -> str:
    """
    Convert a list of Whisper segments (each with 'start', 'end', 'text')
    into a valid SRT string.
    """
    lines: List[str] = []
    for i, seg in enumerate(segments, start=1):
        start_ts = _seconds_to_srt_ts(float(seg["start"]))
        end_ts   = _seconds_to_srt_ts(float(seg["end"]))
        text     = _wrap_subtitle_line(seg["text"].strip())
        lines.append(f"{i}\n{start_ts} --> {end_ts}\n{text}\n")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Per-clip worker
# ---------------------------------------------------------------------------

def _burn_subtitles(clip: ClipObject, clips_dir: Path) -> ClipObject:
    """
    Transcribe *clip* with Whisper and burn subtitles into the output.
    Returns updated ClipObject with path pointing to *_sub.mp4.
    On failure, returns original clip unchanged.
    """
    clip_id   = clip["clip_id"]
    main_path = clip.get("path")

    updated: ClipObject = dict(clip)  # type: ignore[assignment]

    if not main_path or not Path(main_path).exists():
        logger.warning(
            f"SubtitlesNode: skipping {clip_id} — clip path missing or not found."
        )
        return updated

    out_path = str(clips_dir / f"{clip_id}_sub.mp4")

    try:
        import whisper

        logger.debug(f"  {clip_id}: loading Whisper '{_WHISPER_MODEL}' model …")
        model = whisper.load_model(_WHISPER_MODEL)

        logger.debug(f"  {clip_id}: transcribing {Path(main_path).name} …")
        result = model.transcribe(main_path, verbose=False)
        segments = result.get("segments", [])

        if not segments:
            logger.warning(f"  {clip_id}: Whisper returned no segments — skipping subtitles.")
            return updated

        srt_content = _build_srt(segments)

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".srt", delete=False, encoding="utf-8"
        ) as srt_file:
            srt_file.write(srt_content)
            srt_path = srt_file.name

        logger.debug(f"  {clip_id}: SRT written to {srt_path} ({len(segments)} entries)")

        # Build force_style string for ASS-compatible subtitle rendering
        force_style = (
            f"FontSize={_FONT_SIZE},"
            f"PrimaryColour={_FONT_COLOR},"
            f"OutlineColour={_OUTLINE_COLOR},"
            f"Outline={_OUTLINE_WIDTH},"
            f"Alignment=2,"       # bottom-centre (ASS numpad alignment)
            f"MarginV=60"         # margin from bottom edge in pixels
        )

        inp   = ffmpeg.input(main_path)
        # subtitles filter requires the path to use forward slashes and no colons on Windows
        srt_path_safe = srt_path.replace("\\", "/").replace(":", "\\:")
        video = inp.video.filter(
            "subtitles",
            srt_path_safe,
            force_style=force_style,
        )

        has_audio = any(
            s.get("codec_type") == "audio"
            for s in ffmpeg.probe(main_path)["streams"]
        )

        if has_audio:
            out = ffmpeg.output(
                video,
                inp.audio,
                out_path,
                vcodec=_VIDEO_CODEC,
                acodec=_AUDIO_CODEC,
                r=_FPS,
                video_bitrate=_VIDEO_BITRATE,
                audio_bitrate=_AUDIO_BITRATE,
                pix_fmt="yuv420p",
                movflags="+faststart",
            )
        else:
            out = ffmpeg.output(
                video,
                out_path,
                vcodec=_VIDEO_CODEC,
                r=_FPS,
                video_bitrate=_VIDEO_BITRATE,
                pix_fmt="yuv420p",
                movflags="+faststart",
            )

        out.overwrite_output().run(capture_stdout=True, capture_stderr=True)
        updated["path"] = out_path
        logger.info(
            f"  ✓ {clip_id}: subtitles burned ({len(segments)} segments) "
            f"→ {Path(out_path).name}"
        )

    except ffmpeg.Error as exc:
        stderr = exc.stderr.decode("utf-8", errors="replace") if exc.stderr else ""
        logger.error(
            f"  ✗ {clip_id}: ffmpeg error in SubtitlesNode.\n    {stderr[-400:]}"
        )
    except ImportError:
        logger.error(
            "  ✗ SubtitlesNode: openai-whisper is not installed. "
            "Run: pip install openai-whisper"
        )
    except Exception as exc:
        logger.error(f"  ✗ {clip_id}: unexpected error in SubtitlesNode – {exc}")
    finally:
        # Clean up temp SRT file
        try:
            if "srt_path" in dir() and Path(srt_path).exists():
                os.remove(srt_path)
        except OSError:
            pass

    return updated


# ---------------------------------------------------------------------------
# Node function
# ---------------------------------------------------------------------------

def subtitles_node(state: LongToShortsState) -> Dict[str, Any]:
    """
    LangGraph node: transcribe clips with Whisper and burn subtitles.

    Enabled when ADD_SUBTITLES env var is "1"/"true" OR state["add_subtitles"] is True.

    Input state keys used:
        generated_clips – List[ClipObject] from TopTextNode / ContentGenNode
        add_subtitles   – boolean feature flag (optional, overridden by env var)

    Output state keys:
        generated_clips – updated with new path (pointing to *_sub.mp4)
        current_step
    """
    env_val    = os.getenv("ADD_SUBTITLES", "").strip().lower()
    state_flag = state.get("add_subtitles", False)

    if env_val in ("0", "false", "no"):
        logger.info("SubtitlesNode: ADD_SUBTITLES disabled — skipping.")
        return {"current_step": "subtitles_skipped"}

    if env_val not in ("1", "true", "yes") and not state_flag:
        logger.info("SubtitlesNode: not enabled — skipping.")
        return {"current_step": "subtitles_skipped"}

    clips: List[ClipObject] = state.get("generated_clips", [])
    if not clips:
        logger.warning("SubtitlesNode: no clips to process.")
        return {"generated_clips": [], "current_step": "subtitles_skipped"}

    output_dir = Path(os.getenv("OUTPUT_DIR", "output")) / "clips"
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info(
        f"SubtitlesNode: burning subtitles into {len(clips)} clip(s) "
        f"(whisper={_WHISPER_MODEL}, fontsize={_FONT_SIZE})"
    )

    results: List[Optional[ClipObject]] = [None] * len(clips)

    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as executor:
        future_to_idx = {
            executor.submit(_burn_subtitles, clip, output_dir): idx
            for idx, clip in enumerate(clips)
        }
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                results[idx] = future.result()
            except Exception as exc:
                logger.error(f"SubtitlesNode: worker raised unexpectedly: {exc}")
                results[idx] = clips[idx]

    final_clips: List[ClipObject] = [r for r in results if r is not None]

    successful = sum(
        1 for c in final_clips
        if c.get("path") and "_sub.mp4" in (c.get("path") or "")
    )
    logger.info(
        f"SubtitlesNode: {successful}/{len(clips)} clips got subtitles burned."
    )

    return {
        "generated_clips": final_clips,
        "current_step":    "subtitles_burned",
    }
