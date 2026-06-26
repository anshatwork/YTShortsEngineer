"""
FetchTrendingVideos - Standalone function (also usable as a LangGraph node)

Design decisions:
- LLM for query generation is OPTIONAL (off by default).
  For trending video discovery, a curated query bank + random sampling
  is faster, cheaper, and more consistent than LLM-generated queries.
  Enable `use_llm_queries=True` only if you need highly dynamic/contextual queries.

- Searches for long-form videos (>20 min) via YouTube's `videoDuration=long` filter.
- Deduplicates across queries.
- Can be called standalone OR dropped into a LangGraph workflow.
"""

import logging
import math
import random
import re
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional

# ------------------------------------------------------------------
# Ensure the project root is on sys.path when run directly
# ------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Now we can use absolute imports
from tools.youtube.search import search_youtube_videos

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Curated trending query bank — grouped by topic
# Extend this instead of hitting an LLM for every run.
# ---------------------------------------------------------------------------
TRENDING_QUERY_BANK: Dict[str, List[str]] = {
    "ai": [
        "openai latest model explained",
        "claude anthropic deep dive",
        "ai agents tutorial 2025",
        "llm fine tuning walkthrough",
        "google gemini vs gpt comparison",
    ],
    "tech": [
        "apple silicon benchmark 2025",
        "meta quest review",
        "best programming language 2025",
        "software architecture explained",
        "system design interview",
    ],
    "productivity": [
        "second brain notion setup",
        "deep work strategy",
        "obsidian full workflow",
        "time blocking productivity system",
        "pkm knowledge management",
    ],
    "news_analysis": [
        "tech industry layoffs explained",
        "startup funding landscape 2025",
        "silicon valley documentary",
        "big tech antitrust breakdown",
    ],
    "internet_culture": [
        "youtube algorithm explained 2025",
        "creator economy deep dive",
        "viral content strategy breakdown",
    ],
}


def get_topic_keys() -> List[str]:
    """Return the available curated topic keys (for UI chips / API discovery)."""
    return list(TRENDING_QUERY_BANK.keys())


def _get_static_queries(
    topics: Optional[List[str]] = None,
    queries_per_topic: int = 2,
) -> List[str]:
    """
    Sample queries from the curated bank.

    Args:
        topics: Subset of topic keys to sample from. None = all topics.
        queries_per_topic: How many queries to randomly pick per topic.

    Returns:
        Flat list of query strings.
    """
    bank = TRENDING_QUERY_BANK
    if topics:
        bank = {k: v for k, v in bank.items() if k in topics}

    selected = []
    for topic_queries in bank.values():
        selected.extend(random.sample(topic_queries, min(queries_per_topic, len(topic_queries))))

    return selected


def _get_llm_queries(topics: Optional[List[str]] = None) -> List[str]:
    """
    Use an LLM to generate trending queries dynamically.
    Slower + costs tokens — use only when you need highly contextual queries.
    """
    from core.llm import llm  # lazy import — only loaded when needed

    topic_str = ", ".join(topics) if topics else "AI, Tech, Productivity, News, Internet trends"

    prompt = f"""
    Generate 5 trending YouTube search queries for long-form videos (20+ minutes) on these topics: {topic_str}.
    Focus on topics that are currently viral or gaining traction.
    Return ONLY a valid Python list of strings. No explanation.
    Example: ["openai new model deep dive", "ai startup funding explained", "elon musk full interview"]
    """

    result = llm.invoke(prompt)
    queries = result if isinstance(result, list) else eval(result)  # noqa: S307
    logger.info(f"LLM-generated queries: {queries}")
    return queries


# ---------------------------------------------------------------------------
# Result ranking
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(r"[a-z0-9]+")
# Common words that carry no search intent — ignored when matching keywords
# against titles/descriptions so they don't inflate the relevance score.
_STOP_WORDS = frozenset(
    {
        "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with",
        "is", "are", "how", "what", "why", "vs", "explained", "tutorial",
        "guide", "video", "full", "best", "2024", "2025", "2026",
    }
)


