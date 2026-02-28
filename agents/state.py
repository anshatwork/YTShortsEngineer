from typing import TypedDict, List, Optional, Dict, Any, Tuple

class VideoAsset(TypedDict):
    video_id: str
    title: str
    thumbnail: str
    url: str

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
    
    # User selections (HITL)
    selected_video: Optional[VideoAsset]
    overlay_style: str  # "split_screen" or "voiceover_only"
    background_video_path: Optional[str]  # Path to background video (Minecraft/GTA)
    
    # Script generation
    script: Optional[str]
    script_prompt: Optional[str]
    
    # Voiceover & Audio
    voiceover_audio_path: Optional[str]
    voiceover_url: Optional[str]
    
    # Timestamps from Whisper
    word_timestamps: Optional[List[WordTimestamp]]
    
    # Downloaded assets
    downloaded_video_path: Optional[str]
    
    # Review workflow (HITL)
    review_status: str  # "pending", "approved", "rejected"
    review_notes: Optional[str]
    
    # Status tracking
    current_step: str
    final_video_path: Optional[str]
    
    # NEW: Script Parser support (Phase 2)
    source_content: Optional[str]  # Long-form input for parser (podcast transcript, article, etc.)
    
    # NEW: Audio theme selection (Phase 4)
    audio_theme: Optional[str]      # Selected audio theme (e.g., "peaceful", "energetic")
    audio_file_path: Optional[str]  # Path to cached/downloaded audio file
    
    # NEW: Batch processing (Phase 5)
    batch_index: int  # Current script index in batch (0 for single script mode)


# ---------------------------------------------------------------------------
# Long-to-Shorts Clipping Workflow — State Definitions
# ---------------------------------------------------------------------------

class ClipObject(TypedDict):
    """Represents a single extracted 9:16 short clip and its metadata."""
    clip_id: str                        # Unique identifier, e.g. "clip_001"
    source_video_path: str              # Absolute path to the original long video
    path: Optional[str]                 # Absolute path to the extracted 9:16 clip
    timestamp_range: Tuple[float, float]  # (start_seconds, end_seconds)
    hook_score: float                   # Hook quality 1–10 (from LLM analysis)
    title: Optional[str]               # Viral title, max 50 chars
    summary: Optional[str]             # 1-sentence YouTube Shorts description


class LongToShortsState(TypedDict):
    """Global state for the Long-to-Shorts conversion sub-graph."""
    # --- Inputs ---
    source_video_path: str              # Local path to the long-form video file
    transcript: str                     # Full text transcript of the video
    top_n_clips: int                    # Max clips to extract (default: 5)

    # --- Intermediate / Outputs ---
    analyzed_segments: List[ClipObject] # Hook-scored segments from AnalyzeVideoNode
    generated_clips: List[ClipObject]   # Extracted + metadata-enriched clips

    # --- Status ---
    current_step: str
    error: Optional[str]
