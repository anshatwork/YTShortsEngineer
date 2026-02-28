from googleapiclient.discovery import build
import os
from agents.state import ShortsState

def fetch_yt_assets_node(state: ShortsState):
    youtube = build("youtube", "v3", developerKey=os.getenv("YT_API_KEY"))
    all_results = []
    
    for query in state["search_queries"]:
        request = youtube.search().list(
            q=query,
            part="snippet",
            maxResults=3,
            type="video",
            videoDuration="short", # Focus on Short-form content
            order="viewCount"      # Simulating "trendiness"
        )
        response = request.execute()
        
        for item in response.get("items", []):
            all_results.append({
                "video_id": item["id"]["videoId"],
                "title": item["snippet"]["title"],
                "thumbnail": item["snippet"]["thumbnails"]["high"]["url"],
                "url": f"https://www.youtube.com/watch?v={item['id']['videoId']}"
            })
            
    return {"video_candidates": all_results, "current_step": "awaiting_selection"}