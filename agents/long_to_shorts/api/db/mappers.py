"""
agents/long_to_shorts/api/db/mappers.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Convert between Supabase Postgres row dicts and the Pydantic models used
throughout the API.  All DB↔Pydantic translation lives here so that the store
modules stay thin and the route handlers never touch raw dicts.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from agents.long_to_shorts.api.models import (
    ClipResult,
    EditJob,
    JobStatus,
    YouTubeUploadJob,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_dt(value: Any) -> datetime:
    """Accept a datetime, ISO string, or None and always return a UTC datetime."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    # Fallback — should not happen with a well-formed DB row
    return datetime.now(tz=timezone.utc)


def _parse_clips(raw: Any) -> Optional[List[ClipResult]]:
    """Deserialize the clips JSONB column into a list of ClipResult objects."""
    if raw is None:
        return None
    if isinstance(raw, str):
        raw = json.loads(raw)
    if not isinstance(raw, list):
        return None
    return [ClipResult(**c) for c in raw]


def _serialize_clips(clips: Optional[List[ClipResult]]) -> Optional[list]:
    """Serialize ClipResult list for JSONB storage."""
    if clips is None:
        return None
    return [c.model_dump(mode="json") for c in clips]


# ---------------------------------------------------------------------------
# clip_jobs ↔ JobStatus
# ---------------------------------------------------------------------------

def row_to_job_status(row: Dict[str, Any]) -> JobStatus:
    return JobStatus(
        job_id=str(row["job_id"]),
        status=row["status"],
        created_at=_parse_dt(row["created_at"]),
        updated_at=_parse_dt(row["updated_at"]),
        clips=_parse_clips(row.get("clips")),
        error=row.get("error"),
        current_node=row.get("current_node"),
    )


def job_status_to_insert(
    job_id: str,
    user_id: str,
    request_body: Any,
) -> Dict[str, Any]:
    """Build the dict for a new clip_jobs INSERT."""
    request_json = (
        request_body.model_dump(mode="json")
        if hasattr(request_body, "model_dump")
        else request_body
    )
    return {
        "job_id": job_id,
        "user_id": user_id,
        "status": "queued",
        "request": request_json,
    }


def job_status_to_update(
    *,
    status: Optional[str] = None,
    clips: Optional[List[ClipResult]] = None,
    error: Optional[str] = None,
    current_node: Optional[str] = None,
) -> Dict[str, Any]:
    """Build the dict for a partial clip_jobs UPDATE (only set fields)."""
    patch: Dict[str, Any] = {}
    if status is not None:
        patch["status"] = status
    if clips is not None:
        patch["clips"] = _serialize_clips(clips)
    if error is not None:
        patch["error"] = error
    if current_node is not None:
        patch["current_node"] = current_node
    return patch


# ---------------------------------------------------------------------------
# edit_jobs ↔ EditJob
# ---------------------------------------------------------------------------

def row_to_edit_job(row: Dict[str, Any]) -> EditJob:
    return EditJob(
        edit_job_id=str(row["edit_job_id"]),
        operation=row["operation"],
        parent_job_id=str(row["parent_job_id"]) if row.get("parent_job_id") else None,
        clip_id=row.get("clip_id"),
        status=row["status"],
        created_at=_parse_dt(row["created_at"]),
        updated_at=_parse_dt(row["updated_at"]),
        output_path=row.get("output_path"),
        output_url=row.get("output_url"),
        error=row.get("error"),
    )


def edit_job_to_insert(
    edit_job_id: str,
    user_id: str,
    operation: str,
    *,
    parent_job_id: Optional[str] = None,
    clip_id: Optional[str] = None,
) -> Dict[str, Any]:
    row: Dict[str, Any] = {
        "edit_job_id": edit_job_id,
        "user_id": user_id,
        "operation": operation,
        "status": "queued",
    }
    if parent_job_id is not None:
        row["parent_job_id"] = parent_job_id
    if clip_id is not None:
        row["clip_id"] = clip_id
    return row


def edit_job_to_update(
    *,
    status: Optional[str] = None,
    output_path: Optional[str] = None,
    output_url: Optional[str] = None,
    error: Optional[str] = None,
) -> Dict[str, Any]:
    patch: Dict[str, Any] = {}
    if status is not None:
        patch["status"] = status
    if output_path is not None:
        patch["output_path"] = output_path
    if output_url is not None:
        patch["output_url"] = output_url
    if error is not None:
        patch["error"] = error
    return patch


# ---------------------------------------------------------------------------
# youtube_uploads ↔ YouTubeUploadJob
# ---------------------------------------------------------------------------

def row_to_youtube_upload(row: Dict[str, Any]) -> YouTubeUploadJob:
    return YouTubeUploadJob(
        upload_id=str(row["upload_id"]),
        parent_job_id=str(row["parent_job_id"]) if row.get("parent_job_id") else None,
        clip_id=row.get("clip_id"),
        status=row["status"],
        created_at=_parse_dt(row["created_at"]),
        updated_at=_parse_dt(row["updated_at"]),
        title=row.get("title"),
        privacy_status=row.get("privacy_status"),
        video_id=row.get("video_id"),
        video_url=row.get("video_url"),
        error=row.get("error"),
    )


def youtube_upload_to_insert(
    upload_id: str,
    user_id: str,
    *,
    parent_job_id: Optional[str] = None,
    clip_id: Optional[str] = None,
    title: Optional[str] = None,
    privacy_status: Optional[str] = None,
) -> Dict[str, Any]:
    row: Dict[str, Any] = {
        "upload_id": upload_id,
        "user_id": user_id,
        "status": "queued",
    }
    if parent_job_id is not None:
        row["parent_job_id"] = parent_job_id
    if clip_id is not None:
        row["clip_id"] = clip_id
    if title is not None:
        row["title"] = title
    if privacy_status is not None:
        row["privacy_status"] = privacy_status
    return row


def youtube_upload_to_update(
    *,
    status: Optional[str] = None,
    video_id: Optional[str] = None,
    video_url: Optional[str] = None,
    error: Optional[str] = None,
) -> Dict[str, Any]:
    patch: Dict[str, Any] = {}
    if status is not None:
        patch["status"] = status
    if video_id is not None:
        patch["video_id"] = video_id
    if video_url is not None:
        patch["video_url"] = video_url
    if error is not None:
        patch["error"] = error
    return patch
