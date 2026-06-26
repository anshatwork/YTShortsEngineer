"""
agents/long_to_shorts/api/discover_routes.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
FastAPI router for trending-video discovery — the content-sourcing front door.

Endpoints
---------
    GET   /topics    List the curated topic keys (for UI chips).
    POST  /          Search trending long-form videos by topic + free-text, or by a
                     conversational natural-language request (LLM-interpreted).

Unlike the clip pipeline, discovery is synchronous: a YouTube search of a few
queries returns in a second or two, so there is no background job here.
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status

from agents.long_to_shorts.api.auth import get_current_user_id
from agents.long_to_shorts.api.job_store import job_store
from agents.long_to_shorts.api.models import (
    DiscoverInterpretation,
    DiscoverRequest,
    DiscoverResponse,
    DiscoverSuggestion,
    DiscoverSuggestionsResponse,
    DiscoverTopicsResponse,
    DiscoverVideo,
    UserInterestProfile,
)
from agents.long_to_shorts.api.trending_store import trending_store
from agents.long_to_shorts.fetch_trending_videos import (
    fetch_trending_videos,
    get_topic_keys,
)
from core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()

# Absolute floor: never surface clips shorter than this, but otherwise honor
# whatever window the user asks for (short-form is allowed).
_MIN_DURATION_FLOOR_SECONDS = 30

# At or above this we flip on YouTube's `videoDuration=long` filter as a search
# optimization — it's only an optimization, not an invariant.
_LONG_FORM_THRESHOLD_SECONDS = 1200


def interpret_discover_query(text: str, topic_keys: list[str]) -> DiscoverInterpretation:
    """Translate a natural-language discovery request into structured search params.

    Uses the configured LLM provider's structured-output ``parse`` (see
    ``tools/llm``). On *any* failure — no API key, network error, schema-parse
    failure — falls back to treating the raw text as a single keyword query so the
    search still proceeds. Never raises.
    """
    system = (
        "You are a query-understanding engine for a YouTube video discovery tool. "
        "Translate the user's natural-language request into structured search "
        "parameters. Extract topic, intent, recency AND duration — be generous so the "
        "search returns plenty of candidates rather than too few.\n\n"
        f"Available curated topic keys: {', '.join(topic_keys)}.\n\n"
        "Rules:\n"
        "- `topics`: include any curated topic key that clearly matches; otherwise "
        "leave empty (most real-world requests won't match a curated key).\n"
        "- `custom_queries`: 3-6 concrete, varied YouTube search phrases that cover the "
        "request from different angles (synonyms, phrasings people actually search). "
        "Expand vague nouns into searchable phrases — e.g. 'fifa world cup matches' → "
        "['fifa world cup best matches', 'fifa world cup match highlights', "
        "'fifa world cup full match', 'world cup greatest games']. Always provide at "
        "least 3 queries unless a curated topic fully covers it.\n"
        "- `order`: 'viewCount' for trending/popular/most-viewed/best, 'date' for "
        "newest/latest, otherwise 'relevance'.\n"
        "- `days_ago`: ONLY set when the request implies recency (latest, this week, "
        "this month, 2024, trending now). Map 'this week'≈7, 'this month'≈30, "
        "'this year'≈365. For evergreen or historical topics (past events, tutorials, "
        "'best of all time', sports classics) set days_ago to null — no time limit.\n"
        "- Duration window in minutes — extract literally and honor it even if short: "
        "'less than/under 10 minutes' → max_duration_minutes=10; 'under an hour' → "
        "max_duration_minutes=60; 'over an hour'/'long' → min_duration_minutes=60; "
        "'short' → max_duration_minutes=10; '20 to 40 minutes' → min 20, max 40. "
        "Leave both null when duration isn't mentioned.\n"
        "- `summary`: one line starting with 'Understood: ' recapping topic, recency "
        "and duration in plain words."
    )
    try:
        from tools.llm import get_llm

        interp = get_llm().parse(text, DiscoverInterpretation, system=system)
        # Guard against the model inventing topic keys outside the bank.
        interp.topics = [t for t in interp.topics if t in topic_keys]
        if not interp.summary:
            interp.summary = f"Understood: {text}"
        return interp
    except Exception as exc:  # noqa: BLE001 — degrade gracefully to keyword search
        logger.warning(
            "Conversational query interpretation failed (%s); "
            "falling back to raw keyword search.", exc, exc_info=True,
        )
        return DiscoverInterpretation(
            custom_queries=[text],
            summary=f"Understood (basic search): {text}",
        )


@router.get(
    "/topics",
    response_model=DiscoverTopicsResponse,
    summary="List curated topic keys for discovery",
)
async def list_topics(
    user_id: str = Depends(get_current_user_id),
) -> DiscoverTopicsResponse:
    return DiscoverTopicsResponse(topics=get_topic_keys())


@router.post(
    "",
    response_model=DiscoverResponse,
    summary="Search trending long-form videos",
    description=(
        "Combines sampled queries from the curated topic bank with any free-text "
        "`custom_queries`, searches YouTube for long-form videos (>20 min), and "
        "returns ranked candidates with rich metadata."
    ),
)
def discover(
    body: DiscoverRequest,
    user_id: str = Depends(get_current_user_id),
) -> DiscoverResponse:
    conversational = (body.conversational_query or "").strip()
    if not body.topics and not body.custom_queries and not conversational:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Provide at least one of 'topics', 'custom_queries' or "
            "'conversational_query'.",
        )
    if not settings.YT_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="YouTube search is unavailable — YT_API_KEY is not configured.",
        )

    # Resolve the effective search parameters. A conversational query is
    # LLM-interpreted and is authoritative for the scalar controls (order /
    # recency / duration) — the manual filter widgets are a read-out of what was
    # understood, so the user goes manual by clearing the box. Any topic chips or
    # keywords the user added on top are still unioned in.
    topics = list(body.topics)
    custom_queries = list(body.custom_queries)
    order = body.order
    days_ago: int | None = body.days_ago
    min_minutes = body.min_duration_minutes
    max_minutes = body.max_duration_minutes
    interpretation: DiscoverInterpretation | None = None

    if conversational:
        interpretation = interpret_discover_query(conversational, get_topic_keys())
        topics = list(dict.fromkeys(topics + interpretation.topics))
        custom_queries = list(dict.fromkeys(custom_queries + interpretation.custom_queries))
        order = interpretation.order
        days_ago = interpretation.days_ago  # may be None → no recency limit
        min_minutes = interpretation.min_duration_minutes
        max_minutes = interpretation.max_duration_minutes

    # Duration regime. We honor whatever window the user asks for, only flooring
    # the minimum at _MIN_DURATION_FLOOR_SECONDS (30s) so we never surface
    # unclippable micro-clips. No long-form default: with no window given we
    # return anything >= 30s. The long-form YouTube filter is just a search
    # optimization, flipped on only when the requested minimum is genuinely long.
    min_seconds = max(_MIN_DURATION_FLOOR_SECONDS, (min_minutes or 0) * 60)
    max_seconds = max_minutes * 60 if max_minutes else None
    long_form_only = min_seconds >= _LONG_FORM_THRESHOLD_SECONDS

    # Conversational searches cast a wider net (more results per query) so a
    # broad ask like "fifa world cup matches" returns plenty of candidates.
    max_per_query = max(body.max_results_per_query, 8) if conversational else body.max_results_per_query

    # When the user selects topic chips, sample the curated bank for those
    # topics and append any typed keywords. When no topic is selected, the typed
    # keywords drive the search exclusively (topic_overrides skips the bank) —
    # otherwise an empty topics list defaults to *all* topics and drowns out the
    # keywords the user actually typed.
    if topics:
        fetch_kwargs = dict(
            topics=topics,
            extra_queries=custom_queries or None,
        )
    else:
        fetch_kwargs = dict(topic_overrides=custom_queries)

    result = fetch_trending_videos(
        days_ago=days_ago,
        max_results_per_query=max_per_query,
        order=order,
        keywords=custom_queries or None,
        long_form_only=long_form_only,
        min_duration_seconds=min_seconds,
        max_duration_seconds=max_seconds,
        **fetch_kwargs,
    )

    videos = [DiscoverVideo(**v) for v in result["youtube_results"]]
    logger.info(
        "Discover — user=%s conversational=%r topics=%s custom=%s "
        "duration=%ds-%s long_form=%s -> %d videos",
        user_id, conversational or None, topics, custom_queries,
        min_seconds, f"{max_seconds}s" if max_seconds else "∞",
        long_form_only, len(videos),
    )
    return DiscoverResponse(
        videos=videos,
        queries_used=result["queries_used"],
        total=len(videos),
        interpretation=interpretation,
    )


# ---------------------------------------------------------------------------
# Personalized trending suggestions
# ---------------------------------------------------------------------------

# Common words to ignore when deriving keywords from history / ranking.
_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with", "how",
    "what", "why", "this", "that", "is", "are", "your", "you", "best", "video",
    "full", "part", "ep", "episode", "vs", "2024", "2025", "2026",
}

_MAX_SUGGESTIONS = 12


def _tokenize(text: str) -> list[str]:
    """Lowercase word tokens (>=3 chars), stopwords removed."""
    return [
        w for w in re.findall(r"[a-z0-9]+", (text or "").lower())
        if len(w) >= 3 and w not in _STOPWORDS
    ]


def _history_blob(jobs) -> str:
    """Flatten a user's job history into a text blob for interest inference."""
    parts: list[str] = []
    for job in jobs:
        if getattr(job, "video_title", None):
            parts.append(job.video_title)
        for clip in (getattr(job, "clips", None) or []):
            if clip.title:
                parts.append(clip.title)
            if clip.summary:
                parts.append(clip.summary)
            if clip.hashtags:
                parts.extend(clip.hashtags)
    return " · ".join(parts)


