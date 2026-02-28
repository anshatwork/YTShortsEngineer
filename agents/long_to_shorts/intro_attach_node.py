"""
agents/long_to_shorts/intro_attach_node.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
IntroAttachNode – prepend a title-card intro with a crossfade transition
to each generated Short clip.

For every clip in generated_clips (which has path AND title set by
ContentGenNode):
  1.  Renders a 9:16 intro clip (default 2.5 s) using ffmpeg's lavfi
      `color` source + `drawtext` filter showing the clip title on a
      semi-transparent dark background.
  2.  Uses ffmpeg's `xfade` filter to produce a 0.4 s crossfade between
      the intro and the main clip.
  3.  Writes the final combined clip to  <OUTPUT_DIR>/clips/<clip_id>_final.mp4
      and updates clip["path"] to the new path.

Clips without a title fall back to "Now Playing" as the intro text.
Clips without a valid path are skipped.

Configuration via environment variables (all optional):
    INTRO_DURATION_SECS  – float, intro length in seconds (default: 2.5)
    INTRO_BG_COLOR       – ffmpeg color string, e.g. "black" or "0x1a1a2e" (default: black)
    INTRO_FONT_COLOR     – ffmpeg color string for title text (default: white)
    INTRO_FONT_SIZE      – integer, font size (default: 52)
    INTRO_TRANSITION_SECS – float, crossfade duration in seconds (default: 0.4)
    ADD_INTRO            – "0" or "false" to disable intros entirely (default: enabled)
"""

import logging
import os
import re
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional

import ffmpeg  # ffmpeg-python

from agents.state import ClipObject, LongToShortsState

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants / config (overridable via environment)
# ---------------------------------------------------------------------------

_INTRO_DURATION: float    = float(os.getenv("INTRO_DURATION_SECS", "2.5"))
_INTRO_BG_COLOR: str      = os.getenv("INTRO_BG_COLOR", "black")
_INTRO_FONT_COLOR: str    = os.getenv("INTRO_FONT_COLOR", "white")
_INTRO_FONT_SIZE: int     = int(os.getenv("INTRO_FONT_SIZE", "52"))
_TRANSITION_SECS: float   = float(os.getenv("INTRO_TRANSITION_SECS", "0.4"))
_MAX_WORKERS: int         = 4

# Output resolution – must match ClippingLogicNode (9:16 Shorts)
_WIDTH: int  = 1080
_HEIGHT: int = 1920
_FPS: int    = 60

_VIDEO_CODEC: str = "libx264"
_AUDIO_CODEC: str = "aac"
_VIDEO_BITRATE: str = "8000k"
_AUDIO_BITRATE: str = "192k"


# ---------------------------------------------------------------------------
# Safe title for drawtext
# ---------------------------------------------------------------------------

def _safe_drawtext(title: str) -> str:
    r"""
    Escape a title string so it is safe for use inside ffmpeg's drawtext filter.

    ffmpeg drawtext metachars: ' : \ [ ] , ;
    We also strip newlines so the text stays on one logical line (word-wrap
    is handled by drawtext's line_spacing / word_spacing options).
    """
    # Collapse whitespace / newlines to a single space
    text = re.sub(r"\s+", " ", title.strip())
    # Escape characters that ffmpeg drawtext interprets specially
    for char in ("\\", "'", ":", "[", "]", ",", ";"):
        text = text.replace(char, "\\" + char)
    return text


# ---------------------------------------------------------------------------
# Wrap long title text across multiple lines
# ---------------------------------------------------------------------------

def _wrap_title(title: str, max_chars: int = 22) -> str:
    """
    Break title into lines of at most *max_chars* characters so it fits
    the 9:16 frame without overflow.  Returns a drawtext-safe string with
    `\n` (literal backslash-n) as the newline token expected by drawtext.
    """
    words = title.split()
    lines: List[str] = []
    current = ""
    for word in words:
        if current and len(current) + 1 + len(word) > max_chars:
            lines.append(current)
            current = word
        else:
            current = (current + " " + word).strip() if current else word
    if current:
        lines.append(current)

    # Join with drawtext's newline escape and apply character-level escaping
    return r"\n".join(_safe_drawtext(line) for line in lines)


# ---------------------------------------------------------------------------
# Build the intro clip (in-memory temp file)
# ---------------------------------------------------------------------------

