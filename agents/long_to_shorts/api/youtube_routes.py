"""
agents/long_to_shorts/api/youtube_routes.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
FastAPI router for YouTube direct upload (mounted at /api/v1/youtube).

Endpoints
---------
    GET    /auth/status          Is the current user's YouTube connected?
    GET    /auth/login           Begin the Connect-YouTube OAuth flow
    GET    /auth/callback        OAuth redirect target (public; trusts signed state)
    DELETE /auth                 Disconnect YouTube (delete stored credentials)
    POST   /upload               Publish a clip (async; returns 202)
    GET    /uploads/{upload_id}  Poll a single upload job
    GET    /uploads              List upload jobs for the current user
"""

from __future__ import annotations

import logging
import os
from typing import Optional
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse

from agents.long_to_shorts.api.auth import get_current_user_id
from agents.long_to_shorts.api.job_store import job_store
from agents.long_to_shorts.api.models import (
    YouTubeAuthStatus,
    YouTubeUploadJob,
    YouTubeUploadListResponse,
    YouTubeUploadRequest,
)
from agents.long_to_shorts.api.youtube_credentials_store import (
    youtube_credentials_store,
)
from agents.long_to_shorts.api.youtube_upload_store import youtube_upload_store
from agents.long_to_shorts.api import youtube_oauth as oauth

logger = logging.getLogger(__name__)

router = APIRouter()


def _frontend_base() -> str:
    """First configured frontend origin (FRONTEND_URL may be a CSV or '*')."""
    raw = os.getenv("FRONTEND_URL", "http://localhost:3000")
    if raw == "*":
        return "http://localhost:3000"
    return raw.split(",")[0].strip().rstrip("/")


# ---------------------------------------------------------------------------
# Auth — status / connect / callback / disconnect
# ---------------------------------------------------------------------------

@router.get(
    "/auth/status",
    response_model=YouTubeAuthStatus,
    summary="Whether the current user has connected a YouTube account",
)
async def auth_status(
    user_id: str = Depends(get_current_user_id),
) -> YouTubeAuthStatus:
    record = youtube_credentials_store.get(user_id)
    if not record or not record.get("refresh_token"):
        return YouTubeAuthStatus(connected=False)
    return YouTubeAuthStatus(
        connected=True,
        channel_id=record.get("channel_id"),
        channel_title=record.get("channel_title"),
    )


@router.get(
    "/auth/login",
    summary="Get the Google consent URL to connect a YouTube account",
)
async def auth_login(user_id: str = Depends(get_current_user_id)) -> dict:
    if not oauth.is_configured():
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=(
                "YouTube upload is not configured on the server "
                "(GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET missing)."
            ),
        )
    state = oauth.sign_state(user_id)
    return {"authorization_url": oauth.build_authorization_url(state)}


@router.get(
    "/auth/callback",
    summary="OAuth redirect target — exchanges the code and stores credentials",
    include_in_schema=False,
)
async def auth_callback(
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
):
    """Public endpoint hit by Google. Trusts the signed *state* for identity."""
    frontend = _frontend_base()

    def _redirect(result: str) -> RedirectResponse:
        return RedirectResponse(url=f"{frontend}/?{urlencode({'youtube': result})}")

    if error or not code or not state:
        logger.warning("YouTube OAuth callback error=%s (code/state present=%s/%s)",
                       error, bool(code), bool(state))
        return _redirect("error")

    try:
        user_id = oauth.verify_state(state)
    except Exception as exc:  # noqa: BLE001
        logger.warning("YouTube OAuth callback — invalid state: %s", exc)
        return _redirect("error")

    try:
        creds = oauth.exchange_code(code)
        channel_id, channel_title = oauth.fetch_channel_info(creds)
        youtube_credentials_store.upsert(
            user_id,
            refresh_token=creds.refresh_token,
            access_token=creds.token,
            token_expiry=oauth._to_aware_utc(creds.expiry),
            channel_id=channel_id,
            channel_title=channel_title,
            scopes=" ".join(creds.scopes or oauth.SCOPES),
        )
        logger.info("YouTube connected — user=%s channel=%s", user_id, channel_title)
        return _redirect("connected")
    except Exception as exc:  # noqa: BLE001
        logger.exception("YouTube OAuth callback — token exchange failed: %s", exc)
        return _redirect("error")


@router.delete(
    "/auth",
    summary="Disconnect YouTube (delete stored credentials)",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def auth_disconnect(user_id: str = Depends(get_current_user_id)) -> None:
    youtube_credentials_store.delete(user_id)
    logger.info("YouTube disconnected — user=%s", user_id)


# ---------------------------------------------------------------------------
# Upload — submit / poll / list
# ---------------------------------------------------------------------------

@router.post(
    "/upload",
    response_model=YouTubeUploadJob,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Publish an existing clip to YouTube (async)",
)
async def submit_upload(
    body: YouTubeUploadRequest,
    http_request: Request,
    user_id: str = Depends(get_current_user_id),
) -> YouTubeUploadJob:
    # Must have a connected account first.
    record = youtube_credentials_store.get(user_id)
    if not record or not record.get("refresh_token"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="YouTube not connected. Connect a YouTube account first.",
        )

    # Clip must exist and belong to the caller.
    clip = job_store.get_clip_for_user(body.parent_job_id, body.clip_id, user_id)
    if clip is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Clip '{body.clip_id}' not found under job "
                f"'{body.parent_job_id}'."
            ),
        )
    if not clip.path:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Clip has no rendered file to upload yet.",
        )

    upload_job = youtube_upload_store.create(
        user_id=user_id,
        parent_job_id=body.parent_job_id,
        clip_id=body.clip_id,
        title=body.title,
        privacy_status=body.privacy_status,
    )
    logger.info(
        "YouTube upload %s queued — clip=%s/%s user=%s",
        upload_job.upload_id, body.parent_job_id, body.clip_id, user_id,
    )

    from agents.long_to_shorts.api.youtube_upload_runner import run_youtube_upload_job
    http_request.app.state.executor.submit(
        run_youtube_upload_job, upload_job.upload_id, body, user_id
    )
    return upload_job


@router.get(
    "/uploads/{upload_id}",
    response_model=YouTubeUploadJob,
    summary="Get status and result for an upload job",
)
async def get_upload(
    upload_id: str,
    user_id: str = Depends(get_current_user_id),
) -> YouTubeUploadJob:
    job = youtube_upload_store.get_for_user(upload_id, user_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Upload job '{upload_id}' not found.",
        )
    return job


@router.get(
    "/uploads",
    response_model=YouTubeUploadListResponse,
    summary="List upload jobs for the current user (most-recent first)",
)
async def list_uploads(
    user_id: str = Depends(get_current_user_id),
    parent_job_id: Optional[str] = None,
    clip_id: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> YouTubeUploadListResponse:
    uploads = youtube_upload_store.list_for_user(
        user_id,
        parent_job_id=parent_job_id,
        clip_id=clip_id,
        limit=limit,
        offset=offset,
    )
    return YouTubeUploadListResponse(uploads=uploads, total=len(uploads))
