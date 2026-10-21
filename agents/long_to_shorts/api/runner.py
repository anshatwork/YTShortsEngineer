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


def run_job(job_id: str, request: "JobRequest", user_id: str | None = None) -> None:
    """Execute a job, teeing all of its logs into ``logs/jobs/<job_id>.log``.

    Thin wrapper around :func:`_run_job_impl` that binds the per-job logging
    context (see ``core.logging_config.job_log_context``) so every log line for
    this run — including those from nodes, the LLM and ffmpeg — is correlated
    and captured in a single self-contained file.

    *user_id* (when supplied) lets the run pick up that user's BYOK LLM
    credential so their job uses their own key and bypasses our GPU.
    """
    from core.logging_config import job_log_context

    with job_log_context(job_id):
        _run_job_impl(job_id, request, user_id)


def _refund_clip_credits(job_id: str, user_id: str | None) -> None:
    """Return the clip-job's credits after a failure (see credits.refund_for_op).
    Idempotent on the job id, so a retried failure refunds only once."""
    from agents.long_to_shorts.api.credits import refund_for_op
    refund_for_op(user_id, "clip", key=f"refund:{job_id}")


def _clips_from_state(state: dict) -> list:
    """Convert the pipeline's ``generated_clips`` ClipObject dicts → ClipResult models.

    Reused for both incremental mid-run persistence and the terminal write, so the
    frontend can surface playable clips as soon as they're extracted and keep them
    updating in place as enhancement nodes refine each clip.
    """
    from agents.long_to_shorts.api.models import ClipResult

    return [
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
        for c in state.get("generated_clips", [])
    ]


def _resolve_byok_credential(user_id: str | None, job_id: str):
    """Return the user's BYOK LLMCredential, or None to use our default provider.

    Any lookup/decrypt failure degrades gracefully to the default (our GPU) — a
    billing/credential hiccup must never fail an otherwise-valid job. Never logs
    the raw key.
    """
    if not user_id:
        return None
    try:
        from agents.long_to_shorts.api.db.user_llm_credentials_store import (
            user_llm_credential_store,
        )
        from tools.llm.credentials import redact_key

        cred = user_llm_credential_store.get(user_id)
        if cred is not None:
            logger.info(
                "[job:%s] BYOK credential found — provider=%s key=%s (our GPU bypassed)",
                job_id, cred.provider, redact_key(cred.api_key),
            )
        return cred
    except Exception as exc:  # noqa: BLE001 — fall back to default provider
        logger.warning(
            "[job:%s] BYOK lookup failed (%s); using default provider.",
            job_id, type(exc).__name__,
        )
        return None


def _run_job_impl(job_id: str, request: "JobRequest", user_id: str | None = None) -> None:
    """
    Execute the Long-to-Shorts pipeline for *request* and persist results to
    the job store.  Designed to be called from a background thread.

    Transitions:
        queued → running → done | failed
    """
    # Late imports keep module load fast (heavy deps: torch, whisper, ffmpeg…)
    from agents.long_to_shorts.api.job_store import job_store
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
        _refund_clip_credits(job_id, user_id)
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

        # Resolve the caller's BYOK credential (if any) and bind it for the whole
        # pipeline run: every get_llm() inside the nodes then uses the user's key
        # and provider instead of our GPU Ollama default. None => default path.
        from tools.llm.credentials import llm_credential_context

        byok_credential = _resolve_byok_credential(user_id, job_id)

        t0 = time.time()
        logger.info("[job:%s] invoking LangGraph pipeline …", job_id)
        # Stream (not invoke) so we can persist clips incrementally: as soon as a
        # node yields a state with rendered clips, write them to the job store.
        # EventEmittingStore turns each update() into an SSE `update`, so the
        # frontend surfaces playable clips mid-run instead of waiting for `done`.
        # `stream_mode="values"` yields the full accumulated state after each
        # super-step, so the last value is the complete final state.
        final_state = initial_state
        last_clip_sig: tuple | None = None
        with llm_credential_context(byok_credential):
            for state in long_to_shorts_app.stream(
                initial_state, stream_mode="values"
            ):
                final_state = state
                partial = _clips_from_state(state)
                if not partial:
                    continue
                # Only emit when the clip set actually changed (a new clip or an
                # updated path) — avoids an SSE frame for nodes that don't touch
                # clips. status stays "running"; the terminal write flips it.
                sig = tuple((c.clip_id, c.path) for c in partial)
                if sig != last_clip_sig:
                    last_clip_sig = sig
                    job_store.update(job_id, clips=partial)
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
        clips = _clips_from_state(final_state)

        job_store.update(job_id, status="done", clips=clips, current_node="done")

        # Opt-in auto-publish: if the user asked for it before the run, upload
        # every rendered clip to their YouTube channel now. Best-effort — never
        # affects the (already successful) clip job.
        _maybe_enqueue_auto_uploads(job_id, request, user_id, clips)

        # Additive KG hook: feed the source video into the knowledge graph so its
        # understanding accumulates. Idempotent (content-hash keys) and fully
        # decoupled — a KG failure never affects the completed clip job.
        _maybe_enqueue_kg_ingestion(job_id, request, user_id, video_path)

    except Exception as exc:  # noqa: BLE001
        logger.exception("[job:%s] failed: %s", job_id, exc)
        job_store.update(job_id, status="failed", error=str(exc))
        _refund_clip_credits(job_id, user_id)


