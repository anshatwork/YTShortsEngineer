"""
agents/long_to_shorts/api/publishing_store.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Publishing-job store selector (memory | supabase), wrapped in EventEmittingStore
so every update() publishes on the ``publish:<id>`` channel for SSE — exactly
like job_store.py / ingestion_job_store.py.

The ``publishing_jobs`` row is the **source of truth** for the durable, human-gated
state machine: every transition is a persisted update(), so a crash mid-run loses
nothing — the recovery sweep re-enqueues the step for the persisted status.

    from agents.long_to_shorts.api.publishing_store import publishing_store
"""

from __future__ import annotations

import os
import threading
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from agents.long_to_shorts.api.models import PublishingJob, PublishingStartRequest


# The mutable columns of a publishing job. Kept in one place so the memory store
# and the Supabase mapper agree on exactly what update() may set.
_UPDATE_FIELDS = (
    "status", "phase_detail", "candidates", "approved_video_url", "clip_job_id",
    "source_context", "generated_clips", "selected_clip_id",
    "upload_privacy_status", "upload_category_id", "upload_tags",
    "scored_clips", "selected_clip", "eval_report", "revision_count",
    "upload_id", "video_id", "video_url", "error",
)


class _MemoryPublishingStore:
    """Thread-safe in-memory store (development / testing)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._rows: Dict[str, PublishingJob] = {}
        self._requests: Dict[str, PublishingStartRequest] = {}
        self._owners: Dict[str, str] = {}

    def create(self, request: PublishingStartRequest, *, user_id: str = "dev") -> PublishingJob:
        now = datetime.now(tz=timezone.utc)
        job = PublishingJob(
            publishing_job_id=str(uuid.uuid4()),
            status="discovering",
            query=request.query,
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            self._rows[job.publishing_job_id] = job
            self._requests[job.publishing_job_id] = request
            self._owners[job.publishing_job_id] = user_id
        return job

    def update(self, publishing_job_id: str, **fields) -> Optional[PublishingJob]:
        with self._lock:
            job = self._rows.get(publishing_job_id)
            if job is None:
                return None
            updates: dict = {"updated_at": datetime.now(tz=timezone.utc)}
            for key in _UPDATE_FIELDS:
                if key in fields and fields[key] is not None:
                    updates[key] = fields[key]
            job = job.model_copy(update=updates)
            self._rows[publishing_job_id] = job
            return job

    def get(self, publishing_job_id: str) -> Optional[PublishingJob]:
        with self._lock:
            return self._rows.get(publishing_job_id)

    def get_for_user(self, publishing_job_id: str, user_id: str) -> Optional[PublishingJob]:
        with self._lock:
            if self._owners.get(publishing_job_id) not in (None, user_id):
                # memory store is single-tenant in practice; still honour ownership
                return None
            return self._rows.get(publishing_job_id)

    def get_request_for_user(
        self, publishing_job_id: str, user_id: str
    ) -> Optional[PublishingStartRequest]:
        with self._lock:
            return self._requests.get(publishing_job_id)

    def update_request(self, publishing_job_id: str, request: PublishingStartRequest) -> None:
        with self._lock:
            if publishing_job_id in self._requests:
                self._requests[publishing_job_id] = request

    def owner_of(self, publishing_job_id: str) -> Optional[str]:
        with self._lock:
            return self._owners.get(publishing_job_id)

    def list_for_user(self, user_id: str, *, limit: int = 100, offset: int = 0) -> List[PublishingJob]:
        with self._lock:
            rows = list(self._rows.values())
        rows.sort(key=lambda j: j.created_at, reverse=True)
        return rows[offset:offset + limit]

    def list_resumable(self) -> List[PublishingJob]:
        """Non-terminal, non-waiting jobs — the crash-recovery sweep re-enqueues these."""
        from core.execution.lifecycle import PUBLISHING_RESUMABLE

        with self._lock:
            return [j for j in self._rows.values() if j.status in PUBLISHING_RESUMABLE]


def _make_publishing_store():
    backend = os.getenv("JOB_STORE", "memory").lower()
    if backend == "supabase":
        from agents.long_to_shorts.api.db.publishing_store import supabase_publishing_store
        inner = supabase_publishing_store
    else:
        inner = _MemoryPublishingStore()
    from agents.long_to_shorts.api.event_store import EventEmittingStore
    return EventEmittingStore(inner, channel_prefix="publish", id_attr="publishing_job_id")


publishing_store = _make_publishing_store()

__all__ = ["publishing_store"]
