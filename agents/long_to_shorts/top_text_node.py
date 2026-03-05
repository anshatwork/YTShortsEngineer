"""
agents/long_to_shorts/top_text_node.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
TopTextNode – burn a persistent hook-text overlay at the top of each clip.

For every clip in generated_clips (path + hook_text / title set by ContentGenNode):
  1.  Takes `hook_text` from the ClipObject, falling back to `title`.
  2.  Word-wraps it to ≤25 chars per line.
  3.  Burns each line as a `drawtext` filter with a semi-transparent dark box
      behind the text, centred horizontally near the top of the 9:16 frame.
  4.  Writes the result to  <OUTPUT_DIR>/clips/<clip_id>_noted.mp4  and
      updates clip["path"] to the new path.

Clips without a valid path are skipped unchanged.

Configuration via environment variables (all optional):
    ADD_TOP_TEXT          – "1"/"true" to enable (default: disabled)
    TOP_TEXT_FONT_SIZE    – integer, font size in pixels (default: 52)
    TOP_TEXT_COLOR        – ffmpeg color string for text (default: white)
    TOP_TEXT_BG_ALPHA     – float 0–1, background box opacity (default: 0.55)
    TOP_TEXT_Y_PX         – integer, top of text block in pixels (default: 80)
    TOP_TEXT_LINE_CHARS   – integer, max chars per wrapped line (default: 25)
"""

import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional

import ffmpeg  # ffmpeg-python

from agents.state import ClipObject, LongToShortsState

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants / config (overridable via environment)
# ---------------------------------------------------------------------------

_FONT_SIZE: int      = int(os.getenv("TOP_TEXT_FONT_SIZE", "52"))
_FONT_COLOR: str     = os.getenv("TOP_TEXT_COLOR", "white")
_BG_ALPHA: float     = float(os.getenv("TOP_TEXT_BG_ALPHA", "0.55"))
_TOP_Y: int          = int(os.getenv("TOP_TEXT_Y_PX", "80"))
_LINE_CHARS: int     = int(os.getenv("TOP_TEXT_LINE_CHARS", "25"))
_MAX_WORKERS: int    = 4

# Output resolution – must match ClippingLogicNode
_WIDTH: int  = 1080
_HEIGHT: int = 1920
_FPS: int    = 60

_VIDEO_CODEC: str   = "libx264"
_AUDIO_CODEC: str   = "aac"
_VIDEO_BITRATE: str = "8000k"
_AUDIO_BITRATE: str = "192k"


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------

def _wrap_lines(text: str, max_chars: int = _LINE_CHARS) -> List[str]:
    """Word-wrap *text* into lines of at most *max_chars* characters."""
    words = re.sub(r"\s+", " ", text.strip()).split()
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
    return lines or [""]


def _escape_drawtext(text: str) -> str:
    """Escape a text string for the ffmpeg drawtext `text=` option."""
    text = text.replace("\\", "\\\\")
    text = text.replace("'",  "\\'")
    text = text.replace(":",  "\\:")
    text = text.replace("%",  "%%")
    return text


# ---------------------------------------------------------------------------
# Per-clip worker
# ---------------------------------------------------------------------------

