"""
agents/long_to_shorts/subtitles_node.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
SubtitlesNode – burn styled subtitles into each extracted clip.

Subtitle source (in priority order)
-------------------------------------
1.  ``state["timed_transcript"]``  — a list of
    ``{"text": str, "start": float, "duration": float}`` entries produced by
    ``tools.youtube.transcript.fetch_timed_segments`` (YouTube captions API).
    When this is present **no Whisper model is loaded or run**.

2.  Whisper fallback — if the state has no timed transcript (e.g. local video
    workflow without YouTube captions), each clip is auto-transcribed with
    OpenAI Whisper as before.

For every clip in generated_clips:
  1.  Obtains per-clip subtitle segments (see above).
  2.  Writes a temporary .srt file.
  3.  Burns the subtitles into the video using ffmpeg's ``subtitles`` filter
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
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional

import ffmpeg  # ffmpeg-python (used for probe only)

from agents.long_to_shorts._logging_utils import node_stage
from agents.state import ClipObject, LongToShortsState

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants / config
# ---------------------------------------------------------------------------

_WHISPER_MODEL: str    = os.getenv("SUBTITLES_WHISPER_MODEL", "base")
# FontName is REQUIRED for libass to resolve a face on Windows. Without it the
# subtitles filter silently renders nothing (ffmpeg still exits 0).
_FONT_NAME: str        = os.getenv("SUBTITLES_FONT_NAME", "Arial")
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
    Convert a list of segment dicts into a valid SRT string.

    Accepted formats:
      • Whisper output — each dict has keys "start", "end", "text"
      • YouTube captions — each dict has keys "start", "duration", "text"
        ("end" is derived as start + duration)
    """
    lines: List[str] = []
    for i, seg in enumerate(segments, start=1):
        start = float(seg["start"])
        if "end" in seg:
            end = float(seg["end"])
        else:
            end = start + float(seg.get("duration", 2.0))
        text = _wrap_subtitle_line(seg["text"].strip())
        start_ts = _seconds_to_srt_ts(start)
        end_ts   = _seconds_to_srt_ts(end)
        lines.append(f"{i}\n{start_ts} --> {end_ts}\n{text}\n")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helper: slice global timed segments to a clip's time window
# ---------------------------------------------------------------------------

def _slice_timed_segments(
    timed_segments: List[Dict[str, Any]],
    clip_start: float,
    clip_end: float,
) -> List[Dict[str, Any]]:
    """
    Return a *new* list of timed segments that overlap with [clip_start, clip_end],
    with timestamps re-zeroed relative to *clip_start* (so they line up with
    the extracted clip which starts at t=0).

    Any segment that is at least partially within the clip window is included.
    """
    sliced: List[Dict[str, Any]] = []
    for seg in timed_segments:
        s_start = float(seg["start"])
        duration = float(seg.get("duration", 2.0))
        s_end   = s_start + duration

        # Skip segments entirely outside the clip window
        if s_end <= clip_start or s_start >= clip_end:
            continue

        # Re-zero the timestamps relative to clip_start
        rel_start = max(s_start - clip_start, 0.0)
        rel_end   = min(s_end - clip_start, clip_end - clip_start)

        sliced.append({
            "text":     seg["text"],
            "start":    rel_start,
            "end":      rel_end,
            "duration": rel_end - rel_start,
        })

    return sliced


# ---------------------------------------------------------------------------
# Per-clip worker
# ---------------------------------------------------------------------------

