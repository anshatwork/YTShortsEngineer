"""
tools/assets/retrieval.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~
The public entry point of the asset layer: :func:`retrieve`.

Strategy = **cache-first + live fallback with a freshness TTL**:

1. If the bucket's cache is fresh (>= ``ASSET_MIN_POOL`` assets, newest within
   ``ASSET_FRESHNESS_TTL_HOURS``), skip the network entirely.
2. Otherwise discover live across the registered sources, download the top
   candidates, and put them in the cache.
3. Rank the (now-warm) pool and return the best ``k``.

"latest" is honored twice: each source is asked to sort by recency, and local
ranking weights freshness/recency highest when ``query.order == "latest"``.

:func:`record_feedback` is a stub today — it just logs — but it is the seam
where per-user personalization will plug in later (the ``user_id`` and
``discovered_at`` fields already exist on the models, so no schema rework).
"""

from __future__ import annotations

import logging
import os
import time
from typing import Iterable, List, Optional

from tools.assets.models import Asset, AssetQuery, AssetType
from tools.assets.registry import get_sources
from tools.assets.store import AssetStore

logger = logging.getLogger(__name__)

_store = AssetStore()


def _ttl_seconds() -> float:
    return float(os.getenv("ASSET_FRESHNESS_TTL_HOURS", "24")) * 3600.0


def _min_pool() -> int:
    return int(os.getenv("ASSET_MIN_POOL", "5"))


# ---------------------------------------------------------------------------
# Live discovery
# ---------------------------------------------------------------------------

def _discover_live(query: AssetQuery) -> None:
    """Discover from registered sources and warm the cache for the bucket.

    Sources are tried in registration order. We download up to ``query.limit``
    fresh (not-already-cached) candidates across all sources, then run an LRU
    cleanup so the cache stays under its size cap.
    """
    sources = get_sources(query.asset_type)
    if not sources:
        logger.warning(
            "no available sources for asset type %s (check API keys)",
            query.asset_type.value,
        )
        return

    existing = {a.cache_key for a in _store.get(query.asset_type, query.bucket)}
    downloaded = 0

    for source in sources:
        if downloaded >= query.limit:
            break
        try:
            candidates = source.discover(query)
        except Exception as exc:  # noqa: BLE001 — one bad source shouldn't break discovery
            logger.warning("source '%s' discover failed: %s", source.name, exc)
            continue

        for asset in candidates:
            if downloaded >= query.limit:
                break
            if asset.cache_key in existing:
                continue
            local = source.fetch(asset)
            if not local:
                continue
            asset.local_path = local
            asset.discovered_at = time.time()
            try:
                _store.put(asset)
                existing.add(asset.cache_key)
                downloaded += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning("failed to cache %s: %s", asset.cache_key, exc)

    if downloaded:
        logger.info(
            "discovered %d new %s asset(s) for bucket '%s'",
            downloaded, query.asset_type.value, query.bucket,
        )
        _store.cleanup(query.asset_type)


# ---------------------------------------------------------------------------
# Ranking
# ---------------------------------------------------------------------------

def _normalize(values: Iterable[float]) -> List[float]:
    vals = list(values)
    if not vals:
        return []
    lo, hi = min(vals), max(vals)
    if hi - lo < 1e-9:
        return [0.5 for _ in vals]
    return [(v - lo) / (hi - lo) for v in vals]


def _keyword_overlap(asset: Asset, keywords: List[str]) -> float:
    if not keywords:
        return 0.0
    haystack = " ".join([asset.title or "", *asset.tags]).lower()
    hits = sum(1 for kw in keywords if kw and kw.lower() in haystack)
    return hits / len(keywords)


def _personalization_bias(user_id: Optional[str], asset: Asset) -> float:
    """Per-user ranking nudge. Deferred — always 0 in v1.

    Hook for later: bias by the user's previously kept/rejected assets recorded
    via :func:`record_feedback`.
    """
    return 0.0


def _rank(pool: List[Asset], query: AssetQuery) -> List[Asset]:
    """Score and sort the pool. Weights shift with ``query.order``."""
    if not pool:
        return []

    # Freshness from our discovered_at (higher = more recent).
    fresh_norm = _normalize(a.discovered_at for a in pool)
    pop_norm = _normalize(a.popularity for a in pool)
    rel = [_keyword_overlap(a, query.keywords) for a in pool]

    if query.order == "popular":
        w_fresh, w_pop, w_rel = 0.2, 0.6, 0.2
    elif query.order == "relevance":
        w_fresh, w_pop, w_rel = 0.2, 0.2, 0.6
    else:  # "latest" (default)
        w_fresh, w_pop, w_rel = 0.6, 0.2, 0.2

    scored = []
    for asset, f, p, r in zip(pool, fresh_norm, pop_norm, rel):
        score = (
            w_fresh * f
            + w_pop * p
            + w_rel * r
            + _personalization_bias(query.user_id, asset)
        )
        scored.append((score, asset))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [a for _, a in scored]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def retrieve(query: AssetQuery, k: int = 1) -> List[Asset]:
    """Return up to *k* best assets for *query*, refreshing the cache if stale.

    Cache-first: only hits the network when the bucket is empty/stale. Safe to
    call per-clip — same-bucket calls within a run reuse the warm cache.
    """
    ttl, min_pool = _ttl_seconds(), _min_pool()
    if not _store.is_fresh(query.asset_type, query.bucket, ttl, min_pool):
        _discover_live(query)

    pool = _store.get(query.asset_type, query.bucket)
    ranked = _rank(pool, query)
    return ranked[:k]


def record_feedback(user_id: Optional[str], asset: Asset, event: str) -> None:
    """Record that a user used/kept/rejected an asset.

    Stub for v1 (logs only). The personalization layer will persist these
    events and feed :func:`_personalization_bias`.
    """
    logger.info(
        "asset feedback: user=%s event=%s asset=%s",
        user_id or "?", event, asset.cache_key,
    )


__all__ = ["retrieve", "record_feedback"]
