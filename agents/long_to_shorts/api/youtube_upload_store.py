"""
agents/long_to_shorts/api/youtube_upload_store.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Store for YouTube upload jobs — mirrors edit_job_store.py.

Backend selected by JOB_STORE:
  JOB_STORE=supabase  →  SupabaseYouTubeUploadStore  (youtube_uploads table)
  JOB_STORE=memory    →  _MemoryYouTubeUploadStore   (default)

Lifecycle: queued → running → done | failed.
"""

from __future__ import annotations

import os
import threading
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from typing import Dict, List, Optional

from agents.long_to_shorts.api.models import YouTubeUploadJob


class _MemoryYouTubeUploadStore:
    """Thread-safe in-memory store for upload-job records."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: Dict[str, YouTubeUploadJob] = {}

    def create(
        self,
        *,
        user_id: str = "dev",
        parent_job_id: Optional[str] = None,
        clip_id: Optional[str] = None,
        title: Optional[str] = None,
        privacy_status: Optional[str] = None,
    ) -> YouTubeUploadJob:
        now = datetime.now(tz=timezone.utc)
        job = YouTubeUploadJob(
            upload_id=str(uuid.uuid4()),
            parent_job_id=parent_job_id,
            clip_id=clip_id,
            status="queued",
            created_at=now,
            updated_at=now,
            title=title,
            privacy_status=privacy_status,
        )
        with self._lock:
            self._jobs[job.upload_id] = job
        return job

    def update(
        self,
        upload_id: str,
        *,
        status: Optional[str] = None,
        video_id: Optional[str] = None,
        video_url: Optional[str] = None,
        error: Optional[str] = None,
    ) -> Optional[YouTubeUploadJob]:
        with self._lock:
            job = self._jobs.get(upload_id)
            if job is None:
                return None
            updates: dict = {"updated_at": datetime.now(tz=timezone.utc)}
            if status is not None:
                updates["status"] = status
            if video_id is not None:
                updates["video_id"] = video_id
            if video_url is not None:
                updates["video_url"] = video_url
            if error is not None:
                updates["error"] = error
            updated = job.model_copy(update=updates)
            self._jobs[upload_id] = updated
            return updated

    def get(self, upload_id: str) -> Optional[YouTubeUploadJob]:
        with self._lock:
            job = self._jobs.get(upload_id)
            return deepcopy(job) if job else None

    def get_for_user(self, upload_id: str, user_id: str) -> Optional[YouTubeUploadJob]:
        return self.get(upload_id)

    def list_for_user(
        self,
        user_id: str,
        *,
        parent_job_id: Optional[str] = None,
        clip_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[YouTubeUploadJob]:
        with self._lock:
            records = list(self._jobs.values())
        if parent_job_id is not None:
            records = [r for r in records if r.parent_job_id == parent_job_id]
        if clip_id is not None:
            records = [r for r in records if r.clip_id == clip_id]
        records.sort(key=lambda j: j.created_at, reverse=True)
        return [deepcopy(r) for r in records[offset : offset + limit]]


def _make_youtube_upload_store():
    backend = os.getenv("JOB_STORE", "memory").lower()
    if backend == "supabase":
        from agents.long_to_shorts.api.db.youtube_upload_store import (
            supabase_youtube_upload_store,
        )
        return supabase_youtube_upload_store
    return _MemoryYouTubeUploadStore()


youtube_upload_store = _make_youtube_upload_store()

__all__ = ["youtube_upload_store"]
