"""
agents/long_to_shorts/api/events_routes.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Server-Sent Events (SSE) endpoints — the push replacement for polling.

For each resource (clip job, edit job, YouTube upload) a client opens an
``EventSource`` to ``…/events?token=<jwt>``. The handler:

  1. authenticates the query-string JWT (EventSource can't send headers) and
     verifies ownership,
  2. sends an immediate **snapshot** of the current record,
  3. subscribes to the resource's channel on the event bus and streams every
     subsequent ``update`` (published by the EventEmittingStore wrapper),
  4. emits a heartbeat comment every 15s so proxies keep the connection open,
  5. closes once the record reaches a terminal status.

EventSource reconnects automatically if the stream drops; on reconnect the fresh
snapshot re-syncs the client, so no server-side replay buffer is required. All the
existing polling GET endpoints remain, so this is purely additive.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Callable, Optional

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse

from agents.long_to_shorts.api.edit_job_store import edit_job_store
from agents.long_to_shorts.api.job_store import job_store
from agents.long_to_shorts.api.youtube_upload_store import youtube_upload_store
from core.execution.eventbus import get_event_bus

logger = logging.getLogger(__name__)

router = APIRouter()

_HEARTBEAT_SECONDS = 15.0
_TERMINAL = {"done", "failed"}

_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",  # disable nginx buffering so events flush live
}


def _user_from_token(token: Optional[str]) -> str:
    """Validate the query-string JWT and return the user id (or dev user)."""
    from agents.long_to_shorts.api.auth import (
        _DEV_USER_ID,
        _auth_disabled,
        _decode_token,
    )

    if _auth_disabled():
        return _DEV_USER_ID
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing 'token' query parameter.",
        )
    try:
        payload = _decode_token(token)
    except Exception as exc:  # noqa: BLE001 — surface any jwt error as 401
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {exc}",
        )
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token payload missing 'sub' claim.",
        )
    return user_id


def _sse_frame(event_type: str, data: dict, *, event_id: Optional[str] = None) -> str:
    out = []
    if event_id:
        out.append(f"id: {event_id}")
    out.append(f"event: {event_type}")
    out.append(f"data: {json.dumps(data)}")
    return "\n".join(out) + "\n\n"


async def _event_stream(
    request: Request,
    channel: str,
    snapshot_getter: Callable[[], Optional[Any]],
):
    """Async generator yielding SSE frames for one resource channel."""
    bus = get_event_bus()
    sub = bus.subscribe(channel)
    try:
        snapshot = snapshot_getter()
        if snapshot is None:
            yield _sse_frame("error", {"detail": "not found"})
            return
        snap_data = snapshot.model_dump(mode="json")
        yield _sse_frame("snapshot", snap_data, event_id=str(snap_data.get("updated_at")))
        if snap_data.get("status") in _TERMINAL:
            return  # already finished — one snapshot is all the client needs

        while True:
            if await request.is_disconnected():
                break
            event = await sub.get(timeout=_HEARTBEAT_SECONDS)
            if event is None:
                yield ": heartbeat\n\n"
                continue
            yield _sse_frame(event.type, event.data, event_id=event.id)
            if event.data.get("status") in _TERMINAL:
                break
    except asyncio.CancelledError:  # pragma: no cover - client disconnect
        raise
    finally:
        sub.close()


def _stream_response(request: Request, channel: str, snapshot_getter) -> StreamingResponse:
    return StreamingResponse(
        _event_stream(request, channel, snapshot_getter),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


# ---------------------------------------------------------------------------
# Clip job stream
# ---------------------------------------------------------------------------

@router.get("/jobs/{job_id}/events", summary="Stream live job progress (SSE)")
async def job_events(
    job_id: str,
    request: Request,
    token: Optional[str] = Query(default=None),
) -> StreamingResponse:
    user_id = _user_from_token(token)
    return _stream_response(
        request, f"job:{job_id}",
        lambda: job_store.get_for_user(job_id, user_id),
    )


# ---------------------------------------------------------------------------
# Edit job stream
# ---------------------------------------------------------------------------

@router.get("/edit/jobs/{edit_job_id}/events", summary="Stream live edit-job progress (SSE)")
async def edit_job_events(
    edit_job_id: str,
    request: Request,
    token: Optional[str] = Query(default=None),
) -> StreamingResponse:
    user_id = _user_from_token(token)
    return _stream_response(
        request, f"edit:{edit_job_id}",
        lambda: edit_job_store.get_for_user(edit_job_id, user_id),
    )


# ---------------------------------------------------------------------------
# YouTube upload stream
# ---------------------------------------------------------------------------

@router.get("/youtube/uploads/{upload_id}/events", summary="Stream live upload progress (SSE)")
async def upload_events(
    upload_id: str,
    request: Request,
    token: Optional[str] = Query(default=None),
) -> StreamingResponse:
    user_id = _user_from_token(token)
    return _stream_response(
        request, f"upload:{upload_id}",
        lambda: youtube_upload_store.get_for_user(upload_id, user_id),
    )


__all__ = ["router"]