def _burn_subtitles(
    clip: ClipObject,
    clips_dir: Path,
    timed_segments: Optional[List[Dict[str, Any]]],
) -> ClipObject:
    """
    Obtain subtitle segments and burn them into *clip*.

    If *timed_segments* is provided (YouTube captions already in state), the
    global segments are sliced to the clip's time window — **no Whisper**.
    Otherwise Whisper is loaded and run on the clip file as a fallback.

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
    clip_start, clip_end = clip["timestamp_range"]

    try:
        # ------------------------------------------------------------------
        # Obtain segments
        # ------------------------------------------------------------------
        if timed_segments:
            segments = _slice_timed_segments(timed_segments, clip_start, clip_end)
            logger.debug(
                f"  {clip_id}: using {len(segments)} timed-transcript segments "
                f"(sliced from global captions, no Whisper)"
            )
            if not segments:
                logger.warning(
                    f"  {clip_id}: no caption segments overlap "
                    f"[{clip_start:.1f}s → {clip_end:.1f}s] — skipping subtitles."
                )
                return updated
        else:
            # Fallback: run Whisper on the clip file
            import whisper

            logger.debug(f"  {clip_id}: loading Whisper '{_WHISPER_MODEL}' model …")
            model = whisper.load_model(_WHISPER_MODEL)

            logger.debug(f"  {clip_id}: transcribing {Path(main_path).name} …")
            result   = model.transcribe(main_path, verbose=False)
            segments = result.get("segments", [])

            if not segments:
                logger.warning(
                    f"  {clip_id}: Whisper returned no segments — skipping subtitles."
                )
                return updated

        # ------------------------------------------------------------------
        # Write SRT
        # ------------------------------------------------------------------
        srt_content = _build_srt(segments)

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".srt", delete=False, encoding="utf-8"
        ) as srt_file:
            srt_file.write(srt_content)
            srt_path = srt_file.name

        logger.debug(f"  {clip_id}: SRT written to {srt_path} ({len(segments)} entries)")

        # ------------------------------------------------------------------
        # Burn subtitles via ffmpeg  (subprocess — bypasses ffmpeg-python's
        # filter-value backslash-escaping which corrupts Windows paths)
        # ------------------------------------------------------------------
        force_style = (
            f"FontName={_FONT_NAME},"
            f"FontSize={_FONT_SIZE},"
            f"PrimaryColour={_FONT_COLOR},"
            f"OutlineColour={_OUTLINE_COLOR},"
            f"Outline={_OUTLINE_WIDTH},"
            f"Alignment=2,"
            f"MarginV=60"
        )

        # Windows-safe subtitles path handling.  The ffmpeg subtitles filter
        # path is a minefield of escaping: a drive-letter colon (C:) is split
        # by the filtergraph parser (two passes), so even an escaped "\:"
        # survives pass 1 only to be re-split in pass 2 — ffmpeg then reads the
        # tail as the filter's 2nd positional arg (original_size) and errors
        # with "Unable to parse option value ... as image size".
        #
        # We sidestep the whole problem: run ffmpeg with cwd set to the SRT's
        # directory and reference it by *bare filename* (e.g. tmpXXXX.srt) —
        # no colon, no backslash, nothing to escape.  Because cwd changes, the
        # input/output must be absolute.  cwd= is per-subprocess and
        # thread-safe (unlike os.chdir), so it's safe in the ThreadPoolExecutor.
        main_abs = os.path.abspath(main_path)
        out_abs  = os.path.abspath(out_path)
        srt_dir  = os.path.dirname(os.path.abspath(srt_path))
        srt_name = os.path.basename(srt_path)

        # force_style contains commas (FontSize=40,PrimaryColour=...).  In an
        # ffmpeg filtergraph a comma separates *filters*, so the value must be
        # wrapped in single quotes to protect its commas — otherwise ffmpeg
        # reads "OutlineColour=..." as a new (invalid) filter.  Because we run
        # ffmpeg via subprocess with an args list (no shell), these single
        # quotes reach ffmpeg verbatim and act as filtergraph quoting.
        filter_str = f"subtitles={srt_name}:force_style='{force_style}'"

        has_audio = any(
            s.get("codec_type") == "audio"
            for s in ffmpeg.probe(main_abs)["streams"]
        )

        cmd: List[str] = [
            "ffmpeg", "-y",
            "-i", main_abs,
            "-vf", filter_str,
            "-vcodec", _VIDEO_CODEC,
            "-r", str(_FPS),
            "-b:v", _VIDEO_BITRATE,
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
        ]
        if has_audio:
            cmd += ["-acodec", _AUDIO_CODEC, "-b:a", _AUDIO_BITRATE]
        cmd.append(out_abs)

        proc = subprocess.run(cmd, capture_output=True, cwd=srt_dir)
        stderr_txt = proc.stderr.decode("utf-8", errors="replace")
        if proc.returncode != 0:
            raise RuntimeError(
                f"ffmpeg exited {proc.returncode}\n{stderr_txt[-600:]}"
            )

        # libass failures (e.g. no usable font) are *silent* — ffmpeg still
        # exits 0 but draws nothing. Surface those warnings so a "subtitles
        # don't appear" run is diagnosable from the logs.
        lowered = stderr_txt.lower()
        if any(tok in lowered for tok in ("fontselect", "glyph", "no usable font")):
            logger.warning(
                f"  ! {clip_id}: libass font warning during subtitle burn — "
                f"text may not render. Set SUBTITLES_FONT_NAME to an installed "
                f"font.\n    {stderr_txt[-400:]}"
            )
        else:
            logger.debug(f"  {clip_id}: ffmpeg stderr tail:\n{stderr_txt[-400:]}")

        # Confirm the output actually exists and is non-trivial before we point
        # the clip at it (guards against a 0-byte / failed write slipping past).
        if not Path(out_path).exists() or Path(out_path).stat().st_size < 1024:
            raise RuntimeError(
                f"subtitled output missing or empty: {out_path}"
            )

        updated["path"] = out_path
        logger.info(
            f"  ✓ {clip_id}: subtitles burned ({len(segments)} segments) "
            f"→ {Path(out_path).name}"
        )

    except (ffmpeg.Error, RuntimeError) as exc:
        logger.error(
            f"  ✗ {clip_id}: ffmpeg error in SubtitlesNode.\n    {exc}"
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
    LangGraph node: burn subtitles into each clip.

    Subtitle source (priority):
      1. state["timed_transcript"] — YouTube captions sliced to each clip's
         window.  Fast, no Whisper model loaded.
      2. Whisper fallback — transcribes each clip file individually.

    Enabled when ADD_SUBTITLES env var is "1"/"true" OR state["add_subtitles"]
    is True.

    Input state keys used:
        generated_clips    – List[ClipObject] from TopTextNode / ContentGenNode
        add_subtitles      – boolean feature flag (optional, overridden by env var)
        timed_transcript   – optional list of timed caption dicts from YouTube

    Output state keys:
        generated_clips – updated with new path (pointing to *_sub.mp4)
        current_step
    """
    with node_stage(state, "subtitles"):
        return _subtitles_impl(state)


