"""
tools/youtube/search.py

YouTube Search Tool — updated to support:
- Long-form video filtering (videoDuration=long → >20 min via YouTube API)
- Secondary duration filter using contentDetails for precise control
- Trending signals: viewCount ordering, relevance fallback, recency window
- videoCategoryId support for topic-scoped searches
- Richer metadata: duration_seconds, view_count, like_count
"""

import logging
import random
import re
import threading
import time
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta, timezone

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from core.config import settings
from core.exceptions import QuotaExceededError
from tools.youtube.quota import (
    youtube_quota,
    classify_http_error,
    COST_SEARCH,
    COST_VIDEOS_LIST,
    COST_CHANNELS_LIST,
    COST_PLAYLIST_ITEMS,
    COST_COMMENT_THREADS,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Quota-aware execution + in-process TTL search cache
# ---------------------------------------------------------------------------

def _execute_with_backoff(request, cost: int, *, op: str = "youtube call") -> Dict[str, Any]:
    """Execute a googleapiclient request with quota enforcement + smart retries.

    - Pre-checks the shared daily budget; raises ``QuotaExceededError`` *without*
      calling the API if ``cost`` can't be afforded.
    - Charges the budget only on a successful send.
    - On ``HttpError``: daily-quota exhaustion raises ``QuotaExceededError``
      immediately (never retried — it won't clear until the Pacific-midnight
      reset); short-term rate-limits and 5xx are retried with exponential
      backoff + jitter up to ``YT_MAX_RETRIES``; anything else re-raises.
    """
    retries = max(0, int(getattr(settings, "YT_MAX_RETRIES", 3)))
    base = max(0.0, float(getattr(settings, "YT_BACKOFF_BASE_SECONDS", 1.0)))

    if not youtube_quota.can_afford(cost):
        raise QuotaExceededError(
            f"YouTube daily quota exhausted before {op}: need {cost} unit(s), "
            f"{youtube_quota.remaining()} remaining"
        )

    for attempt in range(retries + 1):
        try:
            response = request.execute()
            youtube_quota.charge(cost)
            return response
        except HttpError as exc:
            kind = classify_http_error(exc)
            if kind == "daily_quota":
                raise QuotaExceededError(
                    f"YouTube daily quota exceeded during {op}: {exc}"
                ) from exc
            if kind in ("rate_limit", "transient") and attempt < retries:
                delay = base * (2 ** attempt) + random.uniform(0.0, base)
                logger.warning(
                    "YouTube %s hit %s (attempt %d/%d); backing off %.1fs",
                    op, kind, attempt + 1, retries, delay,
                )
                time.sleep(delay)
                continue
            raise


_search_cache: Dict[str, tuple[float, Any]] = {}
_search_cache_lock = threading.Lock()


def _cache_ttl_seconds() -> float:
    return max(0.0, float(getattr(settings, "YT_SEARCH_CACHE_TTL_HOURS", 6.0))) * 3600.0


def _cache_get(key: str) -> Optional[Any]:
    ttl = _cache_ttl_seconds()
    if ttl <= 0:
        return None
    with _search_cache_lock:
        entry = _search_cache.get(key)
        if not entry:
            return None
        ts, value = entry
        if time.time() - ts > ttl:
            _search_cache.pop(key, None)
            return None
        return value


def _cache_put(key: str, value: Any) -> None:
    if _cache_ttl_seconds() <= 0:
        return
    with _search_cache_lock:
        _search_cache[key] = (time.time(), value)

# YouTube API category IDs (common ones)
CATEGORY_SCIENCE_TECH = "28"
CATEGORY_EDUCATION = "27"
CATEGORY_NEWS = "25"
CATEGORY_ENTERTAINMENT = "24"
CATEGORY_MUSIC = "10"


class YouTubeSearchTool:
    """
    YouTube Search Tool for finding trending long-form videos.
    """

    def __init__(self):
        self.api_key = settings.YT_API_KEY
        if not self.api_key:
            logger.warning("YT_API_KEY not found in settings.")
            self.youtube = None
        else:
            self.youtube = build("youtube", "v3", developerKey=self.api_key)

    def search_videos(
        self,
        queries: List[str],
        max_results: int = 5,
        days_ago: Optional[int] = None,
        long_form_only: bool = True,
        min_duration_seconds: int = 1200,   # 20 min fallback filter
        max_duration_seconds: Optional[int] = None,  # upper cap (None = no cap)
        order: str = "relevance",           # "relevance" | "viewCount" | "date"
        category_id: Optional[str] = None,
        region_code: str = "US",
        language: str = "en",
    ) -> List[Dict[str, Any]]:
        """
        Search for YouTube videos.

        Args:
            queries: List of search queries.
            max_results: Max results per query (YouTube API max: 50).
            days_ago: Only return videos published within the last X days.
            long_form_only: If True, set videoDuration=long (>20 min YouTube filter).
                            Combined with min_duration_seconds for precise filtering.
            min_duration_seconds: Secondary filter — skip videos shorter than this.
                                  Applied whenever set (independent of long_form_only).
            max_duration_seconds: Optional upper bound — skip videos longer than this.
                                  Applied whenever set, regardless of long_form_only.
            order: YouTube sort order. "viewCount" = trending; "relevance" = best match;
                   "date" = newest first.
            category_id: Optional YouTube category ID to scope search.
            region_code: Region for trending context.
            language: Relevance language hint.

        Returns:
            List of video metadata dicts, deduplicated across queries.
        """
        if not self.youtube:
            logger.error("YouTube API client not initialized.")
            return []

        try:
            published_after = None
            if days_ago:
                threshold = datetime.now(timezone.utc) - timedelta(days=days_ago)
                published_after = threshold.isoformat().replace("+00:00", "Z")

            all_results: List[Dict[str, Any]] = []
            seen_ids: set = set()

            for query in queries:
                # Per-query results are cached (TTL) so a duplicate query within
                # the window costs 0 quota units. Cross-query dedup is applied at
                # merge time (below), never cached.
                per_query = self._search_single_query(
                    query,
                    max_results=max_results,
                    order=order,
                    region_code=region_code,
                    language=language,
                    published_after=published_after,
                    long_form_only=long_form_only,
                    category_id=category_id,
                    min_duration_seconds=min_duration_seconds,
                    max_duration_seconds=max_duration_seconds,
                )
                for video in per_query:
                    video_id = video["video_id"]
                    if video_id in seen_ids:
                        continue
                    seen_ids.add(video_id)
                    all_results.append(video)

            logger.info(f"Returning {len(all_results)} videos across {len(queries)} queries")
            return all_results

        except QuotaExceededError:
            # Daily budget exhausted — surface it so callers can degrade to the
            # cached pool instead of mistaking it for "no results".
            raise
        except Exception as e:
            logger.error(f"YouTube search failed: {e}", exc_info=True)
            return []

    def _search_single_query(
        self,
        query: str,
        *,
        max_results: int,
        order: str,
        region_code: str,
        language: str,
        published_after: Optional[str],
        long_form_only: bool,
        category_id: Optional[str],
        min_duration_seconds: int,
        max_duration_seconds: Optional[int],
    ) -> List[Dict[str, Any]]:
        """Search + enrich + duration-filter one query (TTL-cached, no dedup)."""
        cache_key = "search|" + "|".join(str(x) for x in (
            query, max_results, order, region_code, language, published_after,
            long_form_only, category_id, min_duration_seconds, max_duration_seconds,
        ))
        cached = _cache_get(cache_key)
        if cached is not None:
            logger.debug("YouTube search cache hit for %r (0 quota units)", query)
            return cached

        search_args: Dict[str, Any] = {
            "q": query,
            "part": "snippet",
            "maxResults": max_results,
            "type": "video",
            "order": order,
            "regionCode": region_code,
            "relevanceLanguage": language,
            "safeSearch": "none",
        }
        if published_after:
            search_args["publishedAfter"] = published_after
        if long_form_only:
            # YouTube API built-in: "long" = videos longer than 20 minutes
            search_args["videoDuration"] = "long"
        if category_id:
            search_args["videoCategoryId"] = category_id

        logger.debug(f"Searching: {query!r} | order={order} | long_form={long_form_only}")
        response = _execute_with_backoff(
            self.youtube.search().list(**search_args), COST_SEARCH, op=f"search {query!r}",
        )

        items = response.get("items", [])
        video_ids = [item["id"]["videoId"] for item in items]
        if not video_ids:
            _cache_put(cache_key, [])
            return []

        # Fetch enriched metadata (duration, stats) in a single batch call
        enriched = self._fetch_video_details(video_ids)

        results: List[Dict[str, Any]] = []
        for item in items:
            video_id = item["id"]["videoId"]
            details = enriched.get(video_id, {})
            duration_sec = details.get("duration_seconds", 0)

            # Lower duration guard — skip videos shorter than the floor. Applied
            # whenever a min is set (not only for long_form), so an explicit
            # sub-20-min window is still honored precisely.
            if min_duration_seconds and duration_sec and duration_sec < min_duration_seconds:
                logger.debug(f"Skipping short video ({duration_sec}s): {video_id}")
                continue
            # Upper duration cap — skip videos longer than the requested window.
            if max_duration_seconds and duration_sec and duration_sec > max_duration_seconds:
                logger.debug(f"Skipping long video ({duration_sec}s): {video_id}")
                continue

            results.append({
                "video_id": video_id,
                "title": item["snippet"]["title"],
                "description": item["snippet"].get("description", "")[:300],
                "thumbnail": item["snippet"]["thumbnails"]["high"]["url"],
                "url": f"https://www.youtube.com/watch?v={video_id}",
                "channel": item["snippet"]["channelTitle"],
                "published_at": item["snippet"]["publishedAt"],
                # Enriched fields
                "duration_seconds": duration_sec,
                "duration_label": details.get("duration_label", ""),
                "view_count": details.get("view_count", 0),
                "like_count": details.get("like_count", 0),
                "comment_count": details.get("comment_count", 0),
            })

        _cache_put(cache_key, results)
        return results

    def trending_music(
        self,
        max_results: int = 25,
        region_code: str = "US",
    ) -> List[Dict[str, Any]]:
        """Return the currently most-popular music videos for a region.

        Uses ``videos.list(chart="mostPopular", videoCategoryId=10)`` — a single
        call costing **1 quota unit** (vs 100 for search.list) that returns the
        trending Music chart with snippet + contentDetails + statistics in one
        shot, so no enrichment round-trip is needed.

        Args:
            max_results: How many chart entries to return (YouTube API max: 50).
            region_code: Chart region (charts are region-scoped).

        Returns:
            List of track dicts: video_id, title, channel (artist), url,
            thumbnail, duration_seconds/label, view_count.
        """
        if not self.youtube:
            logger.error("YouTube API client not initialized.")
            return []

        try:
            response = _execute_with_backoff(
                self.youtube.videos().list(
                    part="snippet,contentDetails,statistics",
                    chart="mostPopular",
                    videoCategoryId=CATEGORY_MUSIC,
                    regionCode=region_code,
                    maxResults=max(1, min(max_results, 50)),
                ),
                COST_VIDEOS_LIST, op="trending music chart",
            )

            results: List[Dict[str, Any]] = []
            for item in response.get("items", []):
                video_id = item["id"]
                snippet = item.get("snippet", {})
                duration_sec = _parse_iso8601_duration(
                    item.get("contentDetails", {}).get("duration", "PT0S")
                )
                stats = item.get("statistics", {})
                thumbs = snippet.get("thumbnails", {})
                thumb = (thumbs.get("high") or thumbs.get("medium") or thumbs.get("default") or {})
                results.append({
                    "video_id": video_id,
                    "title": snippet.get("title", "") or "Untitled",
                    "channel": snippet.get("channelTitle", "") or "Unknown",
                    "url": f"https://www.youtube.com/watch?v={video_id}",
                    "thumbnail": thumb.get("url", ""),
                    "published_at": snippet.get("publishedAt", ""),
                    "duration_seconds": duration_sec,
                    "duration_label": _seconds_to_label(duration_sec),
                    "view_count": int(stats.get("viewCount", 0) or 0),
                })

            logger.info(
                "Returning %d trending music track(s) for region=%s (1 quota unit)",
                len(results), region_code,
            )
            return results

        except Exception as e:
            logger.error(f"YouTube trending-music fetch failed: {e}", exc_info=True)
            return []

    def search_music(
        self,
        query: str,
        max_results: int = 12,
        order: str = "relevance",
        region_code: str = "US",
    ) -> List[Dict[str, Any]]:
        """Keyword-search the Music category for songs by title/artist.

        Costs **100 quota units** (search.list) + 1 (videos.list enrichment) per
        call — far pricier than :meth:`trending_music`. Callers should cache.

        Args:
            query: Free-text song/artist phrase.
            max_results: Max results (YouTube API max: 50).
            order: "popular" → viewCount, "latest" → date, else relevance.
            region_code: Region hint.

        Returns:
            Track dicts shaped like :meth:`trending_music` (video_id, title,
            channel, url, thumbnail, duration_seconds/label, view_count).
        """
        if not self.youtube:
            logger.error("YouTube API client not initialized.")
            return []

        order_map = {"popular": "viewCount", "latest": "date"}
        yt_order = order_map.get(order, "relevance")

        try:
            response = _execute_with_backoff(
                self.youtube.search().list(
                    q=query,
                    part="snippet",
                    maxResults=max(1, min(max_results, 50)),
                    type="video",
                    videoCategoryId=CATEGORY_MUSIC,
                    order=yt_order,
                    regionCode=region_code,
                    safeSearch="none",
                ),
                COST_SEARCH, op=f"music search {query!r}",
            )

            items = response.get("items", [])
            video_ids = [it["id"]["videoId"] for it in items if it.get("id", {}).get("videoId")]
            if not video_ids:
                return []

            enriched = self._fetch_video_details(video_ids)
            results: List[Dict[str, Any]] = []
            for it in items:
                video_id = it.get("id", {}).get("videoId")
                if not video_id:
                    continue
                snippet = it.get("snippet", {})
                thumbs = snippet.get("thumbnails", {})
                thumb = (thumbs.get("high") or thumbs.get("medium") or thumbs.get("default") or {})
                details = enriched.get(video_id, {})
                results.append({
                    "video_id": video_id,
                    "title": snippet.get("title", "") or "Untitled",
                    "channel": snippet.get("channelTitle", "") or "Unknown",
                    "url": f"https://www.youtube.com/watch?v={video_id}",
                    "thumbnail": thumb.get("url", ""),
                    "published_at": snippet.get("publishedAt", ""),
                    "duration_seconds": details.get("duration_seconds", 0),
                    "duration_label": details.get("duration_label", ""),
                    "view_count": details.get("view_count", 0),
                })

            logger.info(
                "YouTube music search %r → %d track(s) (100 quota units)",
                query, len(results),
            )
            return results

        except Exception as e:
            logger.error(f"YouTube music search failed: {e}", exc_info=True)
            return []

    def _fetch_video_details(self, video_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Batch-fetch contentDetails + statistics for a list of video IDs.

        Returns:
            Dict mapping video_id → enriched metadata dict.
        """
        if not video_ids:
            return {}

        try:
            response = _execute_with_backoff(
                self.youtube.videos().list(
                    part="contentDetails,statistics", id=",".join(video_ids),
                ),
                COST_VIDEOS_LIST, op="videos.list enrichment",
            )
            result = {}
            for item in response.get("items", []):
                vid_id = item["id"]
                duration_iso = item["contentDetails"].get("duration", "PT0S")
                duration_sec = _parse_iso8601_duration(duration_iso)
                stats = item.get("statistics", {})
                result[vid_id] = {
                    "duration_seconds": duration_sec,
                    "duration_label": _seconds_to_label(duration_sec),
                    "view_count": int(stats.get("viewCount", 0)),
                    "like_count": int(stats.get("likeCount", 0)),
                    "comment_count": int(stats.get("commentCount", 0)),
                }
            return result
        except QuotaExceededError:
            raise
        except Exception as e:
            logger.warning(f"Could not fetch video details: {e}")
            return {}

    def latest_channel_videos(self, channel_query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        """Resolve a channel name and return its newest public uploads."""
        if not self.youtube:
            return []
        try:
            response = _execute_with_backoff(
                self.youtube.search().list(
                    part="snippet", q=channel_query, type="channel", order="relevance",
                    maxResults=5, safeSearch="none",
                ),
                COST_SEARCH, op=f"channel search {channel_query!r}",
            )
            items = response.get("items", [])
            if not items:
                return []
            query_tokens = {x.lower() for x in re.findall(r"[a-z0-9]+", channel_query)}
            best = max(
                items,
                key=lambda item: len(query_tokens & {
                    x.lower() for x in re.findall(r"[a-z0-9]+", item.get("snippet", {}).get("channelTitle", ""))
                }),
            )
            channel_id = best.get("snippet", {}).get("channelId") or best.get("id", {}).get("channelId")
            if not channel_id:
                return []
            channel = _execute_with_backoff(
                self.youtube.channels().list(part="contentDetails,snippet", id=channel_id),
                COST_CHANNELS_LIST, op="channels.list uploads",
            ).get("items", [])
            if not channel:
                return []
            uploads_id = channel[0].get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads")
            if not uploads_id:
                return []
            playlist = _execute_with_backoff(
                self.youtube.playlistItems().list(
                    part="snippet,contentDetails", playlistId=uploads_id,
                    maxResults=max(1, min(max_results, 50)),
                ),
                COST_PLAYLIST_ITEMS, op="playlistItems.list uploads",
            )
            ids = [x.get("contentDetails", {}).get("videoId") for x in playlist.get("items", [])]
            ids = [x for x in ids if x]
            details = self._fetch_video_details(ids)
            by_id = {x.get("videoId"): x for x in playlist.get("items", [])}
            result = []
            for video_id in ids:
                item = by_id[video_id]
                snippet = item.get("snippet", {})
                d = details.get(video_id, {})
                thumbs = snippet.get("thumbnails", {})
                thumb = (thumbs.get("high") or thumbs.get("medium") or thumbs.get("default") or {}).get("url", "")
                result.append({
                    "video_id": video_id, "title": snippet.get("title", ""),
                    "description": snippet.get("description", "")[:1000], "thumbnail": thumb,
                    "url": f"https://www.youtube.com/watch?v={video_id}",
                    "channel": snippet.get("channelTitle", ""),
                    "published_at": snippet.get("publishedAt", ""), **d,
                })
            return result
        except Exception as exc:
            logger.warning("Latest channel lookup failed for %r: %s", channel_query, exc)
            return []

    def fetch_video_context(self, url_or_id: str, related_limit: int = 6, comment_limit: int = 12) -> Dict[str, Any]:
        """Fetch best-effort metadata surrounding one YouTube video."""
        from tools.youtube.transcript import extract_video_id, fetch_transcript
        video_id = extract_video_id(url_or_id)
        out: Dict[str, Any] = {"video_id": video_id, "comments": [], "related_videos": [], "chapters": []}
        try:
            item = (_execute_with_backoff(
                self.youtube.videos().list(part="snippet,contentDetails,statistics", id=video_id),
                COST_VIDEOS_LIST, op="video context lookup",
            ).get("items", []) or [None])[0]
            if not item:
                raise ValueError("video not found")
            snippet = item.get("snippet", {})
            stats = item.get("statistics", {})
            out.update({
                "title": snippet.get("title", ""), "description": snippet.get("description", ""),
                "published_at": snippet.get("publishedAt", ""),
                "channel_id": snippet.get("channelId"), "channel_title": snippet.get("channelTitle", ""),
                "view_count": int(stats.get("viewCount", 0) or 0),
            })
            out["chapters"] = _parse_chapters(out["description"])
            try:
                out["transcript"] = fetch_transcript(video_id)
            except Exception as exc:
                logger.info("Transcript unavailable for %s: %s", video_id, exc)
            channel_id = snippet.get("channelId")
            if channel_id:
                channel = _execute_with_backoff(
                    self.youtube.channels().list(part="snippet,statistics", id=channel_id),
                    COST_CHANNELS_LIST, op="channel context lookup",
                ).get("items", [])
                if channel:
                    cs, cstats = channel[0].get("snippet", {}), channel[0].get("statistics", {})
                    out["channel_description"] = cs.get("description", "")
                    out["channel_subscriber_count"] = int(cstats.get("subscriberCount", 0) or 0)
            try:
                comments = _execute_with_backoff(
                    self.youtube.commentThreads().list(
                        part="snippet", videoId=video_id, maxResults=max(1, min(comment_limit, 100)),
                        order="relevance", textFormat="plainText",
                    ),
                    COST_COMMENT_THREADS, op="comment threads",
                ).get("items", [])
                out["comments"] = [
                    {"author": x.get("snippet", {}).get("topLevelComment", {}).get("snippet", {}).get("authorDisplayName", ""),
                     "text": x.get("snippet", {}).get("topLevelComment", {}).get("snippet", {}).get("textDisplay", ""),
                     "like_count": x.get("snippet", {}).get("topLevelComment", {}).get("snippet", {}).get("likeCount", 0)}
                    for x in comments
                ]
            except Exception as exc:
                logger.info("Comments unavailable for %s: %s", video_id, exc)
            try:
                related = _execute_with_backoff(
                    self.youtube.search().list(
                        part="snippet", relatedToVideoId=video_id, type="video", maxResults=related_limit,
                    ),
                    COST_SEARCH, op="related videos",
                ).get("items", [])
                related_ids = [x.get("id", {}).get("videoId") for x in related if x.get("id", {}).get("videoId")]
                enriched = self._fetch_video_details(related_ids)
                for x in related:
                    rid = x.get("id", {}).get("videoId")
                    if not rid:
                        continue
                    s = x.get("snippet", {})
                    out["related_videos"].append({"video_id": rid, "title": s.get("title", ""),
                        "description": s.get("description", "")[:300], "thumbnail": (s.get("thumbnails", {}).get("high") or {}).get("url", ""),
                        "url": f"https://www.youtube.com/watch?v={rid}", "channel": s.get("channelTitle", ""),
                        "published_at": s.get("publishedAt", ""), **enriched.get(rid, {})})
            except Exception as exc:
                logger.info("Related videos unavailable for %s: %s", video_id, exc)
        except Exception:
            logger.exception("Video context lookup failed for %s", video_id)
        return out

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_chapters(description: str) -> List[Dict[str, Any]]:
    chapters = []
    for line in (description or "").splitlines():
        match = re.search(r"(?:(\d{1,2}):)?(\d{1,2}):(\d{2})\s+(.+)", line.strip())
        if not match:
            continue
        hours, minutes, seconds, title = match.groups()
        start = int(hours or 0) * 3600 + int(minutes) * 60 + int(seconds)
        chapters.append({"start_seconds": start, "title": title.strip()})
    return chapters

def _parse_iso8601_duration(duration: str) -> int:
    """
    Parse ISO 8601 duration string (e.g. PT1H23M45S) to total seconds.
    """
    import re
    pattern = re.compile(
        r"PT"
        r"(?:(\d+)H)?"   # hours
        r"(?:(\d+)M)?"   # minutes
        r"(?:(\d+)S)?"   # seconds
    )
    match = pattern.match(duration)
    if not match:
        return 0
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = int(match.group(3) or 0)
    return hours * 3600 + minutes * 60 + seconds


def _seconds_to_label(seconds: int) -> str:
    """Convert seconds to human-readable label, e.g. '1h 23m'."""
    if seconds <= 0:
        return "unknown"
    h, rem = divmod(seconds, 3600)
    m, _ = divmod(rem, 60)
    if h:
        return f"{h}h {m}m"
    return f"{m}m"


# ---------------------------------------------------------------------------
# Backward-compatible function wrapper
# ---------------------------------------------------------------------------

def search_youtube_videos(
    queries: List[str],
    max_results: int = 5,
    days_ago: Optional[int] = None,
    long_form_only: bool = True,
    order: str = "relevance",
    category_id: Optional[str] = None,
    min_duration_seconds: int = 1200,
    max_duration_seconds: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    Convenience wrapper around YouTubeSearchTool.search_videos().
    Maintains backward compatibility with existing callers.
    """
    tool = YouTubeSearchTool()
    return tool.search_videos(
        queries=queries,
        max_results=max_results,
        days_ago=days_ago,
        long_form_only=long_form_only,
        min_duration_seconds=min_duration_seconds,
        max_duration_seconds=max_duration_seconds,
        order=order,
        category_id=category_id,
    )
