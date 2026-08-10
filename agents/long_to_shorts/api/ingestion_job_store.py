"""
agents/long_to_shorts/api/ingestion_job_store.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Ingestion-job store selector (memory | supabase), wrapped in EventEmittingStore so
every update() publishes on the ``ingest:<id>`` channel for SSE — exactly like
job_store.py does for clip jobs.

    from agents.long_to_shorts.api.ingestion_job_store import ingestion_job_store
"""

from __future__ import annotations

import os
import threading
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from agents.long_to_shorts.api.models import IngestionJob


class _MemoryIngestionJobStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._rows: Dict[str, IngestionJob] = {}

    def create(self, asset_id: str, *, user_id: str) -> IngestionJob:
        now = datetime.now(tz=timezone.utc)
        job = IngestionJob(
            ingestion_job_id=str(uuid.uuid4()), asset_id=asset_id,
            status="queued", created_at=now, updated_at=now,
        )
        with self._lock:
            self._rows[job.ingestion_job_id] = job
        return job

    def update(self, ingestion_job_id: str, *, status: Optional[str] = None,
               current_node: Optional[str] = None, error: Optional[str] = None,
               stats: Optional[dict] = None) -> Optional[IngestionJob]:
        with self._lock:
            job = self._rows.get(ingestion_job_id)
            if job is None:
                return None
            updates: dict = {"updated_at": datetime.now(tz=timezone.utc)}
            if status is not None:
                updates["status"] = status
            if current_node is not None:
                updates["current_node"] = current_node
            if error is not None:
                updates["error"] = error
            if stats is not None:
                updates["stats"] = stats
            job = job.model_copy(update=updates)
            self._rows[ingestion_job_id] = job
            return job

    def get(self, ingestion_job_id: str) -> Optional[IngestionJob]:
        with self._lock:
            return self._rows.get(ingestion_job_id)

    def get_for_user(self, ingestion_job_id: str, user_id: str) -> Optional[IngestionJob]:
        return self.get(ingestion_job_id)

    def list_for_user(self, user_id: str, *, limit: int = 100, offset: int = 0) -> List[IngestionJob]:
        with self._lock:
            rows = list(self._rows.values())
        rows.sort(key=lambda j: j.created_at, reverse=True)
        return rows[offset:offset + limit]


def _make_ingestion_job_store():
    backend = os.getenv("JOB_STORE", "memory").lower()
    if backend == "supabase":
        from agents.long_to_shorts.api.db.asset_store import supabase_ingestion_job_store
        inner = supabase_ingestion_job_store
    else:
        inner = _MemoryIngestionJobStore()
    from agents.long_to_shorts.api.event_store import EventEmittingStore
    return EventEmittingStore(inner, channel_prefix="ingest", id_attr="ingestion_job_id")


ingestion_job_store = _make_ingestion_job_store()

__all__ = ["ingestion_job_store"]
