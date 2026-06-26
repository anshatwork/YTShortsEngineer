"""
agents/long_to_shorts/api/stage_store.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The per-stage execution journal (Part 3): one record per (job_id, pipeline stage).

This is the durable manifest / checkpoint log. Every LangGraph node, via
``_logging_utils.node_stage``, records when it starts, completes (with the cache
artifact ids it produced), or fails. Because it is persisted (Supabase in prod),
the journal is visible across processes and machines — a crashed job's progress
is inspectable, and a re-run can see which stages already completed.

Note on resumability: actually *skipping* recompute on resume is handled by the
content-addressable cache (core/cache) — a re-run gets cache hits for Whisper, the
LLM stages, and clip extraction, so it is cheap and idempotent. This journal is
the formal checkpoint/observability layer on top of that mechanism.

Backend mirrors the other stores: JOB_STORE=supabase → Supabase, else in-memory.
"""

from __future__ import annotations

import os
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.execution import lifecycle


class _MemoryStageStore:
    """In-memory journal (dev/test). Keyed by (job_id, stage)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._rows: Dict[tuple, dict] = {}

    def start(self, job_id: str, stage: str) -> None:
        now = datetime.now(tz=timezone.utc)
        with self._lock:
            existing = self._rows.get((job_id, stage))
            attempt = (existing["attempt"] + 1) if existing else 1
            self._rows[(job_id, stage)] = {
                "job_id": job_id, "stage": stage,
                "status": lifecycle.STAGE_RUNNING,
                "attempt": attempt, "started_at": now,
                "completed_at": None, "error": None,
                "output_artifact_ids": None,
            }

    def complete(
        self, job_id: str, stage: str, *, artifact_ids: Optional[List[str]] = None
    ) -> None:
        now = datetime.now(tz=timezone.utc)
        with self._lock:
            row = self._rows.get((job_id, stage)) or {
                "job_id": job_id, "stage": stage, "attempt": 1, "started_at": now
            }
            row.update({
                "status": lifecycle.STAGE_COMPLETE,
                "completed_at": now,
                "output_artifact_ids": artifact_ids,
                "error": None,
            })
            self._rows[(job_id, stage)] = row

    def fail(self, job_id: str, stage: str, *, error: str) -> None:
        now = datetime.now(tz=timezone.utc)
        with self._lock:
            row = self._rows.get((job_id, stage)) or {
                "job_id": job_id, "stage": stage, "attempt": 1, "started_at": now
            }
            row.update({
                "status": lifecycle.STAGE_FAILED,
                "completed_at": now, "error": error[:2000],
            })
            self._rows[(job_id, stage)] = row

    def is_complete(self, job_id: str, stage: str) -> bool:
        with self._lock:
            row = self._rows.get((job_id, stage))
            return bool(row and row["status"] == lifecycle.STAGE_COMPLETE)

    def list_for_job(self, job_id: str) -> List[dict]:
        with self._lock:
            return [dict(v) for (jid, _), v in self._rows.items() if jid == job_id]


def _make_stage_store():
    backend = os.getenv("JOB_STORE", "memory").lower()
    if backend == "supabase":
        try:
            from agents.long_to_shorts.api.db.stage_store import supabase_stage_store
            return supabase_stage_store
        except Exception:  # noqa: BLE001 — never block the pipeline on journal infra
            pass
    return _MemoryStageStore()


stage_store = _make_stage_store()

__all__ = ["stage_store"]