def _render_intro(title: str, output_path: str) -> None:
    """
    Render an intro title-card clip to *output_path* (mp4).

    Layout:
        - Full 9:16 frame ({_WIDTH}x{_HEIGHT}) filled with _INTRO_BG_COLOR
        - Centred title text in _INTRO_FONT_COLOR / _INTRO_FONT_SIZE
        - Duration: _INTRO_DURATION seconds at _FPS fps
        - Silent audio track (so the concat step always has audio)
    """
    wrapped_text = _wrap_title(title, max_chars=22)
    line_height = _INTRO_FONT_SIZE + 8   # approximate px between lines

    # drawtext filter – center the (possibly multi-line) title
    drawtext_filter = (
        f"drawtext=text='{wrapped_text}'"
        f":fontsize={_INTRO_FONT_SIZE}"
        f":fontcolor={_INTRO_FONT_COLOR}"
        f":x=(w-text_w)/2"
        f":y=(h-text_h)/2"
        f":line_spacing={line_height}"
    )

    # Video: lavfi color source forced to yuv420p + drawtext
    # The `format=yuv420p` filter ensures the lavfi color source (which defaults
    # to yuv444p) is converted before drawtext so all downstream filters and the
    # final encode stay in yuv420p — the only pixel format accepted by Windows
    # Media Player, YouTube, and virtually every consumer device.
    video = (
        ffmpeg
        .input(
            f"color=c={_INTRO_BG_COLOR}:s={_WIDTH}x{_HEIGHT}:d={_INTRO_DURATION}",
            f="lavfi",
        )
        .video
        .filter("format", "yuv420p")   # pin pixel format before drawtext
        .filter("drawtext", **{
            "text":         wrapped_text,
            "fontsize":     str(_INTRO_FONT_SIZE),
            "fontcolor":    _INTRO_FONT_COLOR,
            "x":            "(w-text_w)/2",
            "y":            "(h-text_h)/2",
            "line_spacing": str(line_height),
        })
    )

    # Silent audio at 44100 Hz stereo (same spec used in main clips)
    audio = ffmpeg.input(
        f"anullsrc=r=44100:cl=stereo",
        f="lavfi",
        t=_INTRO_DURATION,
    ).audio

    (
        ffmpeg
        .output(
            video,
            audio,
            output_path,
            vcodec=_VIDEO_CODEC,
            acodec=_AUDIO_CODEC,
            r=_FPS,
            video_bitrate=_VIDEO_BITRATE,
            audio_bitrate=_AUDIO_BITRATE,
            pix_fmt="yuv420p",       # belt-and-suspenders: also force on encode
            movflags="+faststart",   # moov atom at start for streaming
            t=_INTRO_DURATION,
        )
        .overwrite_output()
        .run(capture_stdout=True, capture_stderr=True)
    )


# ---------------------------------------------------------------------------
# Concat intro + main clip with xfade transition
# ---------------------------------------------------------------------------

def _concat_with_xfade(intro_path: str, main_path: str, output_path: str) -> None:
    """
    Concatenate *intro_path* and *main_path* with an `xfade` crossfade
    (duration = _TRANSITION_SECS) and write to *output_path*.

    The crossfade starts at (intro_duration - transition_secs) so the fade
    begins just before the intro ends and finishes just after the main clip
    begins.

    If *main_path* has no audio stream, the concat is video-only.
    """
    offset = max(0.0, _INTRO_DURATION - _TRANSITION_SECS)

    intro_streams = ffmpeg.probe(intro_path)["streams"]
    main_streams  = ffmpeg.probe(main_path)["streams"]

    has_audio = any(s.get("codec_type") == "audio" for s in main_streams)

    intro_in = ffmpeg.input(intro_path)
    main_in  = ffmpeg.input(main_path)

    # Video xfade
    video_out = ffmpeg.filter(
        [intro_in.video, main_in.video],
        "xfade",
        transition="fade",
        duration=_TRANSITION_SECS,
        offset=offset,
    )

    if has_audio:
        # Resample both audio streams to the same rate before crossfade to
        # avoid "sample rate mismatch" errors when intro (44100 Hz anullsrc)
        # meets a main clip with a different rate.
        intro_audio = intro_in.audio.filter("aresample", 44100)
        main_audio  = main_in.audio.filter("aresample", 44100)
        audio_out = ffmpeg.filter(
            [intro_audio, main_audio],
            "acrossfade",
            d=_TRANSITION_SECS,
            c1="tri",
            c2="tri",
        )
        out = ffmpeg.output(
            video_out,
            audio_out,
            output_path,
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
            video_out,
            output_path,
            vcodec=_VIDEO_CODEC,
            r=_FPS,
            video_bitrate=_VIDEO_BITRATE,
            pix_fmt="yuv420p",
            movflags="+faststart",
        )

    out.overwrite_output().run(capture_stdout=True, capture_stderr=True)


