"""
agents/long_to_shorts/api/youtube_oauth.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Google OAuth 2.0 plumbing for the "Connect YouTube" flow + authenticated
client construction for uploads.

Design
------
* A dedicated OAuth flow (separate from Supabase login) requests the
  ``youtube.upload`` + ``youtube.readonly`` scopes with ``access_type=offline``
  and ``prompt=consent`` so Google returns a long-lived refresh token.
* The refresh token is stored per user (see youtube_credentials_store). Access
  tokens are minted/refreshed on demand and cached back into the store.
* The public ``/auth/callback`` endpoint carries no Authorization header, so we
  recover the user id from a short-lived signed ``state`` token (HMAC via the
  Supabase JWT secret) — this also doubles as CSRF protection.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

import jwt

# Scopes requested when connecting a YouTube account.
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]

_TOKEN_URI = "https://oauth2.googleapis.com/token"
_AUTH_URI = "https://accounts.google.com/o/oauth2/auth"

# Signed-state lifetime — the user must complete consent within this window.
_STATE_TTL_SECONDS = 600
_STATE_AUDIENCE = "youtube-oauth-state"

# Fallback secret for local dev when SUPABASE_JWT_SECRET is unset (AUTH_DISABLED).
_DEV_STATE_SECRET = "ytshorts-dev-state-secret"


class YouTubeNotConnectedError(Exception):
    """Raised when a user has no stored YouTube credentials."""


class YouTubeOAuthConfigError(Exception):
    """Raised when GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET are not configured."""


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def _redirect_uri() -> str:
    return os.getenv(
        "YOUTUBE_OAUTH_REDIRECT_URI",
        "http://localhost:8000/api/v1/youtube/auth/callback",
    )


def _client_config() -> dict:
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise YouTubeOAuthConfigError(
            "GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be set to use "
            "YouTube upload. See .env.example."
        )
    return {
        "web": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": _AUTH_URI,
            "token_uri": _TOKEN_URI,
            "redirect_uris": [_redirect_uri()],
        }
    }


def _relax_oauthlib_env() -> None:
    """Make oauthlib tolerant of localhost http + Google's scope reshuffling.

    Google often returns scopes in a different order / adds ``openid``, which
    oauthlib otherwise rejects with a "Scope has changed" error. And the
    localhost redirect is plain http, which oauthlib blocks unless told the
    transport is acceptable.
    """
    os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")
    if _redirect_uri().startswith("http://"):
        os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")


def is_configured() -> bool:
    return bool(os.getenv("GOOGLE_CLIENT_ID") and os.getenv("GOOGLE_CLIENT_SECRET"))


# ---------------------------------------------------------------------------
# Signed state (CSRF + user-id carrier through the public callback)
# ---------------------------------------------------------------------------

def _state_secret() -> str:
    return os.environ.get("SUPABASE_JWT_SECRET") or _DEV_STATE_SECRET


def sign_state(user_id: str) -> str:
    now = datetime.now(tz=timezone.utc)
    payload = {
        "sub": user_id,
        "aud": _STATE_AUDIENCE,
        "iat": now,
        "exp": now + timedelta(seconds=_STATE_TTL_SECONDS),
    }
    return jwt.encode(payload, _state_secret(), algorithm="HS256")


def verify_state(token: str) -> str:
    """Return the user_id embedded in a valid state token, else raise."""
    payload = jwt.decode(
        token,
        _state_secret(),
        algorithms=["HS256"],
        audience=_STATE_AUDIENCE,
        options={"require": ["sub", "exp", "aud"]},
    )
    return payload["sub"]


# ---------------------------------------------------------------------------
# OAuth flow
# ---------------------------------------------------------------------------

def build_authorization_url(state: str) -> str:
    """Build the Google consent-screen URL for the connect flow."""
    _relax_oauthlib_env()
    from google_auth_oauthlib.flow import Flow

    flow = Flow.from_client_config(
        _client_config(), scopes=SCOPES, redirect_uri=_redirect_uri()
    )
    authorization_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",  # force a refresh token even on re-consent
        state=state,
    )
    return authorization_url


def exchange_code(code: str):
    """Exchange an authorization code for google credentials."""
    _relax_oauthlib_env()
    from google_auth_oauthlib.flow import Flow

    flow = Flow.from_client_config(
        _client_config(), scopes=SCOPES, redirect_uri=_redirect_uri()
    )
    flow.fetch_token(code=code)
    return flow.credentials


# ---------------------------------------------------------------------------
# Credentials <-> stored record
# ---------------------------------------------------------------------------

def _to_naive_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """google.oauth2 Credentials.expiry must be a naive UTC datetime."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def _to_aware_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def credentials_from_record(record: dict):
    """Reconstruct google credentials from a stored credentials record."""
    from google.oauth2.credentials import Credentials

    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    scopes_str = record.get("scopes")
    creds = Credentials(
        token=record.get("access_token"),
        refresh_token=record.get("refresh_token"),
        token_uri=_TOKEN_URI,
        client_id=client_id,
        client_secret=client_secret,
        scopes=scopes_str.split() if scopes_str else SCOPES,
    )
    creds.expiry = _to_naive_utc(record.get("token_expiry"))
    return creds


def fetch_channel_info(credentials) -> Tuple[Optional[str], Optional[str]]:
    """Return (channel_id, channel_title) for the authenticated account."""
    from googleapiclient.discovery import build

    youtube = build("youtube", "v3", credentials=credentials, cache_discovery=False)
    resp = youtube.channels().list(part="snippet", mine=True).execute()
    items = resp.get("items") or []
    if not items:
        return None, None
    item = items[0]
    return item.get("id"), (item.get("snippet") or {}).get("title")


def get_authenticated_youtube(user_id: str):
    """Return an authenticated YouTube Data API client for *user_id*.

    Refreshes the access token (and persists the new token/expiry) when needed.
    Raises YouTubeNotConnectedError if the user has not connected an account.
    """
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    from agents.long_to_shorts.api.youtube_credentials_store import (
        youtube_credentials_store,
    )

    record = youtube_credentials_store.get(user_id)
    if not record or not record.get("refresh_token"):
        raise YouTubeNotConnectedError(
            "No connected YouTube account. Connect YouTube before publishing."
        )

    creds = credentials_from_record(record)
    if not creds.valid:
        creds.refresh(Request())
        youtube_credentials_store.upsert(
            user_id,
            access_token=creds.token,
            token_expiry=_to_aware_utc(creds.expiry),
        )

    return build("youtube", "v3", credentials=creds, cache_discovery=False)


__all__ = [
    "SCOPES",
    "YouTubeNotConnectedError",
    "YouTubeOAuthConfigError",
    "is_configured",
    "sign_state",
    "verify_state",
    "build_authorization_url",
    "exchange_code",
    "credentials_from_record",
    "fetch_channel_info",
    "get_authenticated_youtube",
    "_to_aware_utc",
]
