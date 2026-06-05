"""
agents/long_to_shorts/api/job_store.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Thread-safe job registry — in-memory implementation.

This module still exports `job_store`, but the active backend depends on the
JOB_STORE environment variable:

  JOB_STORE=supabase  →  SupabaseJobStore  (requires SUPABASE_* env vars)
  JOB_STORE=memory    →  _MemoryJobStore   (default; no external deps)

Usage
-----
    from agents.long_to_shorts.api.job_store import job_store

    record = job_store.create(request, user_id="...")
    job_store.update(record.job_id, status="running")
    record = job_store.get(job_id)              # None if not found
    all_jobs = job_store.list_for_user(user_id) # user-scoped list

The in-memory store keeps the old list_all() name for backward compatibility
and adds a no-op user_id parameter so callers can be written uniformly.
"""

from __future__ import annotations

import os
import threading
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from typing import Dict, List, Optional

from agents.long_to_shorts.api.models import ClipResult, JobRequest, JobStatus


class _MemoryJobStore:
    """Thread-safe in-memory store for job records (development / testing)."""

    def __init__(self) -> None:
        self._lock: threading.Lock = threading.Lock()
        self._jobs: Dict[str, JobStatus] = {}

    def create(self, request: JobRequest, *, user_id: str = "dev") -> JobStatus:
        now = datetime.now(tz=timezone.utc)
        job = JobStatus(
            job_id=str(uuid.uuid4()),
            status="queued",
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            self._jobs[job.job_id] = job
        return job

    def update(
        self,
        job_id: str,
        *,
        status: Optional[str] = None,
        clips: Optional[List[ClipResult]] = None,
        error: Optional[str] = None,
        current_node: Optional[str] = None,
    ) -> Optional[JobStatus]:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            updates: dict = {"updated_at": datetime.now(tz=timezone.utc)}
            if status is not None:
                updates["status"] = status
            if clips is not None:
                updates["clips"] = clips
            if error is not None:
                updates["error"] = error
            if current_node is not None:
                updates["current_node"] = current_node
            updated = job.model_copy(update=updates)
            self._jobs[job_id] = updated
            return updated

    def get(self, job_id: str) -> Optional[JobStatus]:
        with self._lock:
            job = self._jobs.get(job_id)
            return deepcopy(job) if job else None

    def get_for_user(self, job_id: str, user_id: str) -> Optional[JobStatus]:
        return self.get(job_id)

    def list_for_user(
        self,
        user_id: str,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> List[JobStatus]:
        with self._lock:
            records = list(self._jobs.values())
        records.sort(key=lambda j: j.created_at, reverse=True)
        return [deepcopy(r) for r in records[offset : offset + limit]]

    # Keep old name as an alias for backward compatibility
    def list_all(self) -> List[JobStatus]:
        return self.list_for_user("dev")

    def get_clip(self, job_id: str, clip_id: str) -> Optional[ClipResult]:
        job = self.get(job_id)
        if job is None or not job.clips:
            return None
        for clip in job.clips:
            if clip.clip_id == clip_id:
                return clip
        return None

    def get_clip_for_user(
        self, job_id: str, clip_id: str, user_id: str
    ) -> Optional[ClipResult]:
        return self.get_clip(job_id, clip_id)


def _make_job_store():
    backend = os.getenv("JOB_STORE", "memory").lower()
    if backend == "supabase":
        from agents.long_to_shorts.api.db.job_store import supabase_job_store
        return supabase_job_store
    return _MemoryJobStore()


job_store = _make_job_store()

__all__ = ["job_store"]
