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
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta, timezone

from googleapiclient.discovery import build
from core.config import settings

logger = logging.getLogger(__name__)

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
                response = self.youtube.search().list(**search_args).execute()

                video_ids = [
                    item["id"]["videoId"]
                    for item in response.get("items", [])
                    if item["id"]["videoId"] not in seen_ids
                ]

                if not video_ids:
                    continue

                # Fetch enriched metadata (duration, stats) in a single batch call
                enriched = self._fetch_video_details(video_ids)

                for item in response.get("items", []):
                    video_id = item["id"]["videoId"]
                    if video_id in seen_ids:
                        continue

                    details = enriched.get(video_id, {})
                    duration_sec = details.get("duration_seconds", 0)

                    # Lower duration guard — skip videos shorter than the floor.
                    # Applied whenever a min is set (not only for long_form), so an
                    # explicit sub-20-min window is still honored precisely.
                    if min_duration_seconds and duration_sec and duration_sec < min_duration_seconds:
                        logger.debug(f"Skipping short video ({duration_sec}s): {video_id}")
                        continue

                    # Upper duration cap — skip videos longer than the requested window.
                    if max_duration_seconds and duration_sec and duration_sec > max_duration_seconds:
                        logger.debug(f"Skipping long video ({duration_sec}s): {video_id}")
                        continue

                    seen_ids.add(video_id)
                    all_results.append({
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

            logger.info(f"Returning {len(all_results)} videos across {len(queries)} queries")
            return all_results

        except Exception as e:
            logger.error(f"YouTube search failed: {e}", exc_info=True)
            return []

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
            response = self.youtube.videos().list(
                part="snippet,contentDetails,statistics",
                chart="mostPopular",
                videoCategoryId=CATEGORY_MUSIC,
                regionCode=region_code,
                maxResults=max(1, min(max_results, 50)),
            ).execute()

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
            response = self.youtube.search().list(
                q=query,
                part="snippet",
                maxResults=max(1, min(max_results, 50)),
                type="video",
                videoCategoryId=CATEGORY_MUSIC,
                order=yt_order,
                regionCode=region_code,
                safeSearch="none",
            ).execute()

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
            response = self.youtube.videos().list(
                part="contentDetails,statistics",
                id=",".join(video_ids),
            ).execute()

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

        except Exception as e:
            logger.warning(f"Could not fetch video details: {e}")
            return {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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