def _tokenize(text: str) -> List[str]:
    return _TOKEN_RE.findall((text or "").lower())


def _keyword_tokens(keywords: Optional[List[str]]) -> set:
    """Flatten user keywords into a set of meaningful lowercase tokens."""
    tokens: set = set()
    for kw in keywords or []:
        for tok in _tokenize(kw):
            if tok not in _STOP_WORDS:
                tokens.add(tok)
    return tokens


def _rank_videos(
    videos: List[Dict[str, Any]],
    keywords: Optional[List[str]] = None,
    order: str = "relevance",
    max_total: int = 24,
) -> List[Dict[str, Any]]:
    """
    Globally re-rank candidate videos and cap the total.

    Sort key (descending) is a tuple of:
        1. keyword_score   — token overlap of user keywords against the title
                             (weighted 2x) and description. 0 when no keywords,
                             so topic-only searches fall through to the chosen
                             sort order.
        2. secondary       — derived from `order`: log(views) for viewCount,
                             recency for date, original position for relevance.
        3. engagement      — (likes + comments) / views, a light tiebreak.

    Args:
        videos: Flat list of enriched video dicts from search_youtube_videos().
        keywords: User-typed free-text keywords to prioritize.
        order: YouTube sort order originally requested.
        max_total: Hard cap on returned videos.
    """
    kw_tokens = _keyword_tokens(keywords)
    n = len(videos)

    def secondary(idx: int, v: Dict[str, Any]) -> float:
        if order == "viewCount":
            return math.log1p(max(v.get("view_count", 0), 0))
        if order == "date":
            # Lexicographic ISO-8601 timestamps sort chronologically; map to a
            # descending rank so newer videos score higher.
            return float(n - idx)
        # "relevance" — preserve YouTube's per-query ordering (earliest first).
        return float(n - idx)

    def keyword_score(v: Dict[str, Any]) -> float:
        if not kw_tokens:
            return 0.0
        title_tokens = set(_tokenize(v.get("title", "")))
        desc_tokens = set(_tokenize(v.get("description", "")))
        return 2.0 * len(kw_tokens & title_tokens) + len(kw_tokens & desc_tokens)

    def engagement(v: Dict[str, Any]) -> float:
        views = max(v.get("view_count", 0), 1)
        return (v.get("like_count", 0) + v.get("comment_count", 0)) / views

    scored = sorted(
        enumerate(videos),
        key=lambda pair: (
            keyword_score(pair[1]),
            secondary(pair[0], pair[1]),
            engagement(pair[1]),
        ),
        reverse=True,
    )
    return [v for _, v in scored[:max_total]]


# ---------------------------------------------------------------------------
# Core standalone function
# ---------------------------------------------------------------------------

