"""
agents/long_to_shorts/api/kg_routes.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
FastAPI router for the Knowledge Graph — asset registration, ingestion, and the
read surface (hybrid search + NL query). Additive; existing routes/URLs unchanged.

Endpoints (mounted at /api/v1):
    POST /assets                     Register an owned media asset            (201)
    GET  /assets                     List the caller's assets
    GET  /assets/{asset_id}          Get one asset
    POST /assets/{asset_id}/ingest   Enqueue KG ingestion                     (202)
    GET  /ingest/jobs                List ingestion jobs
    GET  /ingest/jobs/{id}           Poll one ingestion job
    POST /kg/search                  Hybrid vector + lexical search
    POST /kg/query                   Natural-language → structured query
    GET  /kg/assets/{asset_id}/graph 1-hop neighborhood of a MediaAsset
    GET  /kg/health                  Graph connectivity probe

Heavy reads (embedding the query, graph traversal) run off the event loop via
``asyncio.to_thread`` — never block the loop (repo rule).
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from agents.long_to_shorts.api.asset_store import asset_store
from agents.long_to_shorts.api.auth import get_current_user_id
from agents.long_to_shorts.api.ingestion_job_store import ingestion_job_store
from agents.long_to_shorts.api.models import (
    AssetListResponse,
    AssetRecord,
    AssetRegisterRequest,
    IngestionJob,
    IngestionJobListResponse,
    KGAskRequest,
    KGNodeResult,
    KGSearchRequest,
    KGSearchResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()

_VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}
_AUDIO_EXT = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}
_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}


def _infer_media_type(uri: str) -> str:
    ext = Path(uri).suffix.lower()
    if ext in _VIDEO_EXT:
        return "video"
    if ext in _AUDIO_EXT:
        return "audio"
    if ext in _IMAGE_EXT:
        return "image"
    return "video"


def _require_kg_enabled() -> None:
    from core.kg import driver

    if not driver.kg_enabled():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Knowledge graph is disabled (set KG_ENABLED=true).",
        )


# ---------------------------------------------------------------------------
# Asset registration + ingestion
# ---------------------------------------------------------------------------

@router.post("/assets", response_model=AssetRecord, status_code=status.HTTP_201_CREATED,
             summary="Register an owned media asset for the knowledge graph")
async def register_asset(
    body: AssetRegisterRequest,
    user_id: str = Depends(get_current_user_id),
) -> AssetRecord:
    uri = body.youtube_url or body.source_path
    if not uri:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Provide either 'youtube_url' or 'source_path'.",
        )
    media_type = body.media_type or (_infer_media_type(uri) if body.source_path else "video")
    return asset_store.register(
        user_id=user_id, media_type=media_type, uri=uri,
        filename=body.filename, title=body.title,
    )


@router.get("/assets", response_model=AssetListResponse,
            summary="List the caller's registered assets")
async def list_assets(
    user_id: str = Depends(get_current_user_id),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> AssetListResponse:
    assets = asset_store.list_for_user(user_id, limit=limit, offset=offset)
    return AssetListResponse(assets=assets, total=len(assets))


@router.get("/assets/{asset_id}", response_model=AssetRecord, summary="Get one asset")
async def get_asset(asset_id: str, user_id: str = Depends(get_current_user_id)) -> AssetRecord:
    asset = asset_store.get_for_user(asset_id, user_id)
    if asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found.")
    return asset


@router.post("/assets/{asset_id}/ingest", response_model=IngestionJob,
             status_code=status.HTTP_202_ACCEPTED,
             summary="Enqueue knowledge-graph ingestion for an asset")
async def ingest_asset(
    asset_id: str,
    http_request: Request,
    user_id: str = Depends(get_current_user_id),
) -> IngestionJob:
    _require_kg_enabled()
    asset = asset_store.get_for_user(asset_id, user_id)
    if asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found.")

    # Meter before enqueue; the runner refunds idempotently on failure.
    from agents.long_to_shorts.api.credits import enforce_and_debit
    enforce_and_debit(user_id, "ingest")

    job = ingestion_job_store.create(asset_id, user_id=user_id)

    from agents.long_to_shorts.api.ingestion_runner import run_ingestion
    http_request.app.state.task_queue.enqueue(run_ingestion, job.ingestion_job_id, asset_id, user_id)
    logger.info("Ingestion %s queued — asset=%s user=%s", job.ingestion_job_id, asset_id, user_id)
    return job


@router.get("/ingest/jobs", response_model=IngestionJobListResponse,
            summary="List ingestion jobs for the current user")
async def list_ingestion_jobs(
    user_id: str = Depends(get_current_user_id),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> IngestionJobListResponse:
    jobs = ingestion_job_store.list_for_user(user_id, limit=limit, offset=offset)
    return IngestionJobListResponse(ingestion_jobs=jobs, total=len(jobs))


@router.get("/ingest/jobs/{ingestion_job_id}", response_model=IngestionJob,
            summary="Poll an ingestion job")
async def get_ingestion_job(
    ingestion_job_id: str, user_id: str = Depends(get_current_user_id)
) -> IngestionJob:
    job = ingestion_job_store.get_for_user(ingestion_job_id, user_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ingestion job not found.")
    return job


# ---------------------------------------------------------------------------
# Read surface
# ---------------------------------------------------------------------------

@router.post("/kg/search", response_model=KGSearchResponse,
             summary="Hybrid vector + lexical search over the knowledge graph")
async def kg_search(
    body: KGSearchRequest, user_id: str = Depends(get_current_user_id)
) -> KGSearchResponse:
    _require_kg_enabled()
    from core.kg import query as kg_query

    try:
        results = await asyncio.to_thread(
            kg_query.semantic_search, body.label, body.query, user_id,
            top_k=body.top_k, modality=body.modality,
        )
    except ValueError as exc:  # unsafe label / bad spec
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    payload = [KGNodeResult(labels=r.labels, properties=r.properties, score=r.score) for r in results]
    return KGSearchResponse(results=payload, total=len(payload))


@router.post("/kg/query", response_model=KGSearchResponse,
             summary="Natural-language question → structured graph query")
async def kg_query_nl(
    body: KGAskRequest, user_id: str = Depends(get_current_user_id)
) -> KGSearchResponse:
    _require_kg_enabled()
    from core.kg import query as kg_query

    def _run():
        spec = kg_query.interpret_query(body.question)
        spec.top_k = body.top_k
        rows = kg_query.query(spec, user_id)
        return rows

    try:
        rows = await asyncio.to_thread(_run)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    payload = [KGNodeResult(labels=r.get("labels", []), properties=r.get("props", {})) for r in rows]
    return KGSearchResponse(results=payload, total=len(payload))


@router.get("/kg/assets/{asset_id}/graph", response_model=KGSearchResponse,
            summary="1-hop neighborhood of an asset's MediaAsset node")
async def kg_asset_graph(
    asset_id: str,
    user_id: str = Depends(get_current_user_id),
    limit: int = Query(default=50, ge=1, le=200),
) -> KGSearchResponse:
    _require_kg_enabled()
    asset = asset_store.get_for_user(asset_id, user_id)
    if asset is None or not asset.content_hash:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not ingested.")
    from core.kg import query as kg_query

    rows = await asyncio.to_thread(
        kg_query.neighborhood, "MediaAsset", {"content_hash": asset.content_hash},
        user_id, limit=limit,
    )
    payload = [KGNodeResult(labels=r.get("labels", []), properties=r.get("props", {})) for r in rows]
    return KGSearchResponse(results=payload, total=len(payload))


@router.get("/kg/health", summary="Knowledge-graph connectivity probe")
async def kg_health() -> dict:
    from core.kg import driver
    return await asyncio.to_thread(driver.health)


__all__ = ["router"]
