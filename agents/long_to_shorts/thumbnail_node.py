"""
agents/long_to_shorts/thumbnail_node.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
ThumbnailNode – generate an AI-directed thumbnail image for each clip.

For every clip in generated_clips (path + title/hook_text set by ContentGenNode):
  1.  The LLM acts as creative director — it writes the headline, picks an accent
      color and text placement, and supplies a fallback image-search query
      (see tools/thumbnail.py:ThumbnailSpec).
  2.  ffmpeg grabs the most representative frame of the clip as the backdrop;
      when the clip has no usable frame, a topical Pixabay photo is used instead.
  3.  The headline is burned over the backdrop and written to
      <clips_dir>/<clip_id>_thumb.jpg, recorded as clip["thumbnail_path"].

This runs right after ContentGenNode so the backdrop comes from the *clean* base
clip (before subtitle/hook overlays) and the LLM metadata is already populated.
clip["path"] is left untouched — only thumbnail_path is added.

Clips without a valid path still attempt the Pixabay fallback. Any failure leaves
the clip without a thumbnail rather than breaking the run.

Configuration via environment variables (all optional):
    ADD_THUMBNAIL          – "1"/"true" to enable (default: disabled)
    THUMBNAIL_WIDTH/HEIGHT – output geometry (default: 1080×1920)
    THUMBNAIL_FONT_SIZE    – headline font size (default: 96)
    PIXABAY_API_KEY        – enables the image-search fallback
"""

import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional

from agents.long_to_shorts._logging_utils import node_stage
from agents.state import ClipObject, LongToShortsState
from tools.thumbnail import generate_thumbnail

logger = logging.getLogger(__name__)

_MAX_WORKERS: int = 4


# ---------------------------------------------------------------------------
# Per-clip worker
# ---------------------------------------------------------------------------

def _make_thumbnail(
    clip: ClipObject,
    clips_dir: Path,
    style: str = "auto",
    user_context: Optional[str] = None,
) -> ClipObject:
    """Generate a thumbnail for *clip*; returns the (possibly) updated ClipObject.

    Never raises — on any failure the clip is returned unchanged (no thumbnail).
    """
    clip_id = clip["clip_id"]
    updated: ClipObject = dict(clip)  # type: ignore[assignment]

    out_path = str(clips_dir / f"{clip_id}_thumb.jpg")
    try:
        result = generate_thumbnail(
            clip_meta={
                "title": clip.get("title"),
                "hook_text": clip.get("hook_text"),
                "summary": clip.get("summary"),
                "hashtags": clip.get("hashtags"),
            },
            video_path=clip.get("path"),
            out_path=out_path,
            style=style,
            user_context=user_context,
        )
        if result:
            updated["thumbnail_path"] = result
            logger.info("  ✓ %s: thumbnail → %s", clip_id, Path(result).name)
        else:
            logger.warning("  ✗ %s: no thumbnail produced.", clip_id)
    except Exception as exc:  # noqa: BLE001 — thumbnails are best-effort
        logger.error("  ✗ %s: unexpected error in ThumbnailNode – %s", clip_id, exc)

    return updated


# ---------------------------------------------------------------------------
# Node function
# ---------------------------------------------------------------------------

def thumbnail_node(state: LongToShortsState) -> Dict[str, Any]:
    """
    LangGraph node: generate an AI-directed thumbnail image for each clip.

    Enabled when ADD_THUMBNAIL env var is "1"/"true" OR state["add_thumbnail"] is True.

    Input state keys used:
        generated_clips – List[ClipObject] from ContentGenNode (path + title/hook_text set)
        add_thumbnail   – boolean feature flag (optional, overridden by env var)

    Output state keys:
        generated_clips – updated with thumbnail_path on each clip
        current_step
    """
    with node_stage(state, "thumbnail"):
        return _thumbnail_impl(state)


def _thumbnail_impl(state: LongToShortsState) -> Dict[str, Any]:
    # Per-job state is the source of truth (set by API runner and CLI). The
    # process-global env var is only a fallback for callers that don't populate
    # state — relying on env alone races across concurrent jobs in the executor.
    state_flag = state.get("add_thumbnail")
    if state_flag is None:
        enabled = os.getenv("ADD_THUMBNAIL", "").strip().lower() in ("1", "true", "yes")
    else:
        enabled = bool(state_flag)

    if not enabled:
        logger.info("ThumbnailNode: not enabled — skipping.")
        return {"current_step": "thumbnail_skipped"}

    clips: List[ClipObject] = state.get("generated_clips", [])
    if not clips:
        logger.warning("ThumbnailNode: no clips to process.")
        return {"generated_clips": [], "current_step": "thumbnail_skipped"}

    clips_dir = state.get("clips_dir")
    output_dir = Path(clips_dir) if clips_dir else Path(os.getenv("OUTPUT_DIR", "output")) / "clips"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Job-wide caption style (applies to every clip); "auto" lets the LLM choose.
    style = state.get("thumbnail_style") or os.getenv("THUMBNAIL_STYLE", "auto")
    user_context = state.get("user_context")

    logger.info("ThumbnailNode: generating thumbnails for %d clip(s) (style=%s).", len(clips), style)

    results: List[Optional[ClipObject]] = [None] * len(clips)

    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as executor:
        future_to_idx = {
            executor.submit(_make_thumbnail, clip, output_dir, style, user_context): idx
            for idx, clip in enumerate(clips)
        }
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                results[idx] = future.result()
            except Exception as exc:  # noqa: BLE001
                logger.error("ThumbnailNode: worker raised unexpectedly: %s", exc)
                results[idx] = clips[idx]

    final_clips: List[ClipObject] = [r for r in results if r is not None]

    successful = sum(1 for c in final_clips if c.get("thumbnail_path"))
    logger.info("ThumbnailNode: %d/%d clips got a thumbnail.", successful, len(clips))

    return {
        "generated_clips": final_clips,
        "current_step": "thumbnail_done",
    }
