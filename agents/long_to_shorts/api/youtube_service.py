"""
agents/long_to_shorts/api/youtube_service.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
A clean facade over the scattered YouTube utilities — search/ranking, upload,
retry/idempotency, and (lightweight) quota accounting — so the Autonomous
Publishing Agent talks to ONE interface instead of reaching into
``fetch_trending_videos``, ``youtube_upload_store`` and ``youtube_upload_runner``
directly. It does not reimplement anything: it wraps the existing, battle-tested
pieces (the resumable + idempotent upload runner in particular).

Quota accounting is a pragmatic first cut (in-process, daily reset). Phase 2
turns the budget into hard enforcement + backoff to the cached trending pool.
"""

from __future__ import annotations

import logging
import threading
from typing import List, Optional

from agents.publishing.schemas import DiscoveryRecommendation
from core.exceptions import QuotaExceededError
from tools.youtube.quota import youtube_quota, COST_SEARCH, COST_VIDEOS_LIST

logger = logging.getLogger(__name__)

# Documented YouTube Data API unit costs (per call).
_COST_SEARCH = COST_SEARCH
_COST_VIDEOS_LIST = COST_VIDEOS_LIST


class YouTubeService:
    """Single entry point for the publishing agent's YouTube needs."""

    def __init__(self) -> None:
        # Shared, enforced daily budget — the same counter the search tool and the
        # background trending crawler charge against (tools.youtube.quota), so the
        # crawler's spend is visible here instead of a separate blind tally.
        self._quota = youtube_quota

    # -- discovery ---------------------------------------------------------

    def search_and_rank(
        self,
        query: str,
        *,
        top_n: Optional[int] = None,
        days_ago: Optional[int] = 7,
        user_context: Optional[str] = None,
    ) -> List[DiscoveryRecommendation]:
        """Ranked, explainable source-video recommendations for *query*.

        Quota discipline: a live search costs ~101 units. The underlying search
        tool enforces and charges the shared daily budget itself; here we (a)
        prefer the cached trending pool (0 units) when the budget is already low,
        and (b) catch ``QuotaExceededError`` from the live path and degrade to the
        pool rather than failing the run."""
        cost = _COST_SEARCH + _COST_VIDEOS_LIST
        if self._quota.remaining() < cost:
            logger.warning(
                "YouTube quota low (%d units left < %d); serving discovery from "
                "the cached trending pool.", self._quota.remaining(), cost,
            )
            recs = self._from_pool(query, top_n=top_n, user_context=user_context)
            if recs:
                return recs
            logger.warning("cached trending pool empty; attempting live search")

        from agents.publishing.discovery_agent import discover_candidates, build_recommendations
        from tools.youtube.search import YouTubeSearchTool

        try:
            # A short creator-like prompt is resolved against channel uploads first.
            # Longer/topic prompts retain the existing conversational search path.
            channel_query = _channel_query(query)
            if channel_query:
                latest = YouTubeSearchTool().latest_channel_videos(channel_query, max_results=5)
                if latest:
                    return build_recommendations(
                        query, latest, top_n=top_n or 5, user_context=user_context, use_llm=True
                    )

            return discover_candidates(
                query, top_n=top_n, days_ago=days_ago, user_context=user_context
            )
        except QuotaExceededError:
            logger.warning(
                "YouTube daily quota exhausted during live discovery; serving from "
                "the cached trending pool (0 units)."
            )
            return self._from_pool(query, top_n=top_n, user_context=user_context)

    def fetch_video_context(self, video_url: str) -> dict:
        from tools.youtube.search import YouTubeSearchTool
        return YouTubeSearchTool().fetch_video_context(video_url)

    def _from_pool(
        self, query: str, *, top_n: Optional[int], user_context: Optional[str]
    ) -> List[DiscoveryRecommendation]:
        """Rank the cached trending pool for *query* (0 quota units)."""
        try:
            from agents.long_to_shorts.api.trending_store import trending_store
            from agents.publishing.discovery_agent import build_recommendations

            pool = trending_store.list_pool()
            videos = [v.model_dump() for (v, _dt, _topic) in pool]
            return build_recommendations(
                query, videos, top_n=top_n, user_context=user_context, use_llm=False
            )
        except Exception as exc:  # noqa: BLE001 — backoff must never crash discovery
            logger.warning("cached-pool discovery failed: %s", exc)
            return []

    # -- upload ------------------------------------------------------------

    def run_upload(
        self,
        *,
        clip_job_id: str,
        clip_id: str,
        user_id: str,
        title: str,
        description: str = "",
        tags: Optional[List[str]] = None,
        privacy_status: str = "private",
        category_id: str = "22",
    ):
        """Create an upload job and drive it to completion synchronously (this
        already runs on a worker thread). Reuses the resumable + idempotent
        upload runner, so a retry never double-publishes. Returns the final
        ``YouTubeUploadJob``."""
        from agents.long_to_shorts.api.models import YouTubeUploadRequest
        from agents.long_to_shorts.api.youtube_upload_runner import run_youtube_upload_job
        from agents.long_to_shorts.api.youtube_upload_store import youtube_upload_store

        req = YouTubeUploadRequest(
            parent_job_id=clip_job_id,
            clip_id=clip_id,
            title=title[:100],
            description=description or "",
            tags=tags or [],
            privacy_status=privacy_status,  # forced to private for unverified apps downstream
            category_id=category_id,
        )
        upload_job = youtube_upload_store.create(
            user_id=user_id, parent_job_id=clip_job_id, clip_id=clip_id,
            title=req.title, privacy_status=req.privacy_status,
        )
        run_youtube_upload_job(upload_job.upload_id, req, user_id)  # blocks; persists result
        return youtube_upload_store.get(upload_job.upload_id)

    def is_connected(self, user_id: str) -> bool:
        try:
            from agents.long_to_shorts.api.youtube_credentials_store import (
                youtube_credentials_store,
            )
            record = youtube_credentials_store.get(user_id)
            return bool(record and record.get("refresh_token"))
        except Exception:  # noqa: BLE001
            return False

    # -- quota -------------------------------------------------------------

    def quota_remaining(self) -> int:
        return self._quota.remaining()

    def quota_used(self) -> int:
        return self._quota.used()


_service: Optional[YouTubeService] = None
_service_lock = threading.Lock()


def get_youtube_service() -> YouTubeService:
    global _service
    if _service is None:
        with _service_lock:
            if _service is None:
                _service = YouTubeService()
    return _service


__all__ = ["YouTubeService", "get_youtube_service"]


def _channel_query(query: str) -> Optional[str]:
    """Extract a likely creator name from prompts such as 'latest from Speed'."""
    import re
    text = (query or "").strip()
    text = re.sub(r"\b(latest|newest|recent|videos?|uploads?|from|channel|on|the)\b", " ", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip(" -,:;")
    if not text or len(text.split()) > 3:
        return None
    if re.search(r"\b(ai|tech|news|gaming|podcast|interview|tutorial|clips?|highlights?)\b", text, re.I):
        return None
    return text
