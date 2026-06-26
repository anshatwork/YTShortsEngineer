"""
agents/long_to_shorts/api/runner.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Background-thread orchestrator that drives the Long-to-Shorts LangGraph
pipeline and writes results back to the job store.

Each job is executed by calling `run_job(job_id, request)` inside a
ThreadPoolExecutor (see app.py).  This mirrors the logic in
`run_clipping_workflow.py` but returns structured data instead of printing.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agents.long_to_shorts.api.models import JobRequest

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Ensure project root is on sys.path so sibling packages resolve correctly
# when this module is imported from within the agents sub-package.
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parents[4]  # YTShortsEnginer/
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def run_job(job_id: str, request: "JobRequest") -> None:
    """Execute a job, teeing all of its logs into ``logs/jobs/<job_id>.log``.

    Thin wrapper around :func:`_run_job_impl` that binds the per-job logging
    context (see ``core.logging_config.job_log_context``) so every log line for
    this run — including those from nodes, the LLM and ffmpeg — is correlated
    and captured in a single self-contained file.
    """
    from core.logging_config import job_log_context

    with job_log_context(job_id):
        _run_job_impl(job_id, request)


def _run_job_impl(job_id: str, request: "JobRequest") -> None:
    """
    Execute the Long-to-Shorts pipeline for *request* and persist results to
    the job store.  Designed to be called from a background thread.

    Transitions:
        queued → running → done | failed
    """
    # Late imports keep module load fast (heavy deps: torch, whisper, ffmpeg…)
    from agents.long_to_shorts.api.job_store import job_store
    from agents.long_to_shorts.api.models import ClipResult
    from agents.long_to_shorts import long_to_shorts_app
    import time

    # We re-use the helpers in run_clipping_workflow to avoid duplication.
    # They are plain functions with no global state so safe to import here.
    try:
        from run_clipping_workflow import (
            get_youtube_inputs,
            probe_video,
            get_transcript,
        )
    except ImportError as exc:
        logger.error("Could not import run_clipping_workflow helpers: %s", exc)
        job_store.update(job_id, status="failed", error=str(exc))
        return

    # ------------------------------------------------------------------
    # Mark job as running
    # ------------------------------------------------------------------
    job_store.update(job_id, status="running")
    logger.info("[job:%s] started — source=%s", job_id,
                request.youtube_url or request.video_path)

    try:
        # ----------------------------------------------------------------
        # Phase 1: Obtain video path + transcript
        # ----------------------------------------------------------------
        timed_segments: list = []

        if request.youtube_url:
            # Best-effort: upgrade the job's displayed name to the real video
            # title (the derived video-id label was set at creation). Never let
            # a metadata-lookup failure affect the run.
            try:
                from tools.youtube.downloader import fetch_video_title
                title = fetch_video_title(request.youtube_url)
                if title:
                    job_store.update(job_id, video_title=title)
            except Exception as title_exc:  # noqa: BLE001
                logger.warning("[job:%s] title fetch skipped: %s", job_id, title_exc)

            video_path, transcript, timed_segments = get_youtube_inputs(
                request.youtube_url
            )
        else:
            video_path = request.video_path
            if not video_path:
                raise ValueError(
                    "Either 'youtube_url' or 'video_path' must be provided."
                )
            probe_video(video_path)

            if request.srt_path:
                # User supplied subtitles → burn from them (no Whisper) and
                # derive the analysis transcript from the same captions.
                from agents.long_to_shorts.srt_utils import parse_srt

                timed_segments = parse_srt(request.srt_path)
                if not timed_segments:
                    raise ValueError(
                        f"No subtitle segments parsed from SRT: {request.srt_path}"
                    )
                transcript = " ".join(
                    seg["text"] for seg in timed_segments if seg.get("text")
                )
                logger.info(
                    "[job:%s] using uploaded SRT (%d segments) — Whisper skipped",
                    job_id, len(timed_segments),
                )
            else:
                transcript = get_transcript(request.transcript, video_path)

        # ----------------------------------------------------------------
        # Phase 2: Set env feature-flags (nodes read from os.environ)
        # ----------------------------------------------------------------
        os.environ["ADD_INTRO"]     = "1" if request.add_intro     else "0"
        os.environ["ADD_TOP_TEXT"]  = "1" if request.add_top_text  else "0"
        os.environ["ADD_THUMBNAIL"] = "1" if request.add_thumbnail else "0"
        os.environ["ADD_SUBTITLES"] = "1" if request.add_subtitles else "0"
        os.environ["ADD_MUSIC"]     = "1" if request.add_music     else "0"
        os.environ["SUBTITLES_POSITION"] = request.subtitle_position
        os.environ["SUBTITLES_SIZE"]     = request.subtitle_size

        # ----------------------------------------------------------------
        # Phase 3: Build initial state and invoke LangGraph pipeline
        # ----------------------------------------------------------------
        # `job_id` is threaded through state so each node can correlate its
        # logs and update job_store.current_node for the frontend.
        initial_state = {
            "job_id":            job_id,
            "current_node":      "initialized",
            "source_video_path": str(Path(video_path).resolve()),
            "transcript":        transcript,
            "top_n_clips":       request.top_n,
            "user_context":      request.user_context,
            "add_top_text":      request.add_top_text,
            "add_thumbnail":     request.add_thumbnail,
            "thumbnail_style":   request.thumbnail_style,
            "add_subtitles":     request.add_subtitles,
            "subtitle_position": request.subtitle_position,
            "subtitle_size":     request.subtitle_size,
            "add_intro":         request.add_intro,
            "add_music":         request.add_music,
            "music_volume_db":   request.music_volume_db,
            "clip_mode":         request.clip_mode,
            "timed_transcript":  timed_segments,
            "analyzed_segments": [],
            "generated_clips":   [],
            "current_step":      "initialized",
            "error":             None,
        }

        t0 = time.time()
        logger.info("[job:%s] invoking LangGraph pipeline …", job_id)
        final_state = long_to_shorts_app.invoke(initial_state)
        elapsed = time.time() - t0

        # ----------------------------------------------------------------
        # Phase 4: Surface pipeline-level errors
        # ----------------------------------------------------------------
        if final_state.get("error"):
            raise RuntimeError(f"Pipeline error: {final_state['error']}")

        logger.info("[job:%s] pipeline done in %.1fs — clips=%d",
                    job_id, elapsed, len(final_state.get("generated_clips", [])))

        # ----------------------------------------------------------------
        # Phase 5: Convert ClipObject dicts → ClipResult Pydantic models
        # ----------------------------------------------------------------
        clips = [
            ClipResult(
                clip_id=c["clip_id"],
                path=c.get("path"),
                timestamp_range=tuple(c["timestamp_range"]),
                hook_score=c["hook_score"],
                title=c.get("title"),
                summary=c.get("summary"),
                hook_text=c.get("hook_text"),
                hashtags=c.get("hashtags"),
                thumbnail_path=c.get("thumbnail_path"),
                music_theme=c.get("music_theme"),
                music_title=c.get("music_title"),
                music_source=c.get("music_source"),
                music_attribution=c.get("music_attribution"),
            )
            for c in final_state.get("generated_clips", [])
        ]

        job_store.update(job_id, status="done", clips=clips, current_node="done")

    except Exception as exc:  # noqa: BLE001
        logger.exception("[job:%s] failed: %s", job_id, exc)
        job_store.update(job_id, status="failed", error=str(exc))
