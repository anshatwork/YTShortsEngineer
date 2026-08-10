"""
agents/long_to_shorts/api/publishing_runner.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The orchestrator step function for the Autonomous Publishing Agent.

``run_publishing_step(publishing_job_id)`` is the single self-contained,
task-queue-enqueued unit of work. It loads the durable job row, runs the ONE
stage its current status calls for, persists the result, and stops at a human
gate or terminal. The human approval endpoints (and the initial start) enqueue
the next step — so every enqueued step runs to a gate/terminal, and a crash mid
step is recovered by :func:`recover_publishing_jobs`, which re-enqueues any job
left in a resumable (non-gate, non-terminal) status. Steps are idempotent (the
clip pipeline + upload are CAS/idempotency-keyed), so redo is safe and cheap.

Stage mapping (status → work):
    discovering                         → discovery (→ waiting_for_source_approval)
    generating|scoring|evaluating|revising → clip pipeline + review sub-graph
                                          (→ waiting_for_upload_approval)
    uploading                           → YouTube upload (→ complete)
    waiting_* / terminal                → no-op
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from core.execution.lifecycle import (
    PUB_COMPLETE,
    PUB_DISCOVERING,
    PUB_EVALUATING,
    PUB_FAILED,
    PUB_GENERATING,
    PUB_REVISING,
    PUB_SCORING,
    PUB_UPLOADING,
    PUB_WAITING_SOURCE,
    PUB_WAITING_REVIEW,
    PUB_WAITING_UPLOAD,
    can_transition_publishing,
)

logger = logging.getLogger(__name__)

_GEN_REVIEW_STATES = {PUB_GENERATING, PUB_SCORING, PUB_EVALUATING, PUB_REVISING}


# ---------------------------------------------------------------------------
# Entry point (enqueued on the task queue)
# ---------------------------------------------------------------------------

def run_publishing_step(publishing_job_id: str, user_id: Optional[str] = None) -> None:
    """Run one stage of the publishing workflow, teeing logs into the job log."""
    from core.logging_config import job_log_context

    with job_log_context(publishing_job_id):
        _run_step_impl(publishing_job_id, user_id)


def _run_step_impl(publishing_job_id: str, user_id: Optional[str]) -> None:
    from agents.long_to_shorts.api.publishing_store import publishing_store

    job = publishing_store.get(publishing_job_id)
    if job is None:
        logger.warning("[publish:%s] step: job not found", publishing_job_id)
        return
    owner = user_id or publishing_store.owner_of(publishing_job_id)
    status = job.status
    logger.info("[publish:%s] step — status=%s", publishing_job_id, status)

    try:
        if status == PUB_DISCOVERING:
            _do_discovery(publishing_job_id, owner)
        elif status == PUB_WAITING_REVIEW:
            _do_context(publishing_job_id, owner)
        elif status in _GEN_REVIEW_STATES:
            _do_generate_and_review(publishing_job_id, owner)
        elif status == PUB_UPLOADING:
            _do_upload(publishing_job_id, owner)
        else:
            # waiting_* gates and terminal states have no queued work.
            logger.info("[publish:%s] step: nothing to do at status=%s",
                        publishing_job_id, status)
    except Exception as exc:  # noqa: BLE001 — any stage failure fails the run
        logger.exception("[publish:%s] step failed at status=%s", publishing_job_id, status)
        _fail(publishing_job_id, owner, str(exc))


# ---------------------------------------------------------------------------
# Stage helpers
# ---------------------------------------------------------------------------

def _do_discovery(pub_id: str, user_id: Optional[str]) -> None:
    from agents.long_to_shorts.api.publishing_store import publishing_store
    from agents.long_to_shorts.api.youtube_service import get_youtube_service

    req = publishing_store.get_request_for_user(pub_id, user_id or "")
    query = req.query if req else (publishing_store.get(pub_id).query or "")
    top_n = (req.top_n_candidates if req else None)
    days_ago = req.days_ago if req else 7
    user_context = req.user_context if req else None

    recs = get_youtube_service().search_and_rank(
        query, top_n=top_n, days_ago=days_ago, user_context=user_context
    )
    detail = (
        f"Found {len(recs)} candidate(s) — approve one to continue."
        if recs else "No candidates found — try refresh with a different query."
    )
    _advance(pub_id, PUB_WAITING_SOURCE, candidates=recs, phase_detail=detail)


def _do_context(pub_id: str, user_id: Optional[str]) -> None:
    from agents.long_to_shorts.api.publishing_store import publishing_store
    from agents.long_to_shorts.api.youtube_service import get_youtube_service

    job = publishing_store.get(pub_id)
    if not job or not job.approved_video_url:
        raise RuntimeError("no approved source video for context enrichment")
    context = get_youtube_service().fetch_video_context(job.approved_video_url)
    from agents.long_to_shorts.api.models import YouTubeVideoContext
    parsed = YouTubeVideoContext(**context)
    publishing_store.update(
        pub_id, source_context=parsed,
        phase_detail="video context ready - review instructions before generating clips",
    )


def _do_generate_and_review(pub_id: str, user_id: Optional[str]) -> None:
    """Generate clips (reusing the clip pipeline) then run the review sub-graph,
    ending at the upload gate. Idempotent: if a clip job already ran (crash
    recovery), its clips are reloaded rather than regenerated."""
    from agents.long_to_shorts.api.job_store import job_store
    from agents.long_to_shorts.api.models import ClipResult, JobRequest
    from agents.long_to_shorts.api.publishing_store import publishing_store
    from agents.long_to_shorts.api.runner import _resolve_byok_credential, run_job
    from agents.publishing.graph import publishing_review_app
    from agents.publishing.schemas import EvalReport
    from tools.llm.credentials import llm_credential_context

    job = publishing_store.get(pub_id)
    req = publishing_store.get_request_for_user(pub_id, user_id or "")

    if job and job.source_context is None and job.approved_video_url:
        try:
            from agents.long_to_shorts.api.youtube_service import get_youtube_service
            from agents.long_to_shorts.api.models import YouTubeVideoContext
            context = get_youtube_service().fetch_video_context(job.approved_video_url)
            publishing_store.update(pub_id, source_context=YouTubeVideoContext(**context),
                                    phase_detail="source context enriched - generating clips")
            job = publishing_store.get(pub_id)
        except Exception as exc:
            logger.warning("[publish:%s] context enrichment degraded: %s", pub_id, exc)

    # -- Stage 2: clip generation (reused pipeline, unchanged) --
    # status == GENERATING means "generate" (fresh run, or a regenerate from the
    # upload gate). status in {scoring,evaluating,revising} means a crash mid-
    # review — reload the already-generated clips instead of paying to redo them.
    clip_job_id = job.clip_job_id
    need_generate = (job.status == PUB_GENERATING) or (not clip_job_id)
    if need_generate:
        if not job.approved_video_url:
            raise ValueError("no approved_video_url to generate from")
        clip_request = JobRequest(
            youtube_url=job.approved_video_url,
            top_n=(req.top_n_clips if req else 3),
            add_subtitles=req.add_subtitles if req else False,
            add_top_text=req.add_top_text if req else False,
            add_intro=req.add_intro if req else True,
            add_music=req.add_music if req else False,
            add_thumbnail=req.add_thumbnail if req else True,
            thumbnail_style=req.thumbnail_style if req else "auto",
            clip_mode=req.clip_mode if req else "portrait",
            user_context=req.user_context if req else None,
        )
        clip_job = job_store.create(clip_request, user_id=user_id or "dev")
        clip_job_id = clip_job.job_id
        publishing_store.update(pub_id, clip_job_id=clip_job_id,
                                phase_detail="generating clips")
        run_job(clip_job_id, clip_request, user_id)  # synchronous; drives its own store

    clip_job = job_store.get(clip_job_id)
    if clip_job is None or clip_job.status == "failed":
        raise RuntimeError(
            f"clip generation failed: {getattr(clip_job, 'error', 'unknown')}"
        )
    clips: List[Dict[str, Any]] = [c.model_dump() for c in (clip_job.clips or [])]
    if not clips:
        raise RuntimeError("clip generation produced no clips")

    # -- Stage 3+4: scoring → eval → bounded revision (review sub-graph) --
    review_state = {
        "job_id": pub_id,
        "clips": clips,
        "user_context": req.user_context if req else None,
        "revision_count": 0,
    }
    byok = _resolve_byok_credential(user_id, pub_id)
    with llm_credential_context(byok):
        final = publishing_review_app.invoke(review_state)

    selected_id = final.get("selected_clip_id")
    selected_eval_raw = final.get("selected_eval") or {}
    review_clips = final.get("clips") or clips
    selected_dict = next((c for c in review_clips if c.get("clip_id") == selected_id), None)
    if selected_dict is None:
        selected_dict = review_clips[0]

    eval_report = EvalReport(**selected_eval_raw) if selected_eval_raw else EvalReport(
        clip_id=selected_dict.get("clip_id")
    )
    # If we exhausted the revision budget without passing, flag it so the human
    # sees the borderline quality at the upload gate.
    if not eval_report.passed:
        eval_report.best_effort = True

    generated_clips = [ClipResult(
        clip_id=c["clip_id"], path=c.get("path"),
        timestamp_range=tuple(c.get("timestamp_range", (0.0, 0.0))),
        hook_score=c.get("hook_score", 0.0), title=c.get("title"),
        summary=c.get("summary"), hook_text=c.get("hook_text"),
        hashtags=c.get("hashtags"), thumbnail_path=c.get("thumbnail_path"),
        music_theme=c.get("music_theme"), music_title=c.get("music_title"),
        music_source=c.get("music_source"), music_attribution=c.get("music_attribution"),
    ) for c in review_clips]
    selected_clip = ClipResult(
        clip_id=selected_dict["clip_id"],
        path=selected_dict.get("path"),
        timestamp_range=tuple(selected_dict.get("timestamp_range", (0.0, 0.0))),
        hook_score=selected_dict.get("hook_score", 0.0),
        title=selected_dict.get("title"),
        summary=selected_dict.get("summary"),
        hook_text=selected_dict.get("hook_text"),
        hashtags=selected_dict.get("hashtags"),
        thumbnail_path=selected_dict.get("thumbnail_path"),
        music_theme=selected_dict.get("music_theme"),
        music_title=selected_dict.get("music_title"),
        music_source=selected_dict.get("music_source"),
        music_attribution=selected_dict.get("music_attribution"),
    )

    detail = (
        f"Selected {selected_clip.clip_id} (eval {eval_report.overall_score}/100"
        f"{', best-effort' if eval_report.best_effort else ''}) — approve to publish."
    )
    _advance(
        pub_id, PUB_WAITING_UPLOAD,
        generated_clips=generated_clips,
        selected_clip_id=selected_clip.clip_id,
        selected_clip=selected_clip, eval_report=eval_report,
        scored_clips=[__sc(s) for s in (final.get("scored_clips") or [])],
        revision_count=int(final.get("revision_count") or 0),
        phase_detail=detail,
    )


def _do_upload(pub_id: str, user_id: Optional[str]) -> None:
    from agents.long_to_shorts.api.publishing_store import publishing_store
    from agents.long_to_shorts.api.youtube_service import get_youtube_service

    job = publishing_store.get(pub_id)
    clip = job.selected_clip
    if clip is None or not job.clip_job_id:
        raise RuntimeError("nothing selected to upload")
    if not clip.path:
        raise RuntimeError("selected clip has no rendered file")

    result = get_youtube_service().run_upload(
        clip_job_id=job.clip_job_id,
        clip_id=clip.clip_id,
        user_id=user_id or "dev",
        title=clip.title or "New Short",
        description=clip.summary or "",
        tags=job.upload_tags or clip.hashtags or [],
        privacy_status=job.upload_privacy_status,
        category_id=job.upload_category_id,
    )
    if result is None or result.status != "done" or not result.video_id:
        raise RuntimeError(f"upload failed: {getattr(result, 'error', 'unknown')}")

    _advance(
        pub_id, PUB_COMPLETE,
        upload_id=result.upload_id, video_id=result.video_id,
        video_url=result.video_url, phase_detail="published to YouTube",
    )


# ---------------------------------------------------------------------------
# Transition + failure helpers
# ---------------------------------------------------------------------------

def __sc(scorecard_dump: Any):
    """Rehydrate a ScoreCard from the sub-graph's dict dump (typed for the store)."""
    from agents.publishing.schemas import ScoreCard

    if isinstance(scorecard_dump, ScoreCard):
        return scorecard_dump
    return ScoreCard(**scorecard_dump)


