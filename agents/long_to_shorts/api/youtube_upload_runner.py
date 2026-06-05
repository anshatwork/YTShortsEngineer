"""
agents/long_to_shorts/api/youtube_upload_runner.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Background worker that publishes an existing clip to YouTube.

Lifecycle (mirrors edit_runner.py):  queued → running → done | failed

The clip's rendered file is resolved from the clip job store; the upload is a
resumable ``youtube.videos().insert`` driven to completion. Heavy Google libs
are imported inside the function to keep module load cheap.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agents.long_to_shorts.api.models import YouTubeUploadRequest

logger = logging.getLogger(__name__)

_WATCH_URL = "https://www.youtube.com/watch?v={video_id}"


def run_youtube_upload_job(
    upload_id: str,
    request: "YouTubeUploadRequest",
    user_id: str,
) -> None:
    """Execute a single YouTube upload job and persist the result."""
    from agents.long_to_shorts.api.youtube_upload_store import youtube_upload_store

    youtube_upload_store.update(upload_id, status="running")
    logger.info(
        "[yt-upload:%s] started — clip=%s/%s privacy=%s user=%s",
        upload_id, request.parent_job_id, request.clip_id,
        request.privacy_status, user_id,
    )

    try:
        from agents.long_to_shorts.api.job_store import job_store

        clip = job_store.get_clip_for_user(
            request.parent_job_id, request.clip_id, user_id
        )
        if clip is None or not clip.path:
            raise ValueError(
                f"Clip '{request.clip_id}' not found under job "
                f"'{request.parent_job_id}', or it has no file path."
            )
        clip_path = Path(clip.path)
        if not clip_path.exists():
            raise FileNotFoundError(f"Clip file missing on disk: {clip_path}")

        from agents.long_to_shorts.api.youtube_oauth import get_authenticated_youtube
        from googleapiclient.http import MediaFileUpload

        youtube = get_authenticated_youtube(user_id)

        body = {
            "snippet": {
                "title": request.title,
                "description": request.description,
                "tags": request.tags,
                "categoryId": request.category_id,
            },
            "status": {
                "privacyStatus": request.privacy_status,
                "selfDeclaredMadeForKids": request.made_for_kids,
            },
        }

        media = MediaFileUpload(str(clip_path), chunksize=-1, resumable=True)
        insert_request = youtube.videos().insert(
            part="snippet,status", body=body, media_body=media
        )

        response = None
        while response is None:
            _status, response = insert_request.next_chunk()

        video_id = response["id"]
        video_url = _WATCH_URL.format(video_id=video_id)
        youtube_upload_store.update(
            upload_id, status="done", video_id=video_id, video_url=video_url
        )
        logger.info("[yt-upload:%s] done — %s", upload_id, video_url)

    except Exception as exc:  # noqa: BLE001 — record any failure on the job
        logger.exception("[yt-upload:%s] failed", upload_id)
        youtube_upload_store.update(upload_id, status="failed", error=str(exc))


__all__ = ["run_youtube_upload_job"]
