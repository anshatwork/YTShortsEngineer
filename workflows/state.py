from typing import TypedDict, List, Optional, Dict, Any

class VideoAsset(TypedDict):
    video_id: str
    title: str
    thumbnail: str
    url: str
    channel: Optional[str]

class WordTimestamp(TypedDict):
    word: str
    start: float
    end: float

class ShortsState(TypedDict):
    # Input data
    broad_topic: str
    
    # Processed data
    search_queries: List[str]
    video_candidates: List[VideoAsset]
    
    # User selections (HITL / Config)
    selected_video: Optional[VideoAsset]
    audio_mode: str  # "voiceover", "fetched_video", "bg_video"
    video_mode: str  # "split_screen", "fetched_video", "bg_video"
    overlay_style: Optional[str]  # "background_only", "split_screen", etc.
    background_video_path: Optional[str]  # Path to background video (Minecraft/GTA)
    
    # Script generation
    script: Optional[str]
    script_prompt: Optional[str]
    hook_style: Optional[str]   # "curiosity", "fear", "identity", "contradiction"
    visual_intent: Optional[str] # "calm", "fast", "serious", "reflective", "tension"
    
    # Validation metadata
    hook_style_validated: Optional[bool]  # True if hook_style matches enum
    visual_intent_validated: Optional[bool]  # True if visual_intent matches enum
    
    # Voiceover & Audio
    voiceover_audio_path: Optional[str]
    voiceover_url: Optional[str]
    
    # Timestamps from Whisper
    word_timestamps: Optional[List[WordTimestamp]]
    
    # Downloaded assets
    downloaded_video_path: Optional[str]
    
    # Video selection metadata
    video_source: Optional[str]  # "local", "safe_base", "external", "llm_fallback"
    video_query_used: Optional[str]  # The actual query used for search
    video_selection_tier: Optional[int]  # 1-4, which tier was used
    
    # Review workflow (HITL)
    review_status: str  # "pending", "approved", "rejected"
    review_notes: Optional[str]
    
    # Status tracking
    current_step: str
    final_video_path: Optional[str]
