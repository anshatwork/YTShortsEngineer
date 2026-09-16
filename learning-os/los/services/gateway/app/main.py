"""API Gateway FastAPI app.

Exposes the client-facing ``/v1`` surface, authenticates each request, and proxies to the ingestion
service with a trusted ``X-User-Id`` header + a per-request ``X-Correlation-Id`` (for cross-service
tracing). Phase 0 wires only the content endpoints; graph/search/assets are added as their services
land.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Optional

import httpx
from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

from los.config import get_settings
from los.domain_shared.ids import new_uuid
from los.services.gateway.app.auth import get_owner_id

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.ingestion_url = settings.ingestion_url.rstrip("/")
    app.state.http = httpx.AsyncClient(timeout=30.0)
    logger.info("gateway up → ingestion %s", app.state.ingestion_url)
    try:
        yield
    finally:
        await app.state.http.aclose()


app = FastAPI(title="Learning OS — API Gateway", version="0.0.0", lifespan=lifespan)


def _fwd_headers(owner_id: str, request: Request) -> dict[str, str]:
    return {
        "X-User-Id": owner_id,
        "X-Correlation-Id": request.headers.get("x-correlation-id") or new_uuid(),
    }


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "gateway"}


@app.post("/v1/content")
async def create_content(request: Request, owner_id: str = Depends(get_owner_id)) -> JSONResponse:
    body = await request.body()
    client: httpx.AsyncClient = request.app.state.http
    resp = await client.post(
        f"{request.app.state.ingestion_url}/content",
        content=body,
        headers={**_fwd_headers(owner_id, request), "Content-Type": "application/json"},
    )
    return JSONResponse(status_code=resp.status_code, content=resp.json())


@app.get("/v1/content")
async def list_content(request: Request, owner_id: str = Depends(get_owner_id)) -> JSONResponse:
    client: httpx.AsyncClient = request.app.state.http
    resp = await client.get(
        f"{request.app.state.ingestion_url}/content",
        headers=_fwd_headers(owner_id, request),
    )
    return JSONResponse(status_code=resp.status_code, content=resp.json())


@app.get("/v1/content/{content_id}")
async def get_content(content_id: str, request: Request,
                      owner_id: str = Depends(get_owner_id)) -> JSONResponse:
    client: httpx.AsyncClient = request.app.state.http
    resp = await client.get(
        f"{request.app.state.ingestion_url}/content/{content_id}",
        headers=_fwd_headers(owner_id, request),
    )
    return JSONResponse(status_code=resp.status_code, content=resp.json())


@app.get("/v1/content/{content_id}/events")
async def content_events(content_id: str, request: Request,
                         owner_id: str = Depends(get_owner_id)) -> StreamingResponse:
    """Pass the ingestion SSE stream straight through to the client."""
    client: httpx.AsyncClient = request.app.state.http
    url = f"{request.app.state.ingestion_url}/content/{content_id}/events"
    headers = _fwd_headers(owner_id, request)

    async def _proxy():
        async with client.stream("GET", url, headers=headers) as upstream:
            async for chunk in upstream.aiter_raw():
                yield chunk

    return StreamingResponse(_proxy(), media_type="text/event-stream")
