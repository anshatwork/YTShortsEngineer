"""
agents/long_to_shorts/api/db/job_store.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Supabase-backed implementation of the clip-job store.

Implements the same surface as the in-memory _JobStore so that routes and
workers require no changes beyond switching which store is imported.

Worker paths (runner.py) must call update() via this module — they use the
service-role client which bypasses RLS, so no user JWT is needed.

Route paths call create() and list_for_user() with an explicit user_id that
was extracted from the verified JWT by auth.py.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from agents.long_to_shorts.api.db.mappers import (
    job_status_to_insert,
    job_status_to_update,
    row_to_job_status,
)
from agents.long_to_shorts.api.models import ClipResult, JobRequest, JobStatus
from agents.long_to_shorts.api.supabase_client import get_worker_client

logger = logging.getLogger(__name__)

_TABLE = "clip_jobs"


class SupabaseJobStore:
    """Supabase-backed job store; all writes use the service-role key."""

    # ------------------------------------------------------------------
    # Write helpers
    # ------------------------------------------------------------------

    def create(self, request: JobRequest, *, user_id: str) -> JobStatus:
        """Insert a new job row and return the populated JobStatus."""
        job_id = str(uuid.uuid4())
        now = datetime.now(tz=timezone.utc)
        row = job_status_to_insert(job_id, user_id, request)
        client = get_worker_client()
        result = (
            client.table(_TABLE)
            .insert(row)
            .execute()
        )
        data = result.data
        if data:
            return row_to_job_status(data[0])
        # Fallback: construct from what we sent
        return JobStatus(
            job_id=job_id,
            status="queued",
            created_at=now,
            updated_at=now,
        )

    def update(
        self,
        job_id: str,
        *,
        status: Optional[str] = None,
        clips: Optional[List[ClipResult]] = None,
        error: Optional[str] = None,
        current_node: Optional[str] = None,
    ) -> Optional[JobStatus]:
        """Partial update via service-role key (bypasses RLS; safe from workers)."""
        patch = job_status_to_update(
            status=status,
            clips=clips,
            error=error,
            current_node=current_node,
        )
        if not patch:
            return self.get(job_id)
        client = get_worker_client()
        result = (
            client.table(_TABLE)
            .update(patch)
            .eq("job_id", job_id)
            .execute()
        )
        data = result.data
        if data:
            return row_to_job_status(data[0])
        return None

    # ------------------------------------------------------------------
    # Read helpers
    # ------------------------------------------------------------------

    def get(self, job_id: str) -> Optional[JobStatus]:
        """Fetch a single job by id (service-role, no RLS check)."""
        client = get_worker_client()
        result = (
            client.table(_TABLE)
            .select("*")
            .eq("job_id", job_id)
            .limit(1)
            .execute()
        )
        data = result.data
        if not data:
            return None
        return row_to_job_status(data[0])

    def get_for_user(self, job_id: str, user_id: str) -> Optional[JobStatus]:
        """Fetch a single job and verify it belongs to the given user."""
        client = get_worker_client()
        result = (
            client.table(_TABLE)
            .select("*")
            .eq("job_id", job_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        data = result.data
        if not data:
            return None
        return row_to_job_status(data[0])

    def list_for_user(
        self,
        user_id: str,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> List[JobStatus]:
        """Return paginated jobs for a user, most-recent first."""
        client = get_worker_client()
        result = (
            client.table(_TABLE)
            .select("*")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .range(offset, offset + limit - 1)
            .execute()
        )
        return [row_to_job_status(row) for row in (result.data or [])]

    def get_clip(self, job_id: str, clip_id: str):
        """Resolve a (job_id, clip_id) pair to its ClipResult, or None."""
        job = self.get(job_id)
        if job is None or not job.clips:
            return None
        for clip in job.clips:
            if clip.clip_id == clip_id:
                return clip
        return None

    def get_clip_for_user(self, job_id: str, clip_id: str, user_id: str):
        """Like get_clip but verifies job ownership first."""
        job = self.get_for_user(job_id, user_id)
        if job is None or not job.clips:
            return None
        for clip in job.clips:
            if clip.clip_id == clip_id:
                return clip
        return None


supabase_job_store = SupabaseJobStore()

__all__ = ["SupabaseJobStore", "supabase_job_store"]