def interpret_user_interests(jobs) -> UserInterestProfile:
    """Infer a user's content interests from their clip-job history.

    Uses the configured LLM's structured-output ``parse`` (like
    ``interpret_discover_query``). On any failure — no key, network, parse error
    — falls back to the most frequent history tokens. Never raises. Empty history
    yields an empty profile (the caller then ranks by global popularity).
    """
    # Cap the blob so a long history can't push the model's structured output
    # past its token budget (which truncates the JSON and trips parse).
    blob = _history_blob(jobs)[:4000]
    if not blob.strip():
        return UserInterestProfile(summary="No history yet — showing what's trending.")

    system = (
        "You profile a short-form video creator from the titles, summaries and "
        "hashtags of clips they've made. Infer what they tend to cover.\n\n"
        f"Available broad topics: {', '.join(get_topic_keys())}.\n\n"
        "Rules:\n"
        "- `keywords`: 3-6 short topic phrases (genres, subjects, niches) the "
        "creator clearly focuses on — drawn from the history, generalized a little. "
        "Keep each phrase under 5 words.\n"
        "- `topics`: any broad topics above that fit; else leave empty.\n"
        "- `summary`: one plain-language line describing this creator's focus."
    )
    try:
        from tools.llm import get_llm

        profile = get_llm().parse(blob, UserInterestProfile, system=system)
        profile.topics = [t for t in profile.topics if t in get_topic_keys()]
        if not profile.keywords:
            profile.keywords = [w for w, _ in Counter(_tokenize(blob)).most_common(8)]
        if not profile.summary:
            profile.summary = "Based on your recent clips."
        return profile
    except Exception as exc:  # noqa: BLE001 — degrade to frequency-based keywords
        logger.warning(
            "User interest interpretation failed (%s); using token frequency.",
            exc, exc_info=True,
        )
        keywords = [w for w, _ in Counter(_tokenize(blob)).most_common(8)]
        return UserInterestProfile(
            keywords=keywords,
            summary="Based on your recent clips.",
        )


