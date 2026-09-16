"""Content Ingestion FastAPI app.

Routes (mounted at root; the gateway prefixes ``/v1`` and proxies here):
- ``POST /content``            → save + append ``ContentSaved`` (202)
- ``GET  /content``            → list this owner's content
- ``GET  /content/{id}``       → status + metadata
- ``GET  /content/{id}/events``→ SSE snapshot of ingestion status (expanded to live in Phase 1)
- ``GET  /health``

Backends are chosen from env (memory by default) and built in the lifespan, so the whole service
runs with zero infra for tests. The outbox relay publishes ``ContentSaved`` to the broker in the
background.
"""

from __future__ import annotations

import json
import logging
import os
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from los.config import get_settings
from los.events.factory import make_broker, make_event_store
from los.events.outbox import OutboxRelay
from los.services.ingestion.adapters.repository import make_content_repository
from los.services.ingestion.app.service import IngestionService
from los.services.ingestion.domain.content import Content, SourceType

logger = logging.getLogger(__name__)


class SaveContentRequest(BaseModel):
    url: str = Field(..., min_length=1)
    source_type: SourceType
    title: Optional[str] = None
    selection: Optional[str] = None  # highlighted text from the extension (kept for Phase 1)


class ContentResponse(BaseModel):
    content_id: str
    owner_id: str
    source_type: SourceType
    url: str
    status: str
    created: bool = True

    @classmethod
    def of(cls, c: Content, created: bool) -> "ContentResponse":
        return cls(content_id=c.content_id, owner_id=c.owner_id, source_type=c.source_type,
                   url=c.url, status=c.status.value, created=created)


def _owner_from_header(x_user_id: Optional[str]) -> str:
    """Owner is set by the gateway (which verified the JWT) via ``X-User-Id``. In AUTH_DISABLED dev
    mode we accept it directly or fall back to the dev owner."""
    settings = get_settings()
    if x_user_id:
        return x_user_id
    if settings.auth_disabled:
        return settings.dev_owner_id
    raise HTTPException(status_code=401, detail="missing X-User-Id (gateway must authenticate)")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    repo = make_content_repository(settings.content_store_backend, settings.pg_dsn)
    store = make_event_store(settings)
    broker = make_broker(settings)
    await repo.start()
    await store.start()
    await broker.start()
    relay = OutboxRelay(store, broker, poll_seconds=settings.outbox_poll_seconds)

    app.state.repo = repo
    app.state.event_store = store
    app.state.broker = broker
    app.state.relay = relay
    app.state.service = IngestionService(repo, store)

    if os.getenv("OUTBOX_AUTOSTART", "1").strip().lower() in {"1", "true", "yes", "on"}:
        relay.start()
    logger.info("ingestion up (content=%s event_store=%s broker=%s)",
                settings.content_store_backend, settings.event_store_backend, settings.broker_backend)
    try:
        yield
    finally:
        await relay.stop()
        await broker.close()
        await store.close()
        await repo.close()


app = FastAPI(title="Learning OS — Content Ingestion", version="0.0.0", lifespan=lifespan)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "ingestion"}


@app.post("/content", status_code=202, response_model=ContentResponse)
async def save_content(
    body: SaveContentRequest,
    request: Request,
    x_user_id: Optional[str] = Header(default=None),
    x_correlation_id: Optional[str] = Header(default=None),
) -> ContentResponse:
    owner_id = _owner_from_header(x_user_id)
    service: IngestionService = request.app.state.service
    content, created = await service.save_content(
        owner_id=owner_id,
        url=body.url,
        source_type=body.source_type,
        title=body.title,
        correlation_id=x_correlation_id,
    )
    return ContentResponse.of(content, created)


@app.get("/content", response_model=list[ContentResponse])
async def list_content(
    request: Request,
    x_user_id: Optional[str] = Header(default=None),
) -> list[ContentResponse]:
    owner_id = _owner_from_header(x_user_id)
    items = await request.app.state.repo.list_for_owner(owner_id)
    return [ContentResponse.of(c, created=False) for c in items]


@app.get("/content/{content_id}", response_model=ContentResponse)
async def get_content(
    content_id: str,
    request: Request,
    x_user_id: Optional[str] = Header(default=None),
) -> ContentResponse:
    owner_id = _owner_from_header(x_user_id)
    c = await request.app.state.repo.get(owner_id, content_id)
    if c is None:
        raise HTTPException(status_code=404, detail="content not found")
    return ContentResponse.of(c, created=False)


@app.get("/content/{content_id}/events")
async def content_events(
    content_id: str,
    request: Request,
    x_user_id: Optional[str] = Header(default=None),
) -> StreamingResponse:
    """Minimal SSE: emit a snapshot of the current status. Phase 1 upgrades this to a live projection
    driven off the broker (mirrors the parent repo's ``events_routes`` snapshot→update pattern)."""
    owner_id = _owner_from_header(x_user_id)
    c = await request.app.state.repo.get(owner_id, content_id)
    if c is None:
        raise HTTPException(status_code=404, detail="content not found")

    async def _stream():
        snapshot = {"content_id": c.content_id, "status": c.status.value, "type": "snapshot"}
        yield f"event: snapshot\ndata: {json.dumps(snapshot)}\n\n"

    return StreamingResponse(_stream(), media_type="text/event-stream")
