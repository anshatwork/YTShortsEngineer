"""
agents/long_to_shorts/api/routes.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
FastAPI router for the Long-to-Shorts API.

Endpoints
---------
    POST   /jobs             Submit a new clip job (returns 202 immediately)
    GET    /jobs/{job_id}    Poll status + results for a job
    GET    /jobs             List jobs for the authenticated user
"""

from __future__ import annotations

import logging
from typing import Optional

import fastapi
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from agents.long_to_shorts.api.auth import get_current_user_id
from agents.long_to_shorts.api.job_store import job_store
from agents.long_to_shorts.api.models import (
    JobListResponse,
    JobRequest,
    JobStatus,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# POST /jobs  —  submit a new job
# ---------------------------------------------------------------------------

@router.post(
    "/jobs",
    response_model=JobStatus,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit a new Long-to-Shorts clip job",
    description=(
        "Enqueues the pipeline in the background and returns a job record "
        "immediately. Poll **GET /jobs/{job_id}** for progress and results."
    ),
)
async def submit_job(
    body: JobRequest,
    http_request: Request,
    user_id: str = Depends(get_current_user_id),
) -> JobStatus:
    if not body.youtube_url and not body.video_path:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Provide either 'youtube_url' or 'video_path'.",
        )
    if body.youtube_url and body.video_path:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Provide EITHER 'youtube_url' OR 'video_path', not both.",
        )

    job = job_store.create(body, user_id=user_id)
    logger.info(
        "Job %s queued — user=%s source=%s",
        job.job_id, user_id, body.youtube_url or body.video_path,
    )

    from agents.long_to_shorts.api.runner import run_job  # late import (heavy deps)
    # Decoupled from the concrete executor: the TaskQueue abstraction lets this
    # move to Celery/Temporal later without touching routes (core/execution).
    http_request.app.state.task_queue.enqueue(run_job, job.job_id, body)

    return job


# ---------------------------------------------------------------------------
# POST /jobs/{job_id}/rerun  —  re-run a job with its original parameters
# ---------------------------------------------------------------------------

@router.post(
    "/jobs/{job_id}/rerun",
    response_model=JobStatus,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Re-run a job using its original submission parameters",
    description=(
        "Creates a NEW job from the original request of *job_id* (the failed "
        "job is preserved for debugging) and enqueues it. Returns the new job "
        "record; poll it like any other job."
    ),
)
async def rerun_job(
    job_id: str,
    http_request: Request,
    user_id: str = Depends(get_current_user_id),
) -> JobStatus:
    # Ownership + existence check.
    existing = job_store.get_for_user(job_id, user_id)
    if existing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found.",
        )

    original = job_store.get_request_for_user(job_id, user_id)
    if original is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Original parameters for this job are unavailable, so it cannot "
                "be re-run. Please submit a new job."
            ),
        )

    job = job_store.create(original, user_id=user_id)
    logger.info(
        "Job %s queued as rerun of %s — user=%s source=%s",
        job.job_id, job_id, user_id, original.youtube_url or original.video_path,
    )

    from agents.long_to_shorts.api.runner import run_job  # late import (heavy deps)
    http_request.app.state.task_queue.enqueue(run_job, job.job_id, original)

    return job


# ---------------------------------------------------------------------------
# GET /jobs/{job_id}  —  poll a single job
# ---------------------------------------------------------------------------

@router.get(
    "/jobs/{job_id}",
    response_model=JobStatus,
    summary="Get status and results for a job",
)
async def get_job(
    job_id: str,
    user_id: str = Depends(get_current_user_id),
) -> JobStatus:
    job = job_store.get_for_user(job_id, user_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found.",
        )
    if job.status == "failed":
        logger.warning(
            "Polled job %s — status=failed error=%s",
            job.job_id, (job.error or "")[:200],
        )
    return job


# ---------------------------------------------------------------------------
# GET /jobs  —  list jobs for the authenticated user
# ---------------------------------------------------------------------------

@router.get(
    "/jobs",
    response_model=JobListResponse,
    summary="List submitted jobs for the current user (most-recent first)",
)
async def list_jobs(
    user_id: str = Depends(get_current_user_id),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> JobListResponse:
    jobs = job_store.list_for_user(user_id, limit=limit, offset=offset)
    return JobListResponse(jobs=jobs, total=len(jobs))
