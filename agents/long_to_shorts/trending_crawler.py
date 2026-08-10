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
from core.exceptions import QuotaExceededError
from tools.youtube.quota import youtube_quota

logger = logging.getLogger(__name__)

# Rotating window offset so successive crawls cover different topics instead of
# re-spending on all of them every cycle (module-level; the crawler runs in one
# long-lived worker process).
_cycle_offset = 0


def crawl_trending_pool() -> dict[str, int]:
    """Crawl trending videos for a rotating subset of topics and warm the pool.

    Returns {topic: count}. Never raises: a missing YouTube key short-circuits to
    an empty summary, and a single topic's failure is logged and skipped so the
    rest still run.

    Quota discipline: the crawler is a background best-effort consumer, so it
    yields to interactive discovery. It skips entirely when the shared daily
    budget is below ``YT_QUOTA_RESERVE`` and stops mid-cycle if the reserve is
    hit, keeping ~1 search query per topic and only a rotating slice of topics
    per cycle to keep per-crawl cost low.
    """
    global _cycle_offset

    if not settings.YT_API_KEY:
        logger.info("trending crawl skipped — YT_API_KEY is not configured")
        return {}

    reserve = int(getattr(settings, "YT_QUOTA_RESERVE", 2000))
    if youtube_quota.remaining() < reserve:
        logger.info(
            "trending crawl skipped — %d quota unit(s) left is below the "
            "YT_QUOTA_RESERVE of %d reserved for interactive discovery",
            youtube_quota.remaining(), reserve,
        )
        return {}

    use_llm = os.getenv("TRENDING_CRAWLER_LLM", "false").lower() in ("1", "true", "yes")

    # Crawl a rotating window of topics each cycle rather than all of them.
    all_topics = get_topic_keys()
    per_cycle = max(1, int(os.getenv("TRENDING_CRAWLER_TOPICS_PER_CYCLE", "3")))
    if per_cycle >= len(all_topics):
        topics = all_topics
    else:
        start = _cycle_offset % len(all_topics)
        topics = [all_topics[(start + i) % len(all_topics)] for i in range(per_cycle)]
    _cycle_offset = (_cycle_offset + len(topics)) % max(1, len(all_topics))

    summary: dict[str, int] = {}
    for topic in topics:
        # Stop before spending into the interactive reserve mid-cycle.
        if youtube_quota.remaining() < reserve:
            logger.info("trending crawl stopping early — quota reserve reached")
            break
        try:
            result = fetch_trending_videos(
                topics=[topic],
                order="date",  # surface what's *new*
                days_ago=7,
                max_results_per_query=6,
                queries_per_topic=1,  # one search query per topic (100 units)
                use_llm_queries=use_llm,
            )
            videos = [DiscoverVideo(**v) for v in result.get("youtube_results", [])]
            trending_store.upsert_videos(videos, topic)
            summary[topic] = len(videos)
        except QuotaExceededError:
            logger.info("trending crawl stopping — YouTube daily quota exhausted")
            break
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
