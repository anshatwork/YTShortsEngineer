"""
agents/long_to_shorts/api/db/asset_store.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Supabase-backed stores for KG asset registration + ingestion jobs (tables from
supabase/migrations/010_kg.sql). Mirrors the shape of db/job_store.py: worker
writes use the service-role client (bypasses RLS); reads are user-scoped.

Supabase remains the system-of-record for OWNERSHIP and job tracking; the semantic
graph itself lives in Neo4j (core/kg).
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from agents.long_to_shorts.api.models import AssetRecord, IngestionJob
from agents.long_to_shorts.api.supabase_client import get_worker_client

logger = logging.getLogger(__name__)

_ASSETS = "assets"
_INGEST = "ingestion_jobs"


def _row_to_asset(row: dict) -> AssetRecord:
    return AssetRecord(**row)  # Pydantic ignores extra keys (user_id) + coerces dates


def _row_to_ingestion(row: dict) -> IngestionJob:
    return IngestionJob(**row)


class SupabaseAssetStore:
    def register(
        self,
        *,
        user_id: str,
        media_type: str,
        uri: str,
        filename: Optional[str] = None,
        title: Optional[str] = None,
    ) -> AssetRecord:
        asset_id = str(uuid.uuid4())
        row = {
            "asset_id": asset_id, "user_id": user_id, "media_type": media_type,
            "uri": uri, "filename": filename, "title": title, "status": "registered",
        }
        data = get_worker_client().table(_ASSETS).insert(row).execute().data
        return _row_to_asset(data[0]) if data else _row_to_asset({
            **row, "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        })

    def set_status(
        self, asset_id: str, *, status: str, content_hash: Optional[str] = None
    ) -> None:
        patch: dict = {"status": status}
        if content_hash is not None:
            patch["content_hash"] = content_hash
        get_worker_client().table(_ASSETS).update(patch).eq("asset_id", asset_id).execute()

    def get(self, asset_id: str) -> Optional[AssetRecord]:
        data = (
            get_worker_client().table(_ASSETS).select("*")
            .eq("asset_id", asset_id).limit(1).execute().data
        )
        return _row_to_asset(data[0]) if data else None

    def get_for_user(self, asset_id: str, user_id: str) -> Optional[AssetRecord]:
        data = (
            get_worker_client().table(_ASSETS).select("*")
            .eq("asset_id", asset_id).eq("user_id", user_id).limit(1).execute().data
        )
        return _row_to_asset(data[0]) if data else None

    def list_for_user(self, user_id: str, *, limit: int = 100, offset: int = 0) -> List[AssetRecord]:
        data = (
            get_worker_client().table(_ASSETS).select("*")
            .eq("user_id", user_id).order("created_at", desc=True)
            .range(offset, offset + limit - 1).execute().data
        )
        return [_row_to_asset(r) for r in (data or [])]


class SupabaseIngestionJobStore:
    def create(self, asset_id: str, *, user_id: str) -> IngestionJob:
        row = {
            "ingestion_job_id": str(uuid.uuid4()), "asset_id": asset_id,
            "user_id": user_id, "status": "queued",
        }
        data = get_worker_client().table(_INGEST).insert(row).execute().data
        return _row_to_ingestion(data[0]) if data else _row_to_ingestion({
            **row, "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        })

    def update(
        self,
        ingestion_job_id: str,
        *,
        status: Optional[str] = None,
        current_node: Optional[str] = None,
        error: Optional[str] = None,
        stats: Optional[dict] = None,
    ) -> Optional[IngestionJob]:
        patch: dict = {}
        if status is not None:
            patch["status"] = status
        if current_node is not None:
            patch["current_node"] = current_node
        if error is not None:
            patch["error"] = error
        if stats is not None:
            patch["stats"] = stats
        if not patch:
            return self.get(ingestion_job_id)
        data = (
            get_worker_client().table(_INGEST).update(patch)
            .eq("ingestion_job_id", ingestion_job_id).execute().data
        )
        return _row_to_ingestion(data[0]) if data else None

    def get(self, ingestion_job_id: str) -> Optional[IngestionJob]:
        data = (
            get_worker_client().table(_INGEST).select("*")
            .eq("ingestion_job_id", ingestion_job_id).limit(1).execute().data
        )
        return _row_to_ingestion(data[0]) if data else None

    def get_for_user(self, ingestion_job_id: str, user_id: str) -> Optional[IngestionJob]:
        data = (
            get_worker_client().table(_INGEST).select("*")
            .eq("ingestion_job_id", ingestion_job_id).eq("user_id", user_id)
            .limit(1).execute().data
        )
        return _row_to_ingestion(data[0]) if data else None

    def list_for_user(self, user_id: str, *, limit: int = 100, offset: int = 0) -> List[IngestionJob]:
        data = (
            get_worker_client().table(_INGEST).select("*")
            .eq("user_id", user_id).order("created_at", desc=True)
            .range(offset, offset + limit - 1).execute().data
        )
        return [_row_to_ingestion(r) for r in (data or [])]


supabase_asset_store = SupabaseAssetStore()
supabase_ingestion_job_store = SupabaseIngestionJobStore()

__all__ = [
    "SupabaseAssetStore",
    "SupabaseIngestionJobStore",
    "supabase_asset_store",
    "supabase_ingestion_job_store",
]
