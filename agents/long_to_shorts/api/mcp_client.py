"""
agents/long_to_shorts/api/mcp_client.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
In-process bridge from MCP tools to the existing FastAPI routes.

Why call the app rather than the service functions directly?
------------------------------------------------------------
The REST handlers already carry all the business rules the MCP layer must not
re-derive: source validation, quota enforcement (``quota.enforce_quota``),
per-user ownership (``*_store.get_for_user``) and the exact request/response
schemas. By dispatching MCP tool calls through the very same ASGI ``app`` via
``httpx.ASGITransport`` we get guaranteed behaviour parity with the HTTP API
and zero logic duplication — an MCP tool is just another client of ``/api/v1``.

Because the MCP server is mounted onto the same ``app`` (see ``app.py``) and
runs in the same process, ``ASGITransport`` shares ``app.state`` — including the
``task_queue`` the routes enqueue background jobs onto — so no separate HTTP
round-trip, socket, or re-initialisation happens.

Auth
----
When the MCP request carried a Supabase OAuth token (the normal case behind
``SupabaseProvider``), the caller forwards it here as ``token`` and we replay it
verbatim as the ``Authorization`` header. The routes' ``get_current_user_id``
dependency verifies it exactly as it would for a browser request, so the tool
acts as the authenticated user. In local ``AUTH_DISABLED`` dev runs there is no
token and the header is omitted (the routes then attribute the call to the dev
user).
"""

from __future__ import annotations

from typing import Any, Optional

import httpx

# Internal base URL for the ASGI transport. Never leaves the process — the host
# is irrelevant, it only satisfies httpx's URL construction.
_BASE_URL = "http://mcp.internal"


async def call_api(
    method: str,
    path: str,
    *,
    token: Optional[str] = None,
    json: Any | None = None,
    params: dict[str, Any] | None = None,
    timeout: float = 60.0,
) -> httpx.Response:
    """Dispatch an HTTP call to the mounted FastAPI app in-process.

    Parameters
    ----------
    method : e.g. "GET", "POST".
    path   : app path, e.g. "/api/v1/jobs" (NOT prefixed with the base url).
    token  : raw Supabase JWT to forward as the bearer credential, or None.
    json   : request body (already JSON-serialisable dict), or None.
    params : query-string parameters, or None.

    Returns the raw ``httpx.Response`` so callers can branch on ``status_code``
    and surface the API's own error ``detail`` to the model.
    """
    # Lazy import to avoid a circular import at module load: app.py imports the
    # MCP server (which imports this module) only after `app` is constructed.
    from agents.long_to_shorts.api.app import app

    headers: dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(
        transport=transport, base_url=_BASE_URL, timeout=timeout
    ) as client:
        return await client.request(
            method, path, json=json, params=params, headers=headers
        )


__all__ = ["call_api"]