def _rank_pool(
    pool: list[tuple[DiscoverVideo, datetime, str]],
    profile: UserInterestProfile,
) -> list[DiscoverSuggestion]:
    """Rank pooled videos by keyword overlap with the profile, tie-broken by
    view count + recency. An empty profile ranks purely by popularity/recency."""
    kw_tokens = set()
    for kw in profile.keywords:
        kw_tokens.update(_tokenize(kw))

    scored: list[tuple[float, int, datetime, DiscoverSuggestion]] = []
    for video, discovered_at, topic in pool:
        text_tokens = set(_tokenize(f"{video.title} {video.description}"))
        matched = kw_tokens & text_tokens
        overlap = len(matched)
        if kw_tokens and overlap:
            reason = "Matches your interest in " + ", ".join(sorted(matched)[:3])
        elif topic:
            reason = f"Trending in {topic.replace('_', ' ')}"
        else:
            reason = "Trending now"
        suggestion = DiscoverSuggestion(
            video=video, reason=reason, discovered_at=discovered_at
        )
        scored.append((float(overlap), video.view_count, discovered_at, suggestion))

    # Sort by overlap, then views, then recency — all descending.
    scored.sort(key=lambda t: (t[0], t[1], t[2]), reverse=True)
    return [s for _, _, _, s in scored[:_MAX_SUGGESTIONS]]


@router.get(
    "/suggestions",
    response_model=DiscoverSuggestionsResponse,
    summary="Personalized trending suggestions based on the user's clip history",
)
def suggestions(
    user_id: str = Depends(get_current_user_id),
) -> DiscoverSuggestionsResponse:
    jobs = job_store.list_for_user(user_id, limit=40)
    profile = interpret_user_interests(jobs)
    pool = trending_store.list_pool()
    ranked = _rank_pool(pool, profile)

    last_seen = trending_store.get_last_seen(user_id)
    new_count = (
        sum(1 for s in ranked if last_seen is None or s.discovered_at > last_seen)
    )
    logger.info(
        "Suggestions — user=%s pool=%d ranked=%d new=%d",
        user_id, len(pool), len(ranked), new_count,
    )
    return DiscoverSuggestionsResponse(
        suggestions=ranked,
        new_count=new_count,
        generated_at=datetime.now(tz=timezone.utc),
        last_seen_at=last_seen,
        interest_summary=profile.summary or None,
    )


@router.post(
    "/suggestions/seen",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Mark the user's trending suggestions as seen (clears the unread badge)",
)
def mark_suggestions_seen(
    user_id: str = Depends(get_current_user_id),
) -> None:
    trending_store.set_last_seen(user_id)
