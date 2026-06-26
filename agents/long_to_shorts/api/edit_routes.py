"""
agents/long_to_shorts/api/edit_routes.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
FastAPI router for per-clip edit operations.

Endpoints (mounted at /api/v1/edit):
    POST   /tts                    Submit a TTS edit job (Chatterbox)
    POST   /add-music              Mix background music under an existing clip
    POST   /split-screen           Compose a 9:16 split-screen
    POST   /uploads                Store a user-supplied audio/video file
    GET    /jobs/{edit_job_id}     Poll a single edit job
    GET    /jobs                   List edit jobs for the current user
"""

from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status

from agents.long_to_shorts.api.auth import get_current_user_id
from agents.long_to_shorts.api.edit_job_store import edit_job_store
from agents.long_to_shorts.api.job_store import job_store
from agents.long_to_shorts.api.models import (
    EditJob,
    EditJobListResponse,
    MusicEditRequest,
    SplitScreenEditRequest,
    ThumbnailEditRequest,
    TtsScriptRequest,
    TtsScriptResponse,
    TTSEditRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# POST /edit/tts
# ---------------------------------------------------------------------------

@router.post(
    "/tts",
    response_model=EditJob,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Generate TTS narration via Chatterbox",
)
async def submit_tts(
    body: TTSEditRequest,
    http_request: Request,
    user_id: str = Depends(get_current_user_id),
) -> EditJob:
    # At most one "destination" mode may be chosen: attach-to-clip, or behind a
    # video (uploaded OR YouTube). With none, a standalone audio file is produced.
    modes = [
        bool(body.attach_to_clip_id),
        bool(body.video_upload_id),
        bool(body.video_url),
    ]
    if sum(modes) > 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Provide at most one of {attach_to_clip_id, video_upload_id, "
                "video_url}."
            ),
        )

    if body.attach_to_clip_id:
        if not body.parent_job_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="attach_to_clip_id requires parent_job_id.",
            )
        clip = job_store.get_clip_for_user(
            body.parent_job_id, body.attach_to_clip_id, user_id
        )
        if clip is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(
                    f"Clip '{body.attach_to_clip_id}' not found under job "
                    f"'{body.parent_job_id}'."
                ),
            )

    edit_job = edit_job_store.create(
        "tts",
        user_id=user_id,
        parent_job_id=body.parent_job_id,
        clip_id=body.attach_to_clip_id,
    )
    logger.info(
        "Edit job %s queued — op=tts preset=%s attach=%s user=%s",
        edit_job.edit_job_id, body.voice_preset, body.attach_to_clip_id, user_id,
    )

    from agents.long_to_shorts.api.edit_runner import run_tts_edit_job
    http_request.app.state.task_queue.enqueue(
        run_tts_edit_job, edit_job.edit_job_id, body
    )
    return edit_job


# ---------------------------------------------------------------------------
# POST /edit/tts/script  (synchronous — expand a summary into a narration script)
# ---------------------------------------------------------------------------

@router.post(
    "/tts/script",
    response_model=TtsScriptResponse,
    summary="Generate a narration script from a summary (Claude/Qwen) for TTS",
)
async def submit_tts_script(
    body: TtsScriptRequest,
    user_id: str = Depends(get_current_user_id),
) -> TtsScriptResponse:
    from agents.long_to_shorts.api.edit_runner import generate_tts_script

    try:
        script = generate_tts_script(
            body.summary, target_seconds=body.target_seconds, tone=body.tone
        )
    except Exception as exc:  # noqa: BLE001 — surface LLM/provider failures cleanly
        logger.exception("TTS script generation failed for user %s: %s", user_id, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Script generation failed: {exc}",
        )

    if not script:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Script generation returned empty text.",
        )
    return TtsScriptResponse(script=script)


# ---------------------------------------------------------------------------
# POST /edit/add-music
# ---------------------------------------------------------------------------

@router.post(
    "/add-music",
    response_model=EditJob,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Mix background music under an existing clip",
)
async def submit_music(
    body: MusicEditRequest,
    http_request: Request,
    user_id: str = Depends(get_current_user_id),
) -> EditJob:
    sources = [bool(body.theme), bool(body.music_path), bool(body.music_upload_id)]
    if sum(sources) != 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Provide exactly one of {theme, music_path, music_upload_id}.",
        )

    clip = job_store.get_clip_for_user(body.parent_job_id, body.clip_id, user_id)
    if clip is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Clip '{body.clip_id}' not found under job "
                f"'{body.parent_job_id}'."
            ),
        )

    edit_job = edit_job_store.create(
        "music",
        user_id=user_id,
        parent_job_id=body.parent_job_id,
        clip_id=body.clip_id,
    )
    logger.info(
        "Edit job %s queued — op=music vol=%.1f dB user=%s",
        edit_job.edit_job_id, body.volume_db, user_id,
    )

    from agents.long_to_shorts.api.edit_runner import run_music_edit_job
    http_request.app.state.task_queue.enqueue(
        run_music_edit_job, edit_job.edit_job_id, body
    )
    return edit_job


# ---------------------------------------------------------------------------
# POST /edit/generate-thumbnail
# ---------------------------------------------------------------------------

