"""
agents/long_to_shorts/api/db/edit_job_store.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Supabase-backed implementation of the edit-job store (TTS, music, split-screen).

Mirrors the in-memory _EditJobStore interface.  Workers use the service-role
client; route handlers pass user_id from the verified JWT for ownership checks.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from agents.long_to_shorts.api.db.mappers import (
    edit_job_to_insert,
    edit_job_to_update,
    row_to_edit_job,
)
from agents.long_to_shorts.api.models import EditJob, EditOperation
from agents.long_to_shorts.api.supabase_client import get_worker_client

logger = logging.getLogger(__name__)

_TABLE = "edit_jobs"


class SupabaseEditJobStore:
    """Supabase-backed store for edit-operation jobs."""

    # ------------------------------------------------------------------
    # Write helpers
    # ------------------------------------------------------------------

    def create(
        self,
        operation: EditOperation,
        *,
        user_id: str,
        parent_job_id: Optional[str] = None,
        clip_id: Optional[str] = None,
    ) -> EditJob:
        edit_job_id = str(uuid.uuid4())
        now = datetime.now(tz=timezone.utc)
        row = edit_job_to_insert(
            edit_job_id,
            user_id,
            operation,
            parent_job_id=parent_job_id,
            clip_id=clip_id,
        )
        client = get_worker_client()
        result = (
            client.table(_TABLE)
            .insert(row)
            .execute()
        )
        data = result.data
        if data:
            return row_to_edit_job(data[0])
        return EditJob(
            edit_job_id=edit_job_id,
            operation=operation,
            parent_job_id=parent_job_id,
            clip_id=clip_id,
            status="queued",
            created_at=now,
            updated_at=now,
        )

    def update(
        self,
        edit_job_id: str,
        *,
        status: Optional[str] = None,
        output_path: Optional[str] = None,
        output_url: Optional[str] = None,
        error: Optional[str] = None,
    ) -> Optional[EditJob]:
        patch = edit_job_to_update(
            status=status,
            output_path=output_path,
            output_url=output_url,
            error=error,
        )
        if not patch:
            return self.get(edit_job_id)
        client = get_worker_client()
        result = (
            client.table(_TABLE)
            .update(patch)
            .eq("edit_job_id", edit_job_id)
            .execute()
        )
        data = result.data
        if data:
            return row_to_edit_job(data[0])
        return None

    # ------------------------------------------------------------------
    # Read helpers
    # ------------------------------------------------------------------

    def get(self, edit_job_id: str) -> Optional[EditJob]:
        client = get_worker_client()
        result = (
            client.table(_TABLE)
            .select("*")
            .eq("edit_job_id", edit_job_id)
            .limit(1)
            .execute()
        )
        data = result.data
        if not data:
            return None
        return row_to_edit_job(data[0])

    def get_for_user(self, edit_job_id: str, user_id: str) -> Optional[EditJob]:
        client = get_worker_client()
        result = (
            client.table(_TABLE)
            .select("*")
            .eq("edit_job_id", edit_job_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        data = result.data
        if not data:
            return None
        return row_to_edit_job(data[0])

    def list_for_user(
        self,
        user_id: str,
        *,
        parent_job_id: Optional[str] = None,
        clip_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[EditJob]:
        client = get_worker_client()
        query = (
            client.table(_TABLE)
            .select("*")
            .eq("user_id", user_id)
        )
        if parent_job_id is not None:
            query = query.eq("parent_job_id", parent_job_id)
        if clip_id is not None:
            query = query.eq("clip_id", clip_id)
        result = (
            query
            .order("created_at", desc=True)
            .range(offset, offset + limit - 1)
            .execute()
        )
        return [row_to_edit_job(row) for row in (result.data or [])]


supabase_edit_job_store = SupabaseEditJobStore()

__all__ = ["SupabaseEditJobStore", "supabase_edit_job_store"]
