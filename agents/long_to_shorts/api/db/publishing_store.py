"""
agents/long_to_shorts/api/db/publishing_store.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Supabase-backed implementation of the publishing-job store — the durable
source-of-truth table (``publishing_jobs``) for the autonomous publishing state
machine. Same surface as ``_MemoryPublishingStore`` so the selector can swap it
in with no route/runner changes.

Rich sub-objects (candidates, scored_clips, selected_clip, eval_report) are held
in JSONB columns and round-tripped through the Pydantic models. Writes use the
service-role worker client (bypasses RLS); reads are scoped by user_id.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from agents.long_to_shorts.api.models import (
    ClipResult,
    PublishingJob,
    PublishingStartRequest,
    YouTubeVideoContext,
)
from agents.long_to_shorts.api.supabase_client import get_worker_client
from agents.publishing.schemas import DiscoveryRecommendation, EvalReport, ScoreCard

logger = logging.getLogger(__name__)

_TABLE = "publishing_jobs"

# JSONB columns that carry Pydantic sub-objects, with their (de)serialisers.
_JSON_LIST = {
    "candidates": DiscoveryRecommendation,
    "scored_clips": ScoreCard,
    "generated_clips": ClipResult,
}
_JSON_OBJ = {
    "source_context": YouTubeVideoContext,
    "selected_clip": ClipResult,
    "eval_report": EvalReport,
}
_UPDATE_FIELDS = (
    "status", "phase_detail", "candidates", "approved_video_url", "clip_job_id",
    "source_context", "generated_clips", "selected_clip_id",
    "upload_privacy_status", "upload_category_id", "upload_tags",
    "scored_clips", "selected_clip", "eval_report", "revision_count",
    "upload_id", "video_id", "video_url", "error",
)


def _parse_dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    return datetime.now(tz=timezone.utc)


def _load(raw: Any):
    if isinstance(raw, str):
        return json.loads(raw)
    return raw


def _row_to_job(row: Dict[str, Any]) -> PublishingJob:
    kwargs: Dict[str, Any] = {
        "publishing_job_id": str(row["publishing_job_id"]),
        "status": row["status"],
        "created_at": _parse_dt(row["created_at"]),
        "updated_at": _parse_dt(row["updated_at"]),
        "query": row.get("query"),
        "phase_detail": row.get("phase_detail"),
        "approved_video_url": row.get("approved_video_url"),
        "selected_clip_id": row.get("selected_clip_id"),
        "upload_privacy_status": row.get("upload_privacy_status") or "private",
        "upload_category_id": row.get("upload_category_id") or "22",
        "upload_tags": row.get("upload_tags") or [],
        "clip_job_id": str(row["clip_job_id"]) if row.get("clip_job_id") else None,
        "revision_count": row.get("revision_count") or 0,
        "upload_id": str(row["upload_id"]) if row.get("upload_id") else None,
        "video_id": row.get("video_id"),
        "video_url": row.get("video_url"),
        "error": row.get("error"),
    }
    for col, model in _JSON_LIST.items():
        raw = _load(row.get(col))
        kwargs[col] = [model(**x) for x in raw] if isinstance(raw, list) else None
    for col, model in _JSON_OBJ.items():
        raw = _load(row.get(col))
        kwargs[col] = model(**raw) if isinstance(raw, dict) else None
    return PublishingJob(**kwargs)


def _patch_value(key: str, value: Any) -> Any:
    if key in _JSON_LIST:
        return [x.model_dump(mode="json") for x in value]
    if key in _JSON_OBJ:
        return value.model_dump(mode="json")
    return value


class SupabasePublishingStore:
    def create(self, request: PublishingStartRequest, *, user_id: str) -> PublishingJob:
        publishing_job_id = str(uuid.uuid4())
        now = datetime.now(tz=timezone.utc)
        row = {
            "publishing_job_id": publishing_job_id,
            "user_id": user_id,
            "status": "discovering",
            "query": request.query,
            "request": request.model_dump(mode="json"),
        }
        client = get_worker_client()
        result = client.table(_TABLE).insert(row).execute()
        if result.data:
            return _row_to_job(result.data[0])
        return PublishingJob(
            publishing_job_id=publishing_job_id, status="discovering",
            query=request.query, created_at=now, updated_at=now,
        )

    def update(self, publishing_job_id: str, **fields) -> Optional[PublishingJob]:
        patch: Dict[str, Any] = {}
        for key in _UPDATE_FIELDS:
            if key in fields and fields[key] is not None:
                patch[key] = _patch_value(key, fields[key])
        if not patch:
            return self.get(publishing_job_id)
        client = get_worker_client()
        result = (
            client.table(_TABLE).update(patch)
            .eq("publishing_job_id", publishing_job_id).execute()
        )
        return _row_to_job(result.data[0]) if result.data else None

    def update_request(self, publishing_job_id: str, request: PublishingStartRequest) -> None:
        get_worker_client().table(_TABLE).update(
            {"request": request.model_dump(mode="json")}
        ).eq("publishing_job_id", publishing_job_id).execute()

    def get(self, publishing_job_id: str) -> Optional[PublishingJob]:
        client = get_worker_client()
        result = (
            client.table(_TABLE).select("*")
            .eq("publishing_job_id", publishing_job_id).limit(1).execute()
        )
        return _row_to_job(result.data[0]) if result.data else None

    def get_for_user(self, publishing_job_id: str, user_id: str) -> Optional[PublishingJob]:
        client = get_worker_client()
        result = (
            client.table(_TABLE).select("*")
            .eq("publishing_job_id", publishing_job_id)
            .eq("user_id", user_id).limit(1).execute()
        )
        return _row_to_job(result.data[0]) if result.data else None

    def get_request_for_user(
        self, publishing_job_id: str, user_id: str
    ) -> Optional[PublishingStartRequest]:
        client = get_worker_client()
        result = (
            client.table(_TABLE).select("request")
            .eq("publishing_job_id", publishing_job_id)
            .eq("user_id", user_id).limit(1).execute()
        )
        if not result.data:
            return None
        raw = _load(result.data[0].get("request"))
        if not raw:
            return None
        try:
            return PublishingStartRequest(**raw)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not rehydrate publishing request %s: %s", publishing_job_id, exc)
            return None

    def owner_of(self, publishing_job_id: str) -> Optional[str]:
        client = get_worker_client()
        result = (
            client.table(_TABLE).select("user_id")
            .eq("publishing_job_id", publishing_job_id).limit(1).execute()
        )
        return str(result.data[0]["user_id"]) if result.data else None

    def list_for_user(self, user_id: str, *, limit: int = 100, offset: int = 0) -> List[PublishingJob]:
        client = get_worker_client()
        result = (
            client.table(_TABLE).select("*").eq("user_id", user_id)
            .order("created_at", desc=True).range(offset, offset + limit - 1).execute()
        )
        return [_row_to_job(r) for r in (result.data or [])]

    def list_resumable(self) -> List[PublishingJob]:
        from core.execution.lifecycle import PUBLISHING_RESUMABLE

        client = get_worker_client()
        result = (
            client.table(_TABLE).select("*")
            .in_("status", list(PUBLISHING_RESUMABLE)).execute()
        )
        return [_row_to_job(r) for r in (result.data or [])]


supabase_publishing_store = SupabasePublishingStore()

__all__ = ["SupabasePublishingStore", "supabase_publishing_store"]
