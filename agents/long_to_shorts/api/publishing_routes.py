"""
agents/long_to_shorts/api/publishing_routes.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
FastAPI router for the Autonomous Publishing Agent (mounted at /api/v1).

The human makes exactly two decisions; everything else is autonomous:

    POST /publishing                     Start a run (returns 202, status=discovering)
    GET  /publishing                     List the caller's runs
    GET  /publishing/{id}                Poll one run (candidates, selected clip, eval)
    POST /publishing/{id}/approve-source Human decision #1 (approve/reject/refresh)
    POST /publishing/{id}/approve-upload Human decision #2 (approve/reject/regenerate/edit)
    GET  /publishing/metrics             Inference scheduler + workflow observability

Live progress streams over SSE at /publishing/{id}/events (events_routes.py).
Each mutating endpoint validates the transition via the pure orchestrator, meters
credits at start, and enqueues the next self-contained step on the task queue.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status

from agents.long_to_shorts.api.auth import get_current_user_id
from agents.long_to_shorts.api.models import (
    ApproveSourceRequest,
    ApproveUploadRequest,
    PublishingJob,
    PublishingJobListResponse,
    PublishingReviewRequest,
    PublishingStartRequest,
)
from agents.long_to_shorts.api.publishing_orchestrator import (
    InvalidTransition,
    resolve_source_action,
    resolve_upload_action,
)
from agents.long_to_shorts.api.publishing_store import publishing_store

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_owned(publishing_job_id: str, user_id: str) -> PublishingJob:
    job = publishing_store.get_for_user(publishing_job_id, user_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Publishing job '{publishing_job_id}' not found.",
        )
    return job


# ---------------------------------------------------------------------------
# Start
# ---------------------------------------------------------------------------

@router.post(
    "/publishing",
    response_model=PublishingJob,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start an autonomous publishing run",
)
async def start_publishing(
    body: PublishingStartRequest,
    http_request: Request,
    user_id: str = Depends(get_current_user_id),
) -> PublishingJob:
    from agents.long_to_shorts.api.credits import enforce_and_debit

    enforce_and_debit(user_id, "publish")  # 402 if short; fails open on ledger error

    job = publishing_store.create(body, user_id=user_id)
    logger.info("Publishing %s started — user=%s query=%r", job.publishing_job_id, user_id, body.query)

    from agents.long_to_shorts.api.publishing_runner import run_publishing_step
    http_request.app.state.task_queue.enqueue(run_publishing_step, job.publishing_job_id, user_id)
    return job


# ---------------------------------------------------------------------------
# Poll / list
# ---------------------------------------------------------------------------

@router.get("/publishing/metrics", summary="Inference scheduler + workflow observability")
async def publishing_metrics(user_id: str = Depends(get_current_user_id)) -> dict:
    from agents.long_to_shorts.api.youtube_service import get_youtube_service
    from core.inference import get_scheduler

    sched = get_scheduler().metrics()
    return {
        "inference": sched,
        "youtube_quota_remaining": get_youtube_service().quota_remaining(),
        "youtube_quota_used": get_youtube_service().quota_used(),
    }


@router.get("/publishing", response_model=PublishingJobListResponse, summary="List publishing runs")
async def list_publishing(
    user_id: str = Depends(get_current_user_id),
    limit: int = 100,
    offset: int = 0,
) -> PublishingJobListResponse:
    jobs = publishing_store.list_for_user(user_id, limit=limit, offset=offset)
    return PublishingJobListResponse(jobs=jobs, total=len(jobs))


@router.get("/publishing/{publishing_job_id}", response_model=PublishingJob, summary="Poll a publishing run")
async def get_publishing(
    publishing_job_id: str,
    user_id: str = Depends(get_current_user_id),
) -> PublishingJob:
    return _get_owned(publishing_job_id, user_id)


# ---------------------------------------------------------------------------
# Human decision #1 — approve the source video
# ---------------------------------------------------------------------------

@router.post(
    "/publishing/{publishing_job_id}/approve-source",
    response_model=PublishingJob,
    summary="Approve / reject / refresh the discovered source video",
)
async def approve_source(
    publishing_job_id: str,
    body: ApproveSourceRequest,
    http_request: Request,
    user_id: str = Depends(get_current_user_id),
) -> PublishingJob:
    job = _get_owned(publishing_job_id, user_id)
    try:
        target = resolve_source_action(job.status, body.action, body.video_url)
    except InvalidTransition as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))

    fields = {"status": target}
    if body.action == "approve":
        fields["approved_video_url"] = body.video_url
        fields["phase_detail"] = "source approved — generating clips"
    elif body.action == "refresh":
        fields["phase_detail"] = "refreshing candidates"
    else:  # reject
        fields["phase_detail"] = "rejected by user"

    updated = publishing_store.update(publishing_job_id, **fields)

    # Approve → generate; refresh → re-discover. Both enqueue the next step.
    if body.action in ("approve", "refresh"):
        from agents.long_to_shorts.api.publishing_runner import run_publishing_step
        http_request.app.state.task_queue.enqueue(run_publishing_step, publishing_job_id, user_id)
    return updated


# ---------------------------------------------------------------------------
# Human decision #2 — approve the upload
# ---------------------------------------------------------------------------

@router.post(
    "/publishing/{publishing_job_id}/approve-upload",
    response_model=PublishingJob,
    summary="Approve / reject / regenerate / edit-metadata at the upload gate",
)
async def approve_upload(
    publishing_job_id: str,
    body: ApproveUploadRequest,
    http_request: Request,
    user_id: str = Depends(get_current_user_id),
) -> PublishingJob:
    job = _get_owned(publishing_job_id, user_id)
    try:
        target = resolve_upload_action(job.status, body.action)
    except InvalidTransition as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))

    if body.action == "select_clip":
        if not body.clip_id or not job.generated_clips:
            raise HTTPException(status_code=422, detail="select_clip requires a generated clip_id.")
        selected = next((c for c in job.generated_clips if c.clip_id == body.clip_id), None)
        if selected is None:
            raise HTTPException(status_code=404, detail="Clip not found in this publishing run.")
        return publishing_store.update(
            publishing_job_id, selected_clip_id=selected.clip_id,
            selected_clip=selected, phase_detail="clip selected - ready to publish",
        )

    # edit_metadata patches the selected clip in place and stays at the gate.
    if body.action == "edit_metadata":
        if not body.metadata or job.selected_clip is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="edit_metadata requires 'metadata' and a selected clip.",
            )
        clip = job.selected_clip.model_copy(update={
            k: v for k, v in {
                "title": body.metadata.title,
                "summary": body.metadata.description,
                "hashtags": body.metadata.hashtags,
            }.items() if v is not None
        })
        return publishing_store.update(
            publishing_job_id, selected_clip=clip, phase_detail="metadata edited",
        )

    fields = {"status": target}
    if body.action == "approve":
        fields.update({
            "upload_privacy_status": body.privacy_status,
            "upload_category_id": body.category_id,
            "upload_tags": body.tags,
        })
    if body.action == "regenerate":
        # status → generating; the runner regenerates fresh whenever status is
        # 'generating' (it only reloads existing clips on crash-recovery mid-review).
        fields["phase_detail"] = "regenerating clips"
    elif body.action == "reject":
        fields["phase_detail"] = "upload rejected by user"
    else:  # approve
        fields["phase_detail"] = "uploading to YouTube"

    updated = publishing_store.update(publishing_job_id, **fields)

    if body.action in ("approve", "regenerate"):
        from agents.long_to_shorts.api.publishing_runner import run_publishing_step
        http_request.app.state.task_queue.enqueue(run_publishing_step, publishing_job_id, user_id)
    return updated


@router.post(
    "/publishing/{publishing_job_id}/review",
    response_model=PublishingJob,
    summary="Submit structured instructions after reviewing source context",
)
async def review_publishing(
    publishing_job_id: str,
    body: PublishingReviewRequest,
    http_request: Request,
    user_id: str = Depends(get_current_user_id),
) -> PublishingJob:
    job = _get_owned(publishing_job_id, user_id)
    if job.status not in ("waiting_for_context_review", "waiting_for_upload_approval"):
        raise HTTPException(status_code=409, detail="Context review is not available in the current state.")
    request = publishing_store.get_request_for_user(publishing_job_id, user_id)
    if request is None:
        raise HTTPException(status_code=409, detail="Original publishing request is unavailable.")
    request = request.model_copy(update=body.model_dump(exclude_none=True, exclude={"regenerate"}))
    publishing_store.update_request(publishing_job_id, request)
    if not body.regenerate:
        return publishing_store.update(publishing_job_id, phase_detail="context reviewed")
    updated = publishing_store.update(
        publishing_job_id, status="generating",
        phase_detail="generating clips from reviewed source",
    )
    from agents.long_to_shorts.api.publishing_runner import run_publishing_step
    http_request.app.state.task_queue.enqueue(run_publishing_step, publishing_job_id, user_id)
    return updated


__all__ = ["router"]
