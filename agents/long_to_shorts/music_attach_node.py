"""
agents/long_to_shorts/music_attach_node.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
MusicAttachNode – mix the background-music track recommended by ContentGenNode
under each clip's audio.

For every clip in generated_clips that carries a ``music_path`` (set by
ContentGenNode via the asset-discovery layer):
  1.  Mixes the track beneath the clip's existing audio with
      ``mix_background_music`` (looped/trimmed to the clip length).
  2.  Writes the result to  <clips_dir>/<clip_id>_music.mp4  and updates
      clip["path"] to the new file.

Runs last in the graph so music plays under the fully-assembled clip (including
the intro, which carries a silent track). Clips without a recommended track are
passed through unchanged.

Configuration via environment variables (all optional):
    ADD_MUSIC       – "1"/"true" to enable (default: disabled; prefer state flag)
    MUSIC_VOLUME_DB – float, music gain vs. clip audio (default: -18.0)
"""

import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional

from agents.long_to_shorts._logging_utils import node_stage
from agents.state import ClipObject, LongToShortsState
from tools.video_editing.audio_mixer import mix_background_music

logger = logging.getLogger(__name__)

_DEFAULT_VOLUME_DB: float = float(os.getenv("MUSIC_VOLUME_DB", "-18.0"))
_MAX_WORKERS: int = 4


# ---------------------------------------------------------------------------
# Per-clip worker
# ---------------------------------------------------------------------------

def _attach_music(clip: ClipObject, clips_dir: Path, volume_db: float) -> ClipObject:
    """Mix the recommended track under one clip's audio.

    Returns an updated ClipObject with path pointing at the mixed file. On any
    failure (or when the clip has no recommended track), returns the clip
    unchanged so the pipeline never loses a clip over background music.
    """
    clip_id    = clip["clip_id"]
    main_path  = clip.get("path")
    music_path = clip.get("music_path")

    updated: ClipObject = dict(clip)  # type: ignore[assignment]

    if not music_path or not Path(music_path).exists():
        logger.info(f"  • {clip_id}: no recommended track — leaving audio as-is.")
        return updated
    if not main_path or not Path(main_path).exists():
        logger.warning(
            f"MusicAttachNode: skipping {clip_id} — clip path missing or not found."
        )
        return updated

    out_path = clips_dir / f"{clip_id}_music.mp4"

    try:
        mix_background_music(main_path, music_path, out_path, volume_db=volume_db)
        updated["path"] = str(out_path)
        logger.info(
            f"  ✓ {clip_id}: mixed '{clip.get('music_title') or Path(music_path).name}' "
            f"({clip.get('music_theme')}) → {out_path.name}"
        )
    except Exception as exc:  # noqa: BLE001 — best-effort; keep the un-mixed clip
        logger.error(f"  ✗ {clip_id}: music mix failed – {exc}. Keeping original clip.")

    return updated


# ---------------------------------------------------------------------------
# Node function
# ---------------------------------------------------------------------------

def music_attach_node(state: LongToShortsState) -> Dict[str, Any]:
    """
    LangGraph node: mix recommended background music into each clip.

    Input state keys used:
        generated_clips – List[ClipObject] with path + music_path set upstream
        add_music       – per-job flag (preferred over ADD_MUSIC env)
        music_volume_db – per-job music gain (preferred over MUSIC_VOLUME_DB env)

    Output state keys:
        generated_clips – updated with new path (pointing to *_music.mp4)
        current_step
    """
    with node_stage(state, "music_attach"):
        return _music_attach_impl(state)


def _music_attach_impl(state: LongToShortsState) -> Dict[str, Any]:
    # Per-job state is the source of truth (set by API runner and CLI); the
    # process-global env var is only a fallback. Music defaults OFF — it is an
    # opt-in enrichment, unlike the intro which defaults ON.
    state_flag = state.get("add_music")
    if state_flag is None:
        enabled = os.getenv("ADD_MUSIC", "0").strip().lower() not in ("0", "false", "no")
    else:
        enabled = bool(state_flag)

    if not enabled:
        logger.info("MusicAttachNode: ADD_MUSIC disabled — skipping.")
        return {"current_step": "music_skipped"}

    clips: List[ClipObject] = state.get("generated_clips", [])
    if not clips:
        logger.warning("MusicAttachNode: no clips to process.")
        return {"generated_clips": [], "current_step": "music_skipped"}

    volume_db = float(state.get("music_volume_db", _DEFAULT_VOLUME_DB))

    # Prefer the per-run clips_dir set by ClippingLogicNode; fall back to the
    # legacy flat layout only when this node runs in isolation.
    clips_dir = state.get("clips_dir")
    output_dir = Path(clips_dir) if clips_dir else Path(os.getenv("OUTPUT_DIR", "output")) / "clips"
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info(
        f"MusicAttachNode: mixing music into {len(clips)} clip(s) (volume={volume_db} dB)"
    )

    results: List[Optional[ClipObject]] = [None] * len(clips)

    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as executor:
        future_to_idx = {
            executor.submit(_attach_music, clip, output_dir, volume_db): idx
            for idx, clip in enumerate(clips)
        }
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                results[idx] = future.result()
            except Exception as exc:
                logger.error(f"MusicAttachNode: worker raised unexpectedly: {exc}")
                results[idx] = clips[idx]

    final_clips: List[ClipObject] = [r for r in results if r is not None]

    successful = sum(
        1 for c in final_clips
        if c.get("path") and "_music.mp4" in (c.get("path") or "")
    )
    logger.info(f"MusicAttachNode: {successful}/{len(clips)} clips got music mixed.")

    return {
        "generated_clips": final_clips,
        "current_step":    "music_attached",
    }
