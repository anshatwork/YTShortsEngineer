"""
agents/long_to_shorts/trending_crawler.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Background crawler that keeps a global pool of currently-trending long-form
videos warm. Modeled on tools/assets/refresh.refresh_music_cache: a blocking
function run off the event loop by the task queue (see app._trending_crawler_loop),
iterating the curated topic bank and upserting fresh results into the trending
store. The per-user personalization/ranking happens later, on request, in
discover_routes — this just fills the pool.
"""

from __future__ import annotations

import logging
import os

from agents.long_to_shorts.api.models import DiscoverVideo
from agents.long_to_shorts.api.trending_store import trending_store
from agents.long_to_shorts.fetch_trending_videos import (
    fetch_trending_videos,
    get_topic_keys,
)
from core.config import settings

logger = logging.getLogger(__name__)


def crawl_trending_pool() -> dict[str, int]:
    """Crawl trending videos per topic and warm the pool. Returns {topic: count}.

    Never raises: a missing YouTube key short-circuits to an empty summary, and
    a single topic's failure is logged and skipped so the rest still run.
    """
    if not settings.YT_API_KEY:
        logger.info("trending crawl skipped — YT_API_KEY is not configured")
        return {}

    use_llm = os.getenv("TRENDING_CRAWLER_LLM", "false").lower() in ("1", "true", "yes")

    summary: dict[str, int] = {}
    for topic in get_topic_keys():
        try:
            result = fetch_trending_videos(
                topics=[topic],
                order="date",  # surface what's *new*
                days_ago=7,
                max_results_per_query=6,
                use_llm_queries=use_llm,
            )
            videos = [DiscoverVideo(**v) for v in result.get("youtube_results", [])]
            trending_store.upsert_videos(videos, topic)
            summary[topic] = len(videos)
        except Exception as exc:  # noqa: BLE001 — one topic failing shouldn't kill the crawl
            logger.warning("trending crawl failed for topic '%s': %s", topic, exc)
            summary[topic] = 0

    try:
        trending_store.prune()
    except Exception:  # noqa: BLE001
        logger.exception("trending pool prune failed")

    total = sum(summary.values())
    logger.info(
        "trending crawl complete — %d video(s) across %d topic(s): %s",
        total, len(summary), summary,
    )
    return summary


__all__ = ["crawl_trending_pool"]
