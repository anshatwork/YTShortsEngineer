"""
agents/long_to_shorts/api/db/youtube_upload_store.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Supabase-backed implementation of the YouTube upload-job store.

Mirrors the in-memory store interface. Workers use the service-role client;
route handlers pass user_id from the verified JWT for ownership checks.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from agents.long_to_shorts.api.db.mappers import (
    row_to_youtube_upload,
    youtube_upload_to_insert,
    youtube_upload_to_update,
)
from agents.long_to_shorts.api.models import YouTubeUploadJob
from agents.long_to_shorts.api.supabase_client import get_worker_client

logger = logging.getLogger(__name__)

_TABLE = "youtube_uploads"


class SupabaseYouTubeUploadStore:
    """Supabase-backed store for YouTube upload jobs."""

    def create(
        self,
        *,
        user_id: str,
        parent_job_id: Optional[str] = None,
        clip_id: Optional[str] = None,
        title: Optional[str] = None,
        privacy_status: Optional[str] = None,
    ) -> YouTubeUploadJob:
        upload_id = str(uuid.uuid4())
        now = datetime.now(tz=timezone.utc)
        row = youtube_upload_to_insert(
            upload_id,
            user_id,
            parent_job_id=parent_job_id,
            clip_id=clip_id,
            title=title,
            privacy_status=privacy_status,
        )
        client = get_worker_client()
        result = client.table(_TABLE).insert(row).execute()
        data = result.data
        if data:
            return row_to_youtube_upload(data[0])
        return YouTubeUploadJob(
            upload_id=upload_id,
            parent_job_id=parent_job_id,
            clip_id=clip_id,
            status="queued",
            created_at=now,
            updated_at=now,
            title=title,
            privacy_status=privacy_status,
        )

    def update(
        self,
        upload_id: str,
        *,
        status: Optional[str] = None,
        video_id: Optional[str] = None,
        video_url: Optional[str] = None,
        error: Optional[str] = None,
    ) -> Optional[YouTubeUploadJob]:
        patch = youtube_upload_to_update(
            status=status,
            video_id=video_id,
            video_url=video_url,
            error=error,
        )
        if not patch:
            return self.get(upload_id)
        client = get_worker_client()
        result = (
            client.table(_TABLE)
            .update(patch)
            .eq("upload_id", upload_id)
            .execute()
        )
        data = result.data
        if data:
            return row_to_youtube_upload(data[0])
        return None

    def get(self, upload_id: str) -> Optional[YouTubeUploadJob]:
        client = get_worker_client()
        result = (
            client.table(_TABLE)
            .select("*")
            .eq("upload_id", upload_id)
            .limit(1)
            .execute()
        )
        data = result.data
        if not data:
            return None
        return row_to_youtube_upload(data[0])

    def get_for_user(self, upload_id: str, user_id: str) -> Optional[YouTubeUploadJob]:
        client = get_worker_client()
        result = (
            client.table(_TABLE)
            .select("*")
            .eq("upload_id", upload_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        data = result.data
        if not data:
            return None
        return row_to_youtube_upload(data[0])

    def list_for_user(
        self,
        user_id: str,
        *,
        parent_job_id: Optional[str] = None,
        clip_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[YouTubeUploadJob]:
        client = get_worker_client()
        query = client.table(_TABLE).select("*").eq("user_id", user_id)
        if parent_job_id is not None:
            query = query.eq("parent_job_id", parent_job_id)
        if clip_id is not None:
            query = query.eq("clip_id", clip_id)
        result = (
            query.order("created_at", desc=True)
            .range(offset, offset + limit - 1)
            .execute()
        )
        return [row_to_youtube_upload(row) for row in (result.data or [])]


supabase_youtube_upload_store = SupabaseYouTubeUploadStore()

__all__ = ["SupabaseYouTubeUploadStore", "supabase_youtube_upload_store"]
