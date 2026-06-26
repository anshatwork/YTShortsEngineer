"""
agents/long_to_shorts/api/db/stage_store.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Supabase-backed per-stage execution journal (table: job_stages).

Same surface as :class:`_MemoryStageStore`. All writes use the service-role
worker client (bypasses RLS) since they happen in background workers with no user
JWT. Upserts are keyed on the (job_id, stage) unique constraint so re-runs update
the existing row rather than duplicating it.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Optional

from agents.long_to_shorts.api.supabase_client import get_worker_client
from core.execution import lifecycle

logger = logging.getLogger(__name__)

_TABLE = "job_stages"


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


class SupabaseStageStore:
    def _client(self):
        return get_worker_client()

    def start(self, job_id: str, stage: str) -> None:
        # Bump attempt if the row already exists; otherwise insert a fresh one.
        prior = (
            self._client().table(_TABLE)
            .select("attempt").eq("job_id", job_id).eq("stage", stage)
            .limit(1).execute()
        )
        attempt = ((prior.data[0]["attempt"] if prior.data else 0) or 0) + 1
        self._client().table(_TABLE).upsert(
            {
                "job_id": job_id, "stage": stage,
                "status": lifecycle.STAGE_RUNNING,
                "attempt": attempt, "started_at": _now_iso(),
                "completed_at": None, "error": None,
            },
            on_conflict="job_id,stage",
        ).execute()

    def complete(
        self, job_id: str, stage: str, *, artifact_ids: Optional[List[str]] = None
    ) -> None:
        self._client().table(_TABLE).upsert(
            {
                "job_id": job_id, "stage": stage,
                "status": lifecycle.STAGE_COMPLETE,
                "completed_at": _now_iso(),
                "output_artifact_ids": artifact_ids,
                "error": None,
            },
            on_conflict="job_id,stage",
        ).execute()

    def fail(self, job_id: str, stage: str, *, error: str) -> None:
        self._client().table(_TABLE).upsert(
            {
                "job_id": job_id, "stage": stage,
                "status": lifecycle.STAGE_FAILED,
                "completed_at": _now_iso(), "error": error[:2000],
            },
            on_conflict="job_id,stage",
        ).execute()

    def is_complete(self, job_id: str, stage: str) -> bool:
        res = (
            self._client().table(_TABLE)
            .select("status").eq("job_id", job_id).eq("stage", stage)
            .limit(1).execute()
        )
        return bool(res.data and res.data[0]["status"] == lifecycle.STAGE_COMPLETE)

    def list_for_job(self, job_id: str) -> List[dict]:
        res = (
            self._client().table(_TABLE)
            .select("*").eq("job_id", job_id).order("started_at").execute()
        )
        return res.data or []


supabase_stage_store = SupabaseStageStore()

__all__ = ["SupabaseStageStore", "supabase_stage_store"]
