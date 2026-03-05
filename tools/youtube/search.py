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
                                  Only applied when long_form_only=True.
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

                    # Secondary duration guard (in case API filter isn't tight enough)
                    if long_form_only and duration_sec and duration_sec < min_duration_seconds:
                        logger.debug(f"Skipping short video ({duration_sec}s): {video_id}")
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
        order=order,
        category_id=category_id,
    )