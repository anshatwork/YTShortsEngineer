"""
agents/publishing/discovery_agent.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Stage 1 — Automatic YouTube discovery. Turns a natural-language request into a
ranked, **explainable** list of source-video recommendations for the first human
gate. Reuses the existing search + ranking machinery rather than reinventing it:

  * search + metadata enrichment → ``tools.youtube.search`` (via
    ``fetch_trending_videos``), which also dedupes across the query;
  * global re-ranking (keyword + popularity + engagement) → the same
    ``_rank_videos`` the /discover surface uses.

On top of that it adds the explainability the brief asks for — why each video was
selected, its expected clip quality, hook potential and topic relevance —
computed deterministically and optionally sharpened by a small-model LLM pass
(best-effort, cached, degrade-not-fail).
"""

from __future__ import annotations

import logging
import math
import os
import re
from typing import Any, Dict, List, Optional

from agents.publishing.schemas import (
    DiscoveryExplanation,
    DiscoveryRecommendation,
    VideoCandidate,
)
from core.inference import Priority

logger = logging.getLogger(__name__)

_DISCOVERY_CACHE_VERSION = 1
_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOP = frozenset({
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with", "is",
    "are", "how", "what", "why", "vs", "best", "today", "todays", "latest", "new",
})

_DISCOVERY_SYSTEM = """\
You assess whether a long-form YouTube video is good raw material for viral
vertical Shorts. Given a creator's request and one video's metadata, judge:
- why_selected: one concrete sentence on why this video fits the request and
  would yield strong Shorts.
- expected_clip_quality: 'low' | 'medium' | 'high'.
- hook_potential: 0-10 (how likely it contains scroll-stopping moments).
- topic_relevance: 0-10 (fit to the request).
Return ONLY the structured object."""

_DISCOVERY_USER = """\
Creator request: {query}
{context}
Video:
- title: {title}
- channel: {channel}
- duration_minutes: {minutes:.0f}
- views: {views}
- description: {description}"""


def _tokens(text: str) -> set:
    return {t for t in _TOKEN_RE.findall((text or "").lower()) if t not in _STOP}


def _default_top_n() -> int:
    return max(1, int(os.getenv("PUBLISH_DISCOVER_TOP_N", "5")))


def _to_candidate(v: Dict[str, Any]) -> VideoCandidate:
    return VideoCandidate(
        video_id=str(v.get("video_id") or v.get("id") or ""),
        title=v.get("title", ""),
        url=v.get("url", ""),
        channel=v.get("channel", ""),
        description=v.get("description", ""),
        thumbnail=v.get("thumbnail", ""),
        published_at=v.get("published_at", ""),
        duration_seconds=int(v.get("duration_seconds", 0) or 0),
        duration_label=v.get("duration_label", ""),
        view_count=int(v.get("view_count", 0) or 0),
        like_count=int(v.get("like_count", 0) or 0),
        comment_count=int(v.get("comment_count", 0) or 0),
    )


def _deterministic_scores(query: str, v: VideoCandidate) -> Dict[str, float]:
    q_tokens = _tokens(query)
    title_tokens = _tokens(v.title)
    desc_tokens = _tokens(v.description)
    overlap = len(q_tokens & title_tokens) * 2 + len(q_tokens & desc_tokens)
    topic_relevance = min(10.0, 4.0 + overlap) if q_tokens else 5.0
    # Engagement + reach heuristic for hook potential.
    views = max(1, v.view_count)
    engagement = (v.like_count + v.comment_count) / views
    hook = 3.0 + min(4.0, math.log1p(v.view_count) / 3.0) + min(3.0, engagement * 500)
    minutes = v.duration_seconds / 60.0
    return {
        "keyword_overlap": float(overlap),
        "topic_relevance": round(topic_relevance, 1),
        "hook_potential": round(min(10.0, hook), 1),
        "minutes": round(minutes, 1),
    }


def _expected_quality(minutes: float) -> str:
    if 15 <= minutes <= 90:
        return "high"
    if minutes < 8 or minutes > 150:
        return "low"
    return "medium"


def _llm_explain(query: str, v: VideoCandidate, user_context: Optional[str]) -> Optional[DiscoveryExplanation]:
    try:
        from tools.llm.inference import get_inference_client

        payload = _DISCOVERY_USER.format(
            query=query,
            context=f"Creator guidance: {user_context}" if user_context else "",
            title=v.title, channel=v.channel, minutes=v.duration_seconds / 60.0,
            views=v.view_count, description=(v.description or "")[:600],
        )
        return get_inference_client().parse(
            payload, DiscoveryExplanation, system=_DISCOVERY_SYSTEM,
            task_class="discovery", priority=Priority.INTERACTIVE,
            cache_op="publish_discovery", cache_version=_DISCOVERY_CACHE_VERSION,
        )
    except Exception as exc:  # noqa: BLE001 — deterministic fallback
        logger.debug("discovery LLM explain failed for %s (%s)", v.video_id, exc)
        return None


def discover_candidates(
    query: str,
    *,
    top_n: Optional[int] = None,
    days_ago: Optional[int] = 7,
    user_context: Optional[str] = None,
    use_llm: bool = True,
) -> List[DiscoveryRecommendation]:
    """Search, rank, and explain candidate source videos for *query*."""
    from agents.long_to_shorts.fetch_trending_videos import fetch_trending_videos

    top_n = top_n or _default_top_n()
    result = fetch_trending_videos(
        topic_overrides=[query],
        keywords=[query],
        days_ago=days_ago,
        order="relevance",
        max_results_per_query=max(top_n * 3, 10),
        max_total=top_n,
        long_form_only=True,
        min_duration_seconds=600,
    )
    videos = result.get("youtube_results") or []
    return build_recommendations(
        query, videos, top_n=top_n, user_context=user_context, use_llm=use_llm
    )


def build_recommendations(
    query: str,
    videos: List[dict],
    *,
    top_n: Optional[int] = None,
    user_context: Optional[str] = None,
    use_llm: bool = True,
) -> List[DiscoveryRecommendation]:
    """Rank + explain a list of candidate video dicts (shared by the live-search
    path and the quota-backoff cached-pool path in youtube_service)."""
    top_n = top_n or _default_top_n()
    if not videos:
        logger.info("discovery: no candidates for query=%r", query)
        return []

    recs: List[DiscoveryRecommendation] = []
    for i, raw in enumerate(videos[:top_n]):
        cand = _to_candidate(raw)
        scores = _deterministic_scores(query, cand)
        hook = int(round(scores["hook_potential"]))
        relevance = int(round(scores["topic_relevance"]))
        quality = _expected_quality(scores["minutes"])
        why = (
            f"Matches your request with {int(scores['keyword_overlap'])} keyword hit(s); "
            f"{cand.view_count:,} views, ~{scores['minutes']:.0f} min — {quality} clip material."
        )

        if use_llm:
            ex = _llm_explain(query, cand, user_context)
            if ex is not None:
                why = ex.why_selected or why
                quality = ex.expected_clip_quality or quality
                hook = ex.hook_potential
                relevance = ex.topic_relevance

        recs.append(DiscoveryRecommendation(
            video=cand, rank=i + 1, why_selected=why,
            expected_clip_quality=quality, hook_potential=hook,
            topic_relevance=relevance, scores=scores,
        ))
    logger.info("discovery: %d recommendation(s) for query=%r", len(recs), query)
    return recs


__all__ = ["discover_candidates", "build_recommendations"]
