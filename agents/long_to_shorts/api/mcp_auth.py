"""
agents/long_to_shorts/api/mcp_auth.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
OAuth wiring for the MCP connector.

Claude.ai and ChatGPT both add a remote MCP server as a *custom connector* and
drive an OAuth 2.1 sign-in (Dynamic Client Registration + PKCE + discovery
metadata) before any tool runs. FastMCP ships a first-class ``SupabaseProvider``
that makes the MCP server a *resource server*: it forwards OAuth metadata so the
client talks to Supabase Auth directly, and verifies the resulting Supabase JWT.

The upshot for this app: the MCP access token **is a Supabase JWT**, so its
``sub`` claim is exactly the ``user_id`` every store and quota check already keys
on. We do not mint tokens or map emails — tools simply forward the verified token
into the in-process routes (see ``mcp_client.call_api``).

Dev / local
-----------
When ``AUTH_DISABLED`` is set (or the Supabase/public-URL env is absent) this
returns ``None`` so the MCP server runs unauthenticated for local smoke tests;
the routes then attribute calls to the fixed dev user. This mirrors ``auth.py``'s
hard guard — an unauthenticated MCP server must never be exposed in production.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_DEV_USER_ID = "00000000-0000-0000-0000-000000000001"


def _auth_disabled() -> bool:
    """Whether MCP auth is intentionally off (dev only), mirroring auth.py.

    Refuses the bypass under ENVIRONMENT=production so a stray AUTH_DISABLED in a
    prod env file can never expose an unauthenticated connector.
    """
    disabled = os.getenv("AUTH_DISABLED", "").lower() in ("1", "true", "yes")
    if disabled and os.getenv("ENVIRONMENT", "development").lower() == "production":
        raise RuntimeError(
            "AUTH_DISABLED is set while ENVIRONMENT=production — refusing to "
            "disable MCP authentication in production."
        )
    return disabled


def build_auth_provider():
    """Construct the FastMCP auth provider for the MCP server, or None (dev).

    Returns a ``SupabaseProvider`` when ``SUPABASE_URL`` and ``MCP_PUBLIC_URL``
    are configured; otherwise returns None. Raises in production if auth cannot
    be configured, so we never silently serve an open connector.
    """
    if _auth_disabled():
        logger.warning("MCP auth DISABLED (dev) — connector will not require sign-in.")
        return None

    supabase_url = os.getenv("SUPABASE_URL", "").strip()
    public_url = os.getenv("MCP_PUBLIC_URL", "").strip()
    # Must match the project's Supabase Auth JWT algorithm. Modern projects use
    # asymmetric keys (ES256/RS256) verified via the JWKS endpoint; HS256 is the
    # legacy symmetric default. See auth.py which supports both.
    algorithm = os.getenv("MCP_JWT_ALGORITHM", "ES256").strip() or "ES256"

    is_production = os.getenv("ENVIRONMENT", "development").lower() == "production"

    if not supabase_url or not public_url:
        msg = (
            "MCP auth requires SUPABASE_URL and MCP_PUBLIC_URL to be set "
            "(the public https base url of this server, e.g. https://api.example.com)."
        )
        if is_production:
            raise RuntimeError(msg + " Refusing to start an open connector in production.")
        logger.warning("%s MCP running WITHOUT auth (dev).", msg)
        return None

    from fastmcp.server.auth.providers.supabase import SupabaseProvider

    logger.info(
        "MCP auth enabled — SupabaseProvider(project=%s, base=%s, alg=%s)",
        supabase_url, public_url, algorithm,
    )
    return SupabaseProvider(
        project_url=supabase_url,
        base_url=public_url,
        algorithm=algorithm,  # type: ignore[arg-type]
    )


def current_bearer() -> str | None:
    """Return the raw Supabase JWT for the current MCP request, or None.

    Tools forward this verbatim to the in-process routes so the call runs as the
    authenticated user. None in AUTH_DISABLED dev runs (routes then use the dev
    user id).
    """
    try:
        from fastmcp.server.dependencies import get_access_token
    except Exception:  # noqa: BLE001 — fastmcp not importable shouldn't crash callers
        return None

    token = get_access_token()
    return token.token if token is not None else None


__all__ = ["build_auth_provider", "current_bearer"]
