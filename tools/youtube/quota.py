"""
tools/youtube/quota.py
~~~~~~~~~~~~~~~~~~~~~~~
Shared, thread-safe accounting for the **YouTube Data API v3 daily quota** — the
single choke point every YouTube call charges against, so the background trending
crawler and interactive discovery draw from *one* budget instead of each guessing.

Why this lives in ``tools/`` (not ``api/``): search belongs here, and ``tools/``
imports only ``core/`` — so both the crawler and the API layer can share this
without an upward import.

Quota facts this module encodes:
  * Default budget is **10,000 units/day** (``settings.YOUTUBE_DAILY_QUOTA``),
    resetting at **midnight US-Pacific** — not local midnight.
  * ``search.list`` = **100 units**; ``videos.list`` / channel / playlist = **1**.

Accounting is in-process (a single API server). A persistent cross-process
counter is a documented follow-up.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone, timedelta, date
from typing import Literal

from core.config import settings

logger = logging.getLogger(__name__)

# ── Documented YouTube Data API unit costs (per call) ────────────────────────
COST_SEARCH = 100
COST_VIDEOS_LIST = 1
COST_CHANNELS_LIST = 1
COST_PLAYLIST_ITEMS = 1
COST_COMMENT_THREADS = 1

ErrorKind = Literal["daily_quota", "rate_limit", "transient", "other"]


def _pacific_date() -> date:
    """Today's date in US-Pacific — matches when Google resets the daily quota.

    Uses IANA tz data when available; falls back to a fixed UTC-8 offset (close
    enough for a day-boundary rollover if ``tzdata`` isn't installed on Windows).
    """
    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo("America/Los_Angeles")).date()
    except Exception:  # noqa: BLE001 — tzdata missing; approximate with UTC-8
        return (datetime.now(timezone.utc) - timedelta(hours=8)).date()


class YouTubeQuota:
    """In-process daily unit counter for the YouTube Data API (Pacific reset)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._day = _pacific_date()
        self._used = 0

    def _roll(self) -> None:
        today = _pacific_date()
        if today != self._day:
            self._day, self._used = today, 0

    @property
    def _budget(self) -> int:
        return int(getattr(settings, "YOUTUBE_DAILY_QUOTA", 10000))

    def charge(self, units: int) -> None:
        with self._lock:
            self._roll()
            self._used += max(0, int(units))

    def used(self) -> int:
        with self._lock:
            self._roll()
            return self._used

    def remaining(self) -> int:
        with self._lock:
            self._roll()
            return max(0, self._budget - self._used)

    def can_afford(self, units: int) -> bool:
        return self.remaining() >= max(0, int(units))


# Module singleton — every YouTube call site shares this budget.
youtube_quota = YouTubeQuota()


def classify_http_error(error: Exception) -> ErrorKind:
    """Classify a ``googleapiclient`` ``HttpError`` for retry/backoff decisions.

    Returns:
        - ``"daily_quota"`` — the daily budget is exhausted (``quotaExceeded`` or a
          ``rateLimitExceeded`` whose message mentions "per day"). **Not retryable**
          within the reset window.
        - ``"rate_limit"`` — a short-term per-user/per-100s limit. Retryable with backoff.
        - ``"transient"`` — 5xx / 503 backendError. Retryable with backoff.
        - ``"other"`` — anything else (auth, bad request, not found). Not retryable.
    """
    status = getattr(getattr(error, "resp", None), "status", None)
    try:
        status = int(status) if status is not None else None
    except (TypeError, ValueError):
        status = None

    text = str(error).lower()

    if status in (500, 503) or "backenderror" in text or "internal error" in text:
        return "transient"

    if status == 403 or status == 429:
        # 403 quotaExceeded and 429 rateLimitExceeded overlap in YouTube's usage.
        # The distinguishing signal for the *daily* cap is the "per day" phrasing.
        if "per day" in text or "quotaexceeded" in text or "dailylimitexceeded" in text:
            return "daily_quota"
        if "userratelimitexceeded" in text or "ratelimitexceeded" in text:
            return "rate_limit"
        # Bare 403 without a rate/quota reason is an access/permission error.
        return "daily_quota" if status == 429 else "other"

    return "other"


__all__ = [
    "youtube_quota",
    "YouTubeQuota",
    "classify_http_error",
    "ErrorKind",
    "COST_SEARCH",
    "COST_VIDEOS_LIST",
    "COST_CHANNELS_LIST",
    "COST_PLAYLIST_ITEMS",
    "COST_COMMENT_THREADS",
]