@router.post(
    "/generate-thumbnail",
    response_model=EditJob,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Generate an AI-directed thumbnail image for an existing clip",
)
async def submit_thumbnail(
    body: ThumbnailEditRequest,
    http_request: Request,
    user_id: str = Depends(get_current_user_id),
) -> EditJob:
    clip = job_store.get_clip_for_user(body.parent_job_id, body.clip_id, user_id)
    if clip is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Clip '{body.clip_id}' not found under job "
                f"'{body.parent_job_id}'."
            ),
        )

    edit_job = edit_job_store.create(
        "thumbnail",
        user_id=user_id,
        parent_job_id=body.parent_job_id,
        clip_id=body.clip_id,
    )
    logger.info(
        "Edit job %s queued — op=thumbnail clip=%s user=%s",
        edit_job.edit_job_id, body.clip_id, user_id,
    )

    from agents.long_to_shorts.api.edit_runner import run_thumbnail_edit_job
    http_request.app.state.task_queue.enqueue(
        run_thumbnail_edit_job, edit_job.edit_job_id, body
    )
    return edit_job


# ---------------------------------------------------------------------------
# POST /edit/split-screen
# ---------------------------------------------------------------------------

@router.post(
    "/split-screen",
    response_model=EditJob,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Compose a 9:16 split-screen of an existing clip + a background",
)
async def submit_split_screen(
    body: SplitScreenEditRequest,
    http_request: Request,
    user_id: str = Depends(get_current_user_id),
) -> EditJob:
    sources = [
        bool(body.background_default),
        bool(body.background_path),
        bool(body.background_url),
        bool(body.background_upload_id),
    ]
    if sum(sources) != 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Provide exactly one of {background_default, background_path, "
                "background_url, background_upload_id}."
            ),
        )

    # Foreground (top half): standalone upload, OR an existing clip — exactly one.
    has_clip = bool(body.parent_job_id and body.clip_id)
    if bool(body.foreground_upload_id) == has_clip:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Provide either foreground_upload_id (standalone) or both "
                "parent_job_id and clip_id (from an existing clip), not both/neither."
            ),
        )

    if has_clip:
        clip = job_store.get_clip_for_user(body.parent_job_id, body.clip_id, user_id)
        if clip is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(
                    f"Clip '{body.clip_id}' not found under job "
                    f"'{body.parent_job_id}'."
                ),
            )

    edit_job = edit_job_store.create(
        "split_screen",
        user_id=user_id,
        parent_job_id=body.parent_job_id,
        clip_id=body.clip_id,
    )
    logger.info(
        "Edit job %s queued — op=split_screen audio_mode=%s user=%s",
        edit_job.edit_job_id, body.audio_mode, user_id,
    )

    from agents.long_to_shorts.api.edit_runner import run_split_screen_edit_job
    http_request.app.state.task_queue.enqueue(
        run_split_screen_edit_job, edit_job.edit_job_id, body
    )
    return edit_job


# ---------------------------------------------------------------------------
# POST /edit/uploads
# ---------------------------------------------------------------------------

_ALLOWED_UPLOAD_EXTS = {".mp3", ".wav", ".m4a", ".ogg", ".mp4", ".mov", ".webm", ".srt"}


@router.post(
    "/uploads",
    summary="Upload an audio or video file for use in subsequent edit jobs",
)
async def upload_asset(
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user_id),
) -> dict:
    ext = Path(file.filename or "").suffix.lower()
    if ext not in _ALLOWED_UPLOAD_EXTS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Unsupported extension '{ext}'. "
                f"Allowed: {sorted(_ALLOWED_UPLOAD_EXTS)}"
            ),
        )

    upload_dir = Path(os.getenv("UPLOAD_DIR", "assets/uploads")).resolve()
    upload_dir.mkdir(parents=True, exist_ok=True)
    upload_id = f"{uuid.uuid4()}{ext}"
    dest = upload_dir / upload_id

    with dest.open("wb") as fh:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            fh.write(chunk)

    logger.info("Upload stored: %s (%d bytes) user=%s", dest, dest.stat().st_size, user_id)

    # Register in the uploads table when using Supabase backend
    if os.getenv("JOB_STORE", "memory").lower() == "supabase":
        try:
            from agents.long_to_shorts.api.supabase_client import get_worker_client
            get_worker_client().table("uploads").insert({
                "upload_id": upload_id,
                "user_id": user_id,
                "path": str(dest),
                "size": dest.stat().st_size,
            }).execute()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to register upload in DB: %s", exc)

    return {
        "upload_id": upload_id,
        "path": str(dest),
        "size": dest.stat().st_size,
    }


# ---------------------------------------------------------------------------
# GET /edit/jobs/{edit_job_id}
# ---------------------------------------------------------------------------

@router.get(
    "/jobs/{edit_job_id}",
    response_model=EditJob,
    summary="Get status and output for an edit job",
)
async def get_edit_job(
    edit_job_id: str,
    user_id: str = Depends(get_current_user_id),
) -> EditJob:
    job = edit_job_store.get_for_user(edit_job_id, user_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Edit job '{edit_job_id}' not found.",
        )
    if job.status == "failed":
        logger.warning(
            "Polled edit job %s — status=failed error=%s",
            job.edit_job_id, (job.error or "")[:200],
        )
    return job


# ---------------------------------------------------------------------------
# GET /edit/jobs
# ---------------------------------------------------------------------------

@router.get(
    "/jobs",
    response_model=EditJobListResponse,
    summary="List edit jobs for the current user (most-recent first)",
)
async def list_edit_jobs(
    user_id: str = Depends(get_current_user_id),
    parent_job_id: Optional[str] = None,
    clip_id: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> EditJobListResponse:
    jobs = edit_job_store.list_for_user(
        user_id,
        parent_job_id=parent_job_id,
        clip_id=clip_id,
        limit=limit,
        offset=offset,
    )
    return EditJobListResponse(edit_jobs=jobs, total=len(jobs))
