from typing import Dict, Any, List, Optional, Tuple
from agents.base import BaseAgent
from workflows.state import ShortsState, VideoAsset
from tools.youtube.search import search_youtube_videos
from tools.llm.huggingface import HuggingFaceLLM
from core.visual_intents import VisualIntent, validate_visual_intent
from core.intent_query_map import (
    get_queries_for_intent,
    get_local_videos_for_intent,
    get_safe_base_videos_for_intent,
    ENABLE_LLM_FALLBACK
)
import random
import os

class VideoSelectionAgent(BaseAgent):
    """
    Agent responsible for intent-first video selection using tiered fetching:
    Tier 1: Local video library (preferred)
    Tier 2: Safe base visuals (curated background videos)
    Tier 3: External search with deterministic queries
    Tier 4: LLM fallback (last resort)
    """
    
    def run(self, state: ShortsState) -> Dict[str, Any]:
        try:
            self.logger.info("Starting Intent-Based Video Selection (Tiered Fetching)...")
            
            # Get and validate visual intent
            visual_intent_str = state.get("visual_intent", "calm")
            is_valid, visual_intent_enum = validate_visual_intent(visual_intent_str)
            
            if not is_valid or not visual_intent_enum:
                self.logger.warning(f"Invalid visual intent '{visual_intent_str}', defaulting to 'calm'")
                visual_intent_enum = VisualIntent.CALM
            
            self.logger.info(f"Visual Intent: {visual_intent_enum.value}")
            
            # Attempt tiered fetching
            video, source, query, tier = self._tiered_fetch(visual_intent_enum)
            
            if not video:
                self.logger.error("All tiers failed to find a video")
                raise ValueError("No video candidates available from any tier")
            
            # Log the selection
            self.logger.info(
                f"Video selected | Intent: {visual_intent_enum.value} | "
                f"Source: {source} | Tier: {tier} | Query: {query or 'N/A'} | "
                f"Video: {video.get('title', 'Unknown')}"
            )
            
            return {
                "selected_video": video,
                "video_source": source,
                "video_query_used": query,
                "video_selection_tier": tier,
                "current_step": "video_selected"
            }
            
        except Exception as e:
            self.logger.error(f"Video selection failed: {str(e)}")
            raise Exception(f"Failed to select video: {str(e)}")
    
    def _tiered_fetch(self, intent: VisualIntent) -> Tuple[Optional[VideoAsset], str, Optional[str], int]:
        """
        Execute tiered video fetching strategy.
        Returns: (video, source, query_used, tier)
        """
        # Tier 1: Local library
        self.logger.info("Tier 1: Checking local video library...")
        video = self._fetch_from_local(intent)
        if video:
            return video, "local", None, 1
        self.logger.info("Tier 1: No local videos found")
        
        # Tier 2: Safe base videos
        self.logger.info("Tier 2: Checking safe base videos...")
        video = self._fetch_from_safe_base(intent)
        if video:
            return video, "safe_base", None, 2
        self.logger.info("Tier 2: No safe base videos found")
        
        # Tier 3: External search with deterministic queries
        self.logger.info("Tier 3: Searching external sources with deterministic queries...")
        video, query = self._fetch_from_external(intent)
        if video:
            return video, "external", query, 3
        self.logger.info("Tier 3: External search failed")
        
        # Tier 4: LLM fallback (if enabled)
        if ENABLE_LLM_FALLBACK:
            self.logger.info("Tier 4: Using LLM fallback...")
            video, query = self._llm_fallback(intent)
            if video:
                return video, "llm_fallback", query, 4
            self.logger.warning("Tier 4: LLM fallback failed")
        else:
            self.logger.info("Tier 4: LLM fallback disabled")
        
        return None, "none", None, 0
    
    def _fetch_from_local(self, intent: VisualIntent) -> Optional[VideoAsset]:
        """
        Tier 1: Fetch from local video library.
        """
        local_videos = get_local_videos_for_intent(intent)
        
        if not local_videos:
            return None
        
        # Randomly select from available local videos
        selected_path = random.choice(local_videos)
        
        # Create VideoAsset from local file
        return {
            "video_id": f"local_{os.path.basename(selected_path)}",
            "title": os.path.basename(selected_path),
            "thumbnail": "",
            "url": f"file://{selected_path}",
            "channel": "Local Library"
        }
    
    def _fetch_from_safe_base(self, intent: VisualIntent) -> Optional[VideoAsset]:
        """
        Tier 2: Fetch from safe base videos (curated backgrounds).
        """
        safe_videos = get_safe_base_videos_for_intent(intent)
        
        if not safe_videos:
            return None
        
        # Randomly select from available safe base videos
        selected_path = random.choice(safe_videos)
        
        # Create VideoAsset from safe base file
        return {
            "video_id": f"safe_base_{os.path.basename(selected_path)}",
            "title": os.path.basename(selected_path),
            "thumbnail": "",
            "url": f"file://{selected_path}",
            "channel": "Safe Base"
        }
    
    def _fetch_from_external(self, intent: VisualIntent) -> Tuple[Optional[VideoAsset], Optional[str]]:
        """
        Tier 3: Fetch from external sources using deterministic queries.
        Returns: (video, query_used)
        """
        queries = get_queries_for_intent(intent)
        
        if not queries:
            self.logger.warning(f"No queries defined for intent '{intent.value}'")
            return None, None
        
        # Randomly select one query from the deterministic list
        selected_query = random.choice(queries)
        self.logger.info(f"Using query: '{selected_query}'")
        
        # Search YouTube with the selected query
        candidates = search_youtube_videos([selected_query], max_results=5, days_ago=3650)
        
        if not candidates:
            return None, selected_query
        
        # Select best match using heuristic
        selected_video = self._select_best_match(candidates, intent)
        
        return selected_video, selected_query
    
    def _llm_fallback(self, intent: VisualIntent) -> Tuple[Optional[VideoAsset], Optional[str]]:
        """
        Tier 4: LLM-based fallback query generation.
        LLM generates broader queries based on intent only (NOT topic).
        Returns: (video, query_used)
        """
        llm = HuggingFaceLLM()
        
        template = """You are a stock footage researcher. Generate 3 specific YouTube search queries 
to find high-quality, copyright-free background videos or b-roll for the following visual intent:

Visual Intent: {intent}

Intent Description: {intent_description}

CRITICAL RULES:
- Generate queries based ONLY on the visual intent
- DO NOT mention any specific topics or subject matter
- Focus on mood, pacing, and visual style
- Use generic, reusable search terms

Return ONLY the 3 queries, one per line. Do not number them.
queries:"""
        
        response = llm.generate(
            prompt_template=template,
            input_variables={
                "intent": intent.value,
                "intent_description": VisualIntent.get_description(intent)
            }
        )
        
        queries = [q.strip() for q in response.split('\n') if q.strip()][:3]
        
        if not queries:
            return None, None
        
        # Try each generated query
        for query in queries:
            self.logger.info(f"LLM fallback query: '{query}'")
            candidates = search_youtube_videos([query], max_results=5, days_ago=3650)
            
            if candidates:
                selected_video = self._select_best_match(candidates, intent)
                return selected_video, query
        
        return None, queries[0] if queries else None
    
    def _select_best_match(self, candidates: List[VideoAsset], intent: VisualIntent) -> VideoAsset:
        """
        Select the video that best matches the visual intent.
        Uses heuristic scoring based on title/description keywords.
        """
        # Keyword maps for heuristic scoring
        avoid_map = {
            VisualIntent.CALM: ["fast", "chaos", "crazy", "loud", "explosion", "speed"],
            VisualIntent.FAST: ["slow", "calm", "relaxing", "meditation"],
            VisualIntent.SERIOUS: ["funny", "prank", "meme", "joke", "laugh"],
            VisualIntent.REFLECTIVE: ["party", "hype", "loud", "fast"],
            VisualIntent.TENSION: ["relaxing", "soothing", "happy"]
        }
        
        best_candidate = candidates[0]  # Default to first
        best_score = -1
        
        avoid_terms = avoid_map.get(intent, [])
        
        for vid in candidates:
            score = 0
            text_block = (vid.get("title", "") + " " + vid.get("description", "")).lower()
            
            # Penalize for bad matches
            for term in avoid_terms:
                if term in text_block:
                    score -= 1
            
            # Boost for explicit matches
            if intent.value in text_block:
                score += 1
            
            # Prefer shorter/cleaner titles (heuristic for b-roll vs clickbait)
            if len(vid.get("title", "")) < 60:
                score += 0.5
            
            if score > best_score:
                best_score = score
                best_candidate = vid
        
        return best_candidate

