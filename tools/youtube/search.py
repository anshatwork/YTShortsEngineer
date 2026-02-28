from googleapiclient.discovery import build
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta, timezone
from core.config import settings

logger = logging.getLogger(__name__)


class YouTubeSearchTool:
    """
    YouTube Search Tool for finding trending videos.
    """
    
    def __init__(self):
        """Initialize YouTube API client with API key from settings."""
        self.api_key = settings.YT_API_KEY
        if not self.api_key:
            logger.warning("YT_API_KEY not found in settings.")
            self.youtube = None
        else:
            self.youtube = build("youtube", "v3", developerKey=self.api_key)
    
    def search_videos(
        self, 
        queries: List[str], 
        max_results: int = 3,
        days_ago: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for YouTube videos based on queries.
        
        Args:
            queries: List of search queries.
            max_results: Max results per query.
            days_ago: Optional filter to find videos posted within the last X days.
            
        Returns:
            List of video metadata dictionaries.
        """
        if not self.youtube:
            logger.error("YouTube API client not initialized. Check YT_API_KEY.")
            return []
            
        try:
            # Calculate RFC 3339 timestamp if days_ago is provided
            published_after = None
            if days_ago:
                time_threshold = datetime.now(timezone.utc) - timedelta(days=days_ago)
                published_after = time_threshold.isoformat().replace("+00:00", "Z")

            all_results = []
            seen_ids = set()
            
            for query in queries:
                # Prepare request arguments
                search_args = {
                    "q": query,
                    "part": "snippet",
                    "maxResults": max_results,
                    "type": "video",
                    "videoDuration": "short",
                    "order": "viewCount",
                }
                
                # Only add publishedAfter if it's set
                if published_after:
                    search_args["publishedAfter"] = published_after
                
                request = self.youtube.search().list(**search_args)
                response = request.execute()
                
                for item in response.get("items", []):
                    video_id = item["id"]["videoId"]
                    if video_id not in seen_ids:
                        seen_ids.add(video_id)
                        all_results.append({
                            "video_id": video_id,
                            "title": item["snippet"]["title"],
                            "thumbnail": item["snippet"]["thumbnails"]["high"]["url"],
                            "url": f"https://www.youtube.com/watch?v={video_id}",
                            "channel": item["snippet"]["channelTitle"],
                            "published_at": item["snippet"]["publishedAt"]
                        })
            
            logger.info(f"Found {len(all_results)} unique videos across {len(queries)} queries")
            return all_results
            
        except Exception as e:
            logger.error(f"YouTube search failed: {e}")
            return []


# Backward compatibility: Keep the original function signature
def search_youtube_videos(
    queries: List[str], 
    max_results: int = 3,
    days_ago: Optional[int] = None
) -> List[Dict[str, Any]]:
    """
    Legacy function wrapper for backward compatibility.
    
    Args:
        queries: List of search queries.
        max_results: Max results per query.
        days_ago: Optional filter to find videos posted within the last X days.
    """
    tool = YouTubeSearchTool()
    return tool.search_videos(queries, max_results, days_ago)