def fetch_trending_videos(
    topics: Optional[List[str]] = None,
    topic_overrides: Optional[List[str]] = None,
    extra_queries: Optional[List[str]] = None,
    max_results_per_query: int = 3,
    days_ago: Optional[int] = 7,
    use_llm_queries: bool = False,
    queries_per_topic: int = 2,
    order: str = "relevance",
    keywords: Optional[List[str]] = None,
    max_total: int = 24,
    long_form_only: bool = True,
    min_duration_seconds: int = 1200,
    max_duration_seconds: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Fetch trending long-form YouTube videos.

    Can be called standalone OR used as a LangGraph node.

    Args:
        topics: Topic keys to filter from query bank (e.g. ["ai", "tech"]).
                None = use all topics.
        topic_overrides: Provide your own raw query strings — skips the query bank entirely.
        extra_queries: Free-text queries appended to the bank/LLM query set
                       (deduped). Use this to combine curated topics with
                       user-typed keywords. Ignored when topic_overrides is set.
        max_results_per_query: Max videos returned per search query.
        days_ago: Only include videos published within this many days.
        use_llm_queries: If True, use LLM to generate queries instead of static bank.
                         Ignored if topic_overrides is provided.
        queries_per_topic: How many queries to sample per topic (static bank only).
        order: YouTube sort order — "relevance" | "viewCount" | "date".
        keywords: User-typed free-text keywords used to prioritize results in the
                  final re-ranking (videos matching these surface first).
        max_total: Hard cap on the number of videos returned after re-ranking.
        long_form_only: If True, set YouTube's videoDuration=long (>20 min) filter.
                        Set False to allow shorter videos (the min/max guards still
                        apply client-side).
        min_duration_seconds: Skip videos shorter than this. Defaults to 1200s.
        max_duration_seconds: Optional upper bound — skip videos longer than this.

    Returns:
        Dict with keys:
            - video_urls: List[str]
            - youtube_results: List[Dict]  (full metadata)
            - queries_used: List[str]
    """
    try:
        # ------------------------------------------------------------------
        # Step 1: Build queries
        # ------------------------------------------------------------------
        if topic_overrides:
            queries = list(topic_overrides)
            logger.info(f"Using override queries: {queries}")
        elif use_llm_queries:
            queries = _get_llm_queries(topics)
        else:
            queries = _get_static_queries(topics, queries_per_topic)
            logger.info(f"Using static queries ({len(queries)}): {queries}")

        # Append free-text queries (curated bank + free-text), preserving order
        # and dropping duplicates.
        if extra_queries:
            queries = queries + [q for q in extra_queries if q]
        seen: set = set()
        queries = [q for q in queries if not (q in seen or seen.add(q))]

        # ------------------------------------------------------------------
        # Step 2: Search YouTube for long-form videos
        # ------------------------------------------------------------------
        videos = search_youtube_videos(
            queries=queries,
            max_results=max_results_per_query,
            days_ago=days_ago,
            long_form_only=long_form_only,
            min_duration_seconds=min_duration_seconds,
            max_duration_seconds=max_duration_seconds,
            order=order,               # "viewCount" | "relevance" | "date"
        )

        # ------------------------------------------------------------------
        # Step 3: Globally re-rank (keyword relevance first) and cap the total
        # ------------------------------------------------------------------
        videos = _rank_videos(videos, keywords=keywords, order=order, max_total=max_total)

        urls = [v["url"] for v in videos]
        logger.info(f"Found {len(urls)} long-form videos across {len(queries)} queries")

        return {
            "video_urls": urls,
            "youtube_results": videos,
            "queries_used": queries,
        }

    except Exception as e:
        logger.error(f"Trending video fetch failed: {e}", exc_info=True)
        return {
            "video_urls": [],
            "youtube_results": [],
            "queries_used": [],
        }


# ---------------------------------------------------------------------------
# LangGraph node adapter (thin wrapper — keeps graph state handling separate)
# ---------------------------------------------------------------------------

def fetch_trending_videos_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    LangGraph node wrapper around fetch_trending_videos().

    Reads optional config from state:
        - state.get("topics"): topic filter list
        - state.get("use_llm_queries"): bool
        - state.get("days_ago"): int
    """
    result = fetch_trending_videos(
        topics=state.get("topics"),
        days_ago=state.get("days_ago", 7),
        use_llm_queries=state.get("use_llm_queries", False),
    )
    return result  # LangGraph merges this into state automatically


# ---------------------------------------------------------------------------
# CLI / direct invocation
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Example: standalone call
    result = fetch_trending_videos(
        topics=["ai", "tech"],
        days_ago=7,
        max_results_per_query=5,
        use_llm_queries=False,  # flip to True to test LLM path
    )

    print(f"\nQueries used: {result['queries_used']}")
    print(f"Videos found: {len(result['video_urls'])}")
    for v in result["youtube_results"]:
        print(f"  [{v['duration_seconds']//60}min] {v['title']} — {v['url']}")