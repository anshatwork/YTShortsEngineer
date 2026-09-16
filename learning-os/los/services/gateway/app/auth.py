"""Edge authentication — verify a Supabase JWT and return the owner id (``sub``).

Mirrors the parent repo's ``auth.py``: HS256 verification against ``SUPABASE_JWT_SECRET``, with an
``AUTH_DISABLED`` escape hatch for local dev/tests (never enable in prod). Entitlement/owner is
always derived from the verified token, never from the request body.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import Header, HTTPException

from los.config import get_settings

logger = logging.getLogger(__name__)


def _decode_owner(token: str, secret: str) -> str:
    import jwt  # PyJWT, lazy

    try:
        claims = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            options={"verify_aud": False},  # Supabase sets aud="authenticated"
        )
    except Exception as exc:  # invalid signature / expired / malformed
        raise HTTPException(status_code=401, detail="invalid token") from exc
    sub = claims.get("sub")
    if not sub:
        raise HTTPException(status_code=401, detail="token missing sub")
    return str(sub)


async def get_owner_id(authorization: Optional[str] = Header(default=None)) -> str:
    """FastAPI dependency → owner id. Bearer JWT in prod; dev owner when ``AUTH_DISABLED``."""
    settings = get_settings()

    if settings.auth_disabled:
        # Allow an explicit bearer even in dev (so tests can pin an owner), else the dev owner.
        if authorization and authorization.lower().startswith("bearer "):
            raw = authorization[7:].strip()
            # In dev a bearer may be a bare owner id rather than a signed JWT.
            if raw and "." not in raw:
                return raw
        return settings.dev_owner_id

    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    if not settings.supabase_jwt_secret:
        raise HTTPException(status_code=500, detail="server auth not configured")
    return _decode_owner(authorization[7:].strip(), settings.supabase_jwt_secret)