def _maybe_enqueue_auto_uploads(
    job_id: str,
    request: "JobRequest",
    user_id: str | None,
    clips: list,
) -> None:
    """Auto-publish every rendered clip to YouTube when the user opted in before
    the run (``request.auto_upload``).

    Best-effort and fully decoupled from the clip job's success:
      * no account connected  → log + skip (the job still succeeds);
      * per-clip metadata is derived from the generated title/summary/hashtags;
      * each upload reuses the same runner/idempotency path as manual uploads.
    Any error here is swallowed — a publish hiccup must never fail the clip job.
    """
    try:
        if not getattr(request, "auto_upload", False):
            return
        if not user_id:
            logger.info("[job:%s] auto-upload requested but no user id; skipping.", job_id)
            return

        # Require a connected YouTube account (a refresh token). Skip cleanly
        # otherwise — we can't (and shouldn't) publish without one.
        from agents.long_to_shorts.api.youtube_credentials_store import (
            youtube_credentials_store,
        )

        record = youtube_credentials_store.get(user_id)
        if not record or not record.get("refresh_token"):
            logger.warning(
                "[job:%s] auto-upload requested but no YouTube account connected; "
                "skipping (connect YouTube, then re-run or upload manually).",
                job_id,
            )
            return

        from agents.long_to_shorts.api.models import YouTubeUploadRequest
        from agents.long_to_shorts.api.youtube_upload_store import youtube_upload_store
        from agents.long_to_shorts.api.youtube_upload_runner import run_youtube_upload_job
        from core.execution import get_task_queue

        privacy = getattr(request, "auto_upload_privacy", "public") or "public"
        queue = get_task_queue()

        enqueued = 0
        for clip in clips:
            if not clip.path:
                continue  # nothing rendered to upload
            title = (clip.title or clip.hook_text or clip.clip_id)[:100]
            tags = [
                t.lstrip("#").strip()
                for t in (clip.hashtags or [])
                if t and t.strip()
            ]
            upload = youtube_upload_store.create(
                user_id=user_id,
                parent_job_id=job_id,
                clip_id=clip.clip_id,
                title=title,
                privacy_status=privacy,
            )
            req = YouTubeUploadRequest(
                parent_job_id=job_id,
                clip_id=clip.clip_id,
                title=title,
                description=(clip.summary or "")[:5000],
                tags=tags,
                privacy_status=privacy,
            )
            queue.enqueue(run_youtube_upload_job, upload.upload_id, req, user_id)
            enqueued += 1

        logger.info(
            "[job:%s] auto-upload enqueued %d clip(s) as %s.",
            job_id, enqueued, privacy,
        )
    except Exception as exc:  # noqa: BLE001 — auto-upload is best-effort
        logger.warning("[job:%s] auto-upload enqueue skipped: %s", job_id, exc)


def _maybe_enqueue_kg_ingestion(
    job_id: str, request: "JobRequest", user_id: str | None, video_path: str
) -> None:
    """Register + enqueue KG ingestion of the clip job's source (best-effort).

    Gated by KG_ENABLED so it is a no-op unless the graph is turned on. Any error
    here is swallowed — the clip job has already succeeded and must not be affected.
    """
    try:
        from core.kg import driver

        if not driver.kg_enabled():
            return
        from agents.long_to_shorts.api.asset_store import asset_store
        from agents.long_to_shorts.api.ingestion_job_store import ingestion_job_store
        from agents.long_to_shorts.api.ingestion_runner import run_ingestion
        from core.execution import get_task_queue

        uri = request.youtube_url or video_path
        owner = user_id or "00000000-0000-0000-0000-000000000001"
        asset = asset_store.register(
            user_id=owner, media_type="video", uri=uri,
            filename=request.video_filename, title=None,
        )
        ing = ingestion_job_store.create(asset.asset_id, user_id=owner)
        get_task_queue().enqueue(run_ingestion, ing.ingestion_job_id, asset.asset_id, owner)
        logger.info("[job:%s] KG ingestion enqueued — ingestion_job=%s asset=%s",
                    job_id, ing.ingestion_job_id, asset.asset_id)
    except Exception as exc:  # noqa: BLE001 — KG is best-effort, never fail the clip job
        logger.warning("[job:%s] KG ingestion enqueue skipped: %s", job_id, exc)
