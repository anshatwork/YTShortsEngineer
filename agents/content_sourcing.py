from typing import Dict, Any
from agents.base import BaseAgent
from workflows.state import ShortsState
from tools.youtube.search import search_youtube_videos

class ContentSourcingAgent(BaseAgent):
    """
    Agent responsible for finding video candidates on YouTube.
    """
    
    def run(self, state: ShortsState) -> Dict[str, Any]:
        try:
            self.logger.info("Searching for video candidates...")
            
            queries = state.get("search_queries", [])
            if not queries:
                raise ValueError("No search queries found in state")
                
            video_candidates = search_youtube_videos(queries, max_results=3,days_ago=365)
            
            self.logger.info(f"Found {len(video_candidates)} video candidates")
            
            return {
                "video_candidates": video_candidates,
                "current_step": "awaiting_selection"
            }
            
        except Exception as e:
            self.logger.error(f"Content sourcing failed: {str(e)}")
            raise Exception(f"Failed to source content: {str(e)}")