def _add_top_text(clip: ClipObject, clips_dir: Path) -> ClipObject:
    """
    Burn hook-text overlay at the top of *clip*.
    Returns updated ClipObject with path pointing to *_noted.mp4.
    On failure, returns original clip unchanged.
    """
    clip_id   = clip["clip_id"]
    main_path = clip.get("path")
    text      = clip.get("hook_text") or clip.get("title") or ""

    updated: ClipObject = dict(clip)  # type: ignore[assignment]

    if not text.strip():
        logger.warning(f"TopTextNode: skipping {clip_id} — no hook_text or title.")
        return updated

    if not main_path or not Path(main_path).exists():
        logger.warning(
            f"TopTextNode: skipping {clip_id} — clip path missing or not found."
        )
        return updated

    out_path = str(clips_dir / f"{clip_id}_noted.mp4")

    try:
        lines     = _wrap_lines(text, max_chars=_LINE_CHARS)
        line_gap  = 14
        line_step = _FONT_SIZE + line_gap
        block_h   = len(lines) * line_step - line_gap

        # Box padding around the entire text block
        box_pad = 20
        box_x   = 0   # full-width strip; actual x offset handled by drawtext x=
        box_y   = max(0, _TOP_Y - box_pad)
        box_w   = _WIDTH
        box_h   = block_h + box_pad * 2

        inp   = ffmpeg.input(main_path)
        video = inp.video

        # Draw a full-width semi-transparent background strip first via drawbox
        bg_color = f"black@{_BG_ALPHA:.2f}"
        video = video.filter(
            "drawbox",
            x=str(box_x),
            y=str(box_y),
            w=str(box_w),
            h=str(box_h),
            color=bg_color,
            t="fill",
        )

        # One drawtext call per wrapped line
        for i, line in enumerate(lines):
            y_px = _TOP_Y + i * line_step
            video = video.filter(
                "drawtext",
                text=_escape_drawtext(line),
                fontsize=str(_FONT_SIZE),
                fontcolor=_FONT_COLOR,
                x="(w-text_w)/2",
                y=str(y_px),
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
        logger.info(f"  ✓ {clip_id}: top-text overlay applied → {Path(out_path).name}")

    except ffmpeg.Error as exc:
        stderr = exc.stderr.decode("utf-8", errors="replace") if exc.stderr else ""
        logger.error(
            f"  ✗ {clip_id}: ffmpeg error in TopTextNode.\n    {stderr[-400:]}"
        )
    except Exception as exc:
        logger.error(f"  ✗ {clip_id}: unexpected error in TopTextNode – {exc}")

    return updated


# ---------------------------------------------------------------------------
# Node function
# ---------------------------------------------------------------------------

def top_text_node(state: LongToShortsState) -> Dict[str, Any]:
    """
    LangGraph node: burn a persistent hook-text overlay at the top of each clip.

    Enabled when ADD_TOP_TEXT env var is "1"/"true" OR state["add_top_text"] is True.

    Input state keys used:
        generated_clips – List[ClipObject] from ContentGenNode (path + hook_text/title set)
        add_top_text    – boolean feature flag (optional, overridden by env var)

    Output state keys:
        generated_clips – updated with new path (pointing to *_noted.mp4)
        current_step
    """
    env_val = os.getenv("ADD_TOP_TEXT", "").strip().lower()
    state_flag = state.get("add_top_text", False)

    # Env var "0"/"false" hard-disables regardless of state flag
    if env_val in ("0", "false", "no"):
        logger.info("TopTextNode: ADD_TOP_TEXT disabled — skipping.")
        return {"current_step": "top_text_skipped"}

    # Enabled if env var is explicitly "1"/"true" OR state flag is set
    if env_val not in ("1", "true", "yes") and not state_flag:
        logger.info("TopTextNode: not enabled — skipping.")
        return {"current_step": "top_text_skipped"}

    clips: List[ClipObject] = state.get("generated_clips", [])
    if not clips:
        logger.warning("TopTextNode: no clips to process.")
        return {"generated_clips": [], "current_step": "top_text_skipped"}

    output_dir = Path(os.getenv("OUTPUT_DIR", "output")) / "clips"
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info(
        f"TopTextNode: adding top-text overlay to {len(clips)} clip(s) "
        f"(fontsize={_FONT_SIZE}, alpha={_BG_ALPHA})"
    )

    results: List[Optional[ClipObject]] = [None] * len(clips)

    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as executor:
        future_to_idx = {
            executor.submit(_add_top_text, clip, output_dir): idx
            for idx, clip in enumerate(clips)
        }
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                results[idx] = future.result()
            except Exception as exc:
                logger.error(f"TopTextNode: worker raised unexpectedly: {exc}")
                results[idx] = clips[idx]

    final_clips: List[ClipObject] = [r for r in results if r is not None]

    successful = sum(
        1 for c in final_clips
        if c.get("path") and "_noted.mp4" in (c.get("path") or "")
    )
    logger.info(f"TopTextNode: {successful}/{len(clips)} clips got top-text applied.")

    return {
        "generated_clips": final_clips,
        "current_step":    "top_text_applied",
    }