def _subtitles_impl(state: LongToShortsState) -> Dict[str, Any]:
    # Per-job state is the source of truth (set by API runner and CLI). The
    # process-global env var is only a fallback for callers that don't populate
    # state — relying on env alone races across concurrent jobs in the executor.
    state_flag = state.get("add_subtitles")
    if state_flag is None:
        enabled = os.getenv("ADD_SUBTITLES", "").strip().lower() in ("1", "true", "yes")
    else:
        enabled = bool(state_flag)

    if not enabled:
        logger.info("SubtitlesNode: not enabled — skipping.")
        return {"current_step": "subtitles_skipped"}

    clips: List[ClipObject] = state.get("generated_clips", [])
    if not clips:
        logger.warning("SubtitlesNode: no clips to process.")
        return {"generated_clips": [], "current_step": "subtitles_skipped"}

    # Prefer the per-run clips_dir set by ClippingLogicNode; fall back to the
    # legacy flat layout only when this node runs in isolation.
    clips_dir = state.get("clips_dir")
    output_dir = Path(clips_dir) if clips_dir else Path(os.getenv("OUTPUT_DIR", "output")) / "clips"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Retrieve timed transcript from state (may be None for local video paths)
    timed_segments: Optional[List[Dict[str, Any]]] = state.get("timed_transcript")

    if timed_segments:
        logger.info(
            f"SubtitlesNode: burning subtitles into {len(clips)} clip(s) "
            f"using YouTube captions ({len(timed_segments)} segments, no Whisper)"
        )
    else:
        logger.info(
            f"SubtitlesNode: burning subtitles into {len(clips)} clip(s) "
            f"using Whisper fallback (whisper={_WHISPER_MODEL})"
        )

    results: List[Optional[ClipObject]] = [None] * len(clips)

    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as executor:
        future_to_idx = {
            executor.submit(_burn_subtitles, clip, output_dir, timed_segments): idx
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
