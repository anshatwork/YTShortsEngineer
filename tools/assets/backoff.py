"""
tools/assets/backoff.py
~~~~~~~~~~~~~~~~~~~~~~~~~
Resilience helpers shared by every asset source: an HTTP GET with exponential
backoff for transient failures, and a TTL **negative cache** so a persistently
broken asset (a track whose download 500s, a rate-limited window) is remembered
and skipped instead of being re-fetched on every refresh cycle.

Why this exists: the music-cache warmer walks every theme on a timer, and popular
tracks recur across themes and cycles. Without a negative cache, one broken
Jamendo download (e.g. a storage-node 500) gets retried forever, spamming logs
and hammering the source. The layer stays in ``tools/assets`` (imports only
``core``/stdlib), so all sources share one policy.

Tunables (env, with defaults):
  * ``ASSET_MAX_RETRIES`` (2) — retries for transient 5xx / 429 / connection errors.
  * ``ASSET_BACKOFF_BASE_SECONDS`` (0.5) — base for ``base * 2**attempt + jitter``.
  * ``ASSET_NEGATIVE_CACHE_TTL_HOURS`` (6) — how long a bad key stays blocklisted.
"""

from __future__ import annotations

import logging
import os
import random
import threading
import time
from typing import Any, Dict, Optional

import requests

logger = logging.getLogger(__name__)

# HTTP statuses worth retrying: rate-limit + transient server/gateway errors.
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}

_neg_lock = threading.Lock()
_neg_cache: Dict[str, float] = {}  # key -> epoch when the blocklist entry expires


# ── Negative cache ───────────────────────────────────────────────────────────

def _neg_ttl_seconds() -> float:
    try:
        return max(0.0, float(os.getenv("ASSET_NEGATIVE_CACHE_TTL_HOURS", "6"))) * 3600.0
    except ValueError:
        return 6 * 3600.0


def mark_bad(key: str) -> None:
    """Blocklist *key* (an ``Asset.cache_key``) for the negative-cache TTL."""
    ttl = _neg_ttl_seconds()
    if ttl <= 0 or not key:
        return
    with _neg_lock:
        _neg_cache[key] = time.time() + ttl


def is_bad(key: str) -> bool:
    """True while *key* is blocklisted; expired entries self-evict."""
    if not key:
        return False
    with _neg_lock:
        expiry = _neg_cache.get(key)
        if expiry is None:
            return False
        if time.time() >= expiry:
            _neg_cache.pop(key, None)
            return False
        return True


def clear_negative_cache() -> None:
    """Drop all blocklist entries (test seam)."""
    with _neg_lock:
        _neg_cache.clear()


# ── HTTP GET with backoff ────────────────────────────────────────────────────

def _max_retries() -> int:
    try:
        return max(0, int(os.getenv("ASSET_MAX_RETRIES", "2")))
    except ValueError:
        return 2


def _backoff_base() -> float:
    try:
        return max(0.0, float(os.getenv("ASSET_BACKOFF_BASE_SECONDS", "0.5")))
    except ValueError:
        return 0.5


def get_with_backoff(
    url: str,
    *,
    timeout: float,
    params: Optional[Dict[str, Any]] = None,
) -> requests.Response:
    """``requests.get`` that retries transient failures with exp backoff + jitter.

    Retries on 429/5xx and connection/timeout errors up to ``ASSET_MAX_RETRIES``;
    raises (via ``raise_for_status`` or the underlying exception) once retries are
    exhausted or on a non-retryable status. Callers decide whether to
    :func:`mark_bad` the asset on failure.
    """
    retries = _max_retries()
    base = _backoff_base()

    for attempt in range(retries + 1):
        try:
            resp = requests.get(url, params=params, timeout=timeout)
            if resp.status_code in _RETRYABLE_STATUS and attempt < retries:
                delay = base * (2 ** attempt) + random.uniform(0.0, base)
                logger.debug(
                    "asset GET %s -> %s (attempt %d/%d); backing off %.1fs",
                    url, resp.status_code, attempt + 1, retries, delay,
                )
                time.sleep(delay)
                continue
            resp.raise_for_status()
            return resp
        except (requests.Timeout, requests.ConnectionError) as exc:
            if attempt < retries:
                delay = base * (2 ** attempt) + random.uniform(0.0, base)
                logger.debug(
                    "asset GET %s failed (%s, attempt %d/%d); backing off %.1fs",
                    url, exc.__class__.__name__, attempt + 1, retries, delay,
                )
                time.sleep(delay)
                continue
            raise

    # Retryable status never cleared within the retry budget — do a final
    # attempt so the caller gets a definitive response/raise.
    resp = requests.get(url, params=params, timeout=timeout)
    resp.raise_for_status()
    return resp


__all__ = [
    "get_with_backoff",
    "mark_bad",
    "is_bad",
    "clear_negative_cache",
]
