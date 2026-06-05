"""
agents/long_to_shorts/api/edit_job_store.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Edit-job store — in-memory implementation with optional Supabase backend.

Active backend is determined by the JOB_STORE environment variable:

  JOB_STORE=supabase  →  SupabaseEditJobStore
  JOB_STORE=memory    →  _MemoryEditJobStore  (default)

Usage
-----
    from agents.long_to_shorts.api.edit_job_store import edit_job_store

    job = edit_job_store.create("tts", user_id="...", parent_job_id="...")
    edit_job_store.update(job.edit_job_id, status="done", output_url="...")
"""

from __future__ import annotations

import os
import threading
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from typing import Dict, List, Optional

from agents.long_to_shorts.api.models import EditJob, EditOperation


class _MemoryEditJobStore:
    """Thread-safe in-memory store for edit-operation job records."""

    def __init__(self) -> None:
        self._lock: threading.Lock = threading.Lock()
        self._jobs: Dict[str, EditJob] = {}

    def create(
        self,
        operation: EditOperation,
        *,
        user_id: str = "dev",
        parent_job_id: Optional[str] = None,
        clip_id: Optional[str] = None,
    ) -> EditJob:
        now = datetime.now(tz=timezone.utc)
        job = EditJob(
            edit_job_id=str(uuid.uuid4()),
            operation=operation,
            parent_job_id=parent_job_id,
            clip_id=clip_id,
            status="queued",
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            self._jobs[job.edit_job_id] = job
        return job

    def update(
        self,
        edit_job_id: str,
        *,
        status: Optional[str] = None,
        output_path: Optional[str] = None,
        output_url: Optional[str] = None,
        error: Optional[str] = None,
    ) -> Optional[EditJob]:
        with self._lock:
            job = self._jobs.get(edit_job_id)
            if job is None:
                return None
            updates: dict = {"updated_at": datetime.now(tz=timezone.utc)}
            if status is not None:
                updates["status"] = status
            if output_path is not None:
                updates["output_path"] = output_path
            if output_url is not None:
                updates["output_url"] = output_url
            if error is not None:
                updates["error"] = error
            updated = job.model_copy(update=updates)
            self._jobs[edit_job_id] = updated
            return updated

    def get(self, edit_job_id: str) -> Optional[EditJob]:
        with self._lock:
            job = self._jobs.get(edit_job_id)
            return deepcopy(job) if job else None

    def get_for_user(self, edit_job_id: str, user_id: str) -> Optional[EditJob]:
        return self.get(edit_job_id)

    def list_for_user(
        self,
        user_id: str,
        *,
        parent_job_id: Optional[str] = None,
        clip_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[EditJob]:
        with self._lock:
            records = list(self._jobs.values())
        if parent_job_id is not None:
            records = [r for r in records if r.parent_job_id == parent_job_id]
        if clip_id is not None:
            records = [r for r in records if r.clip_id == clip_id]
        records.sort(key=lambda j: j.created_at, reverse=True)
        return [deepcopy(r) for r in records[offset : offset + limit]]

    # Backward-compatible alias used by legacy callers
    def list_all(
        self,
        *,
        parent_job_id: Optional[str] = None,
        clip_id: Optional[str] = None,
    ) -> List[EditJob]:
        return self.list_for_user(
            "dev", parent_job_id=parent_job_id, clip_id=clip_id
        )


def _make_edit_job_store():
    backend = os.getenv("JOB_STORE", "memory").lower()
    if backend == "supabase":
        from agents.long_to_shorts.api.db.edit_job_store import (
            supabase_edit_job_store,
        )
        return supabase_edit_job_store
    return _MemoryEditJobStore()


edit_job_store = _make_edit_job_store()

__all__ = ["edit_job_store"]
