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

from core.logging_config import job_log_scope

logger = logging.getLogger(__name__)

_WATCH_URL = "https://www.youtube.com/watch?v={video_id}"


def _persist_done_with_retry(store, upload_id, *, video_id, video_url, attempts=3):
    """Persist the completed-upload result, retrying transient store failures."""
    import time as _time

    last_exc = None
    for i in range(attempts):
        try:
            store.update(upload_id, status="done", video_id=video_id, video_url=video_url)
            return
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            logger.warning(
                "[yt-upload:%s] persist attempt %d/%d failed: %s",
                upload_id, i + 1, attempts, exc,
            )
            _time.sleep(2 ** i)
    # Out of retries: re-raise so the outer handler records a failure. The video
    # is live but unpersisted — the idempotency_key guards against re-upload.
    raise RuntimeError(
        f"YouTube upload {upload_id} succeeded (video {video_id}) but the result "
        f"could not be persisted after {attempts} attempts."
    ) from last_exc


@job_log_scope
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

        # ── Idempotency guard (Part 3) ───────────────────────────────────────
        # Derive a deterministic key for this logical upload. If an equivalent
        # upload already completed (e.g. this is a retry after a crash, or a
        # duplicate submission), reconcile to the existing video instead of
        # publishing it to YouTube a second time.
        from core.cache.keys import file_signature, make_key

        idem_key = make_key(
            "yt_upload", 1,
            {
                "user": user_id,
                "clip": file_signature(clip_path),
                "title": request.title,
                "privacy": request.privacy_status,
            },
        )
        try:
            youtube_upload_store.set_idempotency_key(upload_id, idem_key)
            prior = youtube_upload_store.find_completed_by_idempotency(
                user_id, idem_key, exclude_upload_id=upload_id
            )
        except Exception:  # noqa: BLE001 — idempotency is best-effort, never fatal
            prior = None
        if prior is not None and prior.video_id:
            logger.warning(
                "[yt-upload:%s] equivalent upload already on YouTube (%s); "
                "reconciling without re-uploading.", upload_id, prior.video_url,
            )
            youtube_upload_store.update(
                upload_id, status="done",
                video_id=prior.video_id, video_url=prior.video_url,
            )
            return

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
        # The video is now live. Persist the result, retrying a few times so a
        # transient DB blip doesn't strand us in 'running' (which would let a
        # retry re-upload). The idempotency_key already on this row lets a future
        # channel-side reconciliation recover from a hard crash in this window.
        _persist_done_with_retry(
            youtube_upload_store, upload_id, video_id=video_id, video_url=video_url
        )
        logger.info("[yt-upload:%s] done — %s", upload_id, video_url)

    except Exception as exc:  # noqa: BLE001 — record any failure on the job
        logger.exception("[yt-upload:%s] failed", upload_id)
        youtube_upload_store.update(upload_id, status="failed", error=str(exc))


__all__ = ["run_youtube_upload_job"]