def _advance(pub_id: str, target: str, **fields) -> None:
    """Guarded transition + persist. Logs and skips an illegal hop rather than
    crashing (the recovery sweep will re-drive from the persisted status)."""
    from agents.long_to_shorts.api.publishing_store import publishing_store

    job = publishing_store.get(pub_id)
    current = getattr(job, "status", None)
    if current and current != target and not can_transition_publishing(current, target):
        logger.error("[publish:%s] illegal transition %s -> %s (skipped)", pub_id, current, target)
        return
    publishing_store.update(pub_id, status=target, **fields)
    logger.info("[publish:%s] %s -> %s", pub_id, current, target)


def _fail(pub_id: str, user_id: Optional[str], error: str) -> None:
    from agents.long_to_shorts.api.credits import refund_for_op
    from agents.long_to_shorts.api.publishing_store import publishing_store

    publishing_store.update(pub_id, status=PUB_FAILED, error=error)
    refund_for_op(user_id, "publish", key=f"refund:{pub_id}")


# ---------------------------------------------------------------------------
# Crash recovery (called from the app lifespan on startup)
# ---------------------------------------------------------------------------

def recover_publishing_jobs() -> int:
    """Re-enqueue every publishing job stuck in a resumable status (a worker/
    process died mid-step). Returns how many were re-enqueued. Best-effort."""
    try:
        from agents.long_to_shorts.api.publishing_store import publishing_store
        from core.execution import get_task_queue

        jobs = publishing_store.list_resumable()
        queue = get_task_queue()
        for job in jobs:
            owner = publishing_store.owner_of(job.publishing_job_id)
            queue.enqueue(run_publishing_step, job.publishing_job_id, owner)
        if jobs:
            logger.info("Re-enqueued %d in-flight publishing job(s) after restart.", len(jobs))
        return len(jobs)
    except Exception as exc:  # noqa: BLE001 — recovery must never crash startup
        logger.warning("Publishing crash-recovery sweep skipped: %s", exc)
        return 0


__all__ = ["run_publishing_step", "recover_publishing_jobs"]
