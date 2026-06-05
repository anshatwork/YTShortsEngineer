"""
agents/long_to_shorts/api/auth.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
FastAPI dependency for JWT authentication via Supabase.

Usage in route handlers
-----------------------
    from agents.long_to_shorts.api.auth import get_current_user_id

    @router.get("/jobs")
    async def list_jobs(user_id: str = Depends(get_current_user_id)):
        ...

AUTH_DISABLED mode
------------------
Set the environment variable AUTH_DISABLED=true to skip JWT verification
entirely.  All requests are attributed to the fixed dev user id
`00000000-0000-0000-0000-000000000001`.  Only use in local development —
never expose an AUTH_DISABLED server on a public network.

JWT verification
----------------
Supabase signs JWTs with the project's JWT secret (available in Project
Settings → API → JWT Secret).  Set SUPABASE_JWT_SECRET in the FastAPI .env
and we validate HMAC-SHA256 (HS256) locally — no network round-trip needed.
"""

from __future__ import annotations

import os

import jwt
from jwt import PyJWKClient
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_DEV_USER_ID = "00000000-0000-0000-0000-000000000001"
_bearer_scheme = HTTPBearer(auto_error=False)

# Cached JWKS client — lazily initialised on first request.
_jwks_client: PyJWKClient | None = None


def _auth_disabled() -> bool:
    return os.getenv("AUTH_DISABLED", "").lower() in ("1", "true", "yes")


def _get_jwks_client() -> PyJWKClient | None:
    global _jwks_client
    if _jwks_client is None:
        supabase_url = os.environ.get("SUPABASE_URL")
        if supabase_url:
            _jwks_client = PyJWKClient(
                f"{supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json",
                cache_keys=True,
            )
    return _jwks_client


def _decode_token(token: str) -> dict:
    """Decode a Supabase JWT, supporting both RS256 (JWKS) and HS256."""
    # Peek at the header algorithm without verifying the signature.
    header = jwt.get_unverified_header(token)
    alg = header.get("alg", "HS256")

    if alg != "HS256":
        # RS256 / ES256 — validate via Supabase's JWKS endpoint.
        client = _get_jwks_client()
        if client is None:
            raise jwt.InvalidTokenError("SUPABASE_URL not set; cannot fetch JWKS.")
        signing_key = client.get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key,
            algorithms=["RS256", "ES256"],
            options={"require": ["sub", "exp"], "verify_aud": False},
        )

    # HS256 — validate with the symmetric JWT secret.
    jwt_secret = os.environ.get("SUPABASE_JWT_SECRET")
    if not jwt_secret:
        raise jwt.InvalidTokenError("SUPABASE_JWT_SECRET not set.")
    return jwt.decode(
        token,
        jwt_secret,
        algorithms=["HS256"],
        options={"require": ["sub", "exp"], "verify_aud": False},
    )


async def get_current_user_id(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> str:
    """Extract and verify the caller's user_id from the Supabase JWT.

    Returns the string UUID of the authenticated user, or raises HTTP 401.
    When AUTH_DISABLED=true returns the fixed dev user id without validating.
    """
    if _auth_disabled():
        return _DEV_USER_ID

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = _decode_token(credentials.credentials)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id: str | None = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token payload missing 'sub' claim.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user_id


__all__ = ["get_current_user_id"]