# ---------------------------------------------------------------------------
# Per-clip worker
# ---------------------------------------------------------------------------

def _attach_intro(clip: ClipObject, clips_dir: Path) -> ClipObject:
    """
    Build intro + transition + main clip for a single ClipObject.
    Returns updated ClipObject with path pointing to the final video.
    On failure, returns original clip unchanged (path = existing clip).
    """
    clip_id    = clip["clip_id"]
    main_path  = clip.get("path")
    title      = clip.get("title") or "Now Playing"

    updated: ClipObject = dict(clip)  # type: ignore[assignment]

    if not main_path or not Path(main_path).exists():
        logger.warning(
            f"IntroAttachNode: skipping {clip_id} — main clip path missing or not found."
        )
        return updated

    final_path = str(clips_dir / f"{clip_id}_final.mp4")

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            intro_tmp = str(Path(tmpdir) / "intro.mp4")

            # 1. Render intro title card
            logger.debug(f"  {clip_id}: rendering intro …  title='{title[:40]}'")
            _render_intro(title, intro_tmp)

            # 2. Concat with crossfade transition
            logger.debug(f"  {clip_id}: applying xfade transition …")
            _concat_with_xfade(intro_tmp, main_path, final_path)

        updated["path"] = final_path
        logger.info(f"  ✓ {clip_id}: intro attached → {Path(final_path).name}")

    except ffmpeg.Error as exc:
        stderr = exc.stderr.decode("utf-8", errors="replace") if exc.stderr else ""
        logger.error(
            f"  ✗ {clip_id}: ffmpeg error during intro attach.\n"
            f"    {stderr[-400:]}"
        )
    except Exception as exc:
        logger.error(f"  ✗ {clip_id}: unexpected error – {exc}")

    return updated


# ---------------------------------------------------------------------------
# Node function
# ---------------------------------------------------------------------------

def intro_attach_node(state: LongToShortsState) -> Dict[str, Any]:
    """
    LangGraph node: prepend a title-card intro (with crossfade) to each clip.

    Input state keys used:
        generated_clips – List[ClipObject] from ContentGenNode (path + title set)

    Output state keys:
        generated_clips – updated with new path (pointing to *_final.mp4)
        current_step
    """
    # Allow disabling intros via environment variable
    add_intro_env = os.getenv("ADD_INTRO", "1").strip().lower()
    if add_intro_env in ("0", "false", "no"):
        logger.info("IntroAttachNode: ADD_INTRO disabled — skipping.")
        return {"current_step": "intro_skipped"}

    clips: List[ClipObject] = state.get("generated_clips", [])

    if not clips:
        logger.warning("IntroAttachNode: no clips to process.")
        return {"generated_clips": [], "current_step": "intro_skipped"}

    output_dir = Path(os.getenv("OUTPUT_DIR", "output")) / "clips"
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info(
        f"IntroAttachNode: attaching intros to {len(clips)} clip(s) "
        f"(intro={_INTRO_DURATION}s, transition={_TRANSITION_SECS}s)"
    )

    results: List[Optional[ClipObject]] = [None] * len(clips)

    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as executor:
        future_to_idx = {
            executor.submit(_attach_intro, clip, output_dir): idx
            for idx, clip in enumerate(clips)
        }
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                results[idx] = future.result()
            except Exception as exc:
                logger.error(f"IntroAttachNode: worker raised unexpectedly: {exc}")
                results[idx] = clips[idx]

    final_clips: List[ClipObject] = [r for r in results if r is not None]

    successful = sum(
        1 for c in final_clips
        if c.get("path") and "_final.mp4" in (c.get("path") or "")
    )
    logger.info(
        f"IntroAttachNode: {successful}/{len(clips)} clips got intro attached."
    )

    return {
        "generated_clips": final_clips,
        "current_step":    "intro_attached",
    }
