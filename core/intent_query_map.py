"""
Intent Query Mapping
Static, deterministic mapping from visual intents to search queries.
Ensures topic text is never used in video search.
"""

import os
from pathlib import Path
from typing import Dict, List
from core.visual_intents import VisualIntent


# Deterministic query mapping for external video search
# Each intent maps to a list of safe, reusable search queries
INTENT_QUERY_MAP: Dict[VisualIntent, List[str]] = {
    VisualIntent.CALM: [
        "nature 4k relaxing",
        "slow motion water peaceful",
        "peaceful landscape timelapse",
        "meditation ambient visuals",
        "calm ocean waves",
        "forest nature sounds visual",
        "sunrise sunset timelapse calm"
    ],
    
    VisualIntent.FAST: [
        "city timelapse hyperlapse",
        "fast paced sports action",
        "racing POV footage 4k",
        "quick cuts montage",
        "energetic workout footage",
        "fast motion urban life",
        "speed ramp action shots"
    ],
    VisualIntent.ASPIRATIONAL: [
    "city skyline night luxury",
    "driving luxury car pov",
    "modern office aesthetic",
    "successful lifestyle b roll",
    "urban night drone shot",
    "high rise city cinematic",
    "focus work desk night"
    ],
    VisualIntent.NEUTRAL: [
    "abstract motion background",
    "minimal animation loop",
    "soft gradient animated background",
    "geometric motion graphics",
    "clean presentation background",
    "neutral animated backdrop",
    "simple infographic motion"
]

,
    VisualIntent.SERIOUS: [
        "cinematic dark mode 4k",
        "news studio background professional",
        "monochrome 4k cinematic",
        "corporate office professional",
        "business meeting serious",
        "documentary style footage",
        "professional presentation background"
    ],
    
    VisualIntent.REFLECTIVE: [
    "person staring out window rain",
    "walking alone night city",
    "coffee shop window reflection",
    "journal writing aesthetic close up",
    "quiet room soft lighting",
    "slow motion thinking silhouette",
    "rainy street reflection night"
    ],
    
    VisualIntent.TENSION: [
         "dark hallway cinematic",
    "dramatic shadows slow movement",
    "moody fog night scene",
    "suspense lighting silhouette",
    "thriller cinematic background",
    "low light dramatic room",
    "rainy night suspense mood"
    ],
    
    VisualIntent.FINANCIAL: [
        "stock market ticker display",
        "business charts graphs animation",
        "money counting close up 4k",
        "city financial district skyline",
        "modern office trading floor",
        "cryptocurrency bitcoin visual",
        "calculator spreadsheet business",
        "handshake business deal professional",
        "bank vault gold bars",
        "financial newspaper stock data"
    ]
}


# Local video library paths (organized by intent)
# Users should populate these directories with their own footage
def get_local_video_library_path() -> Path:
    """Get the base path for local video library."""
    base_path = os.getenv("VIDEO_LIBRARY_PATH", "./assets/video_library")
    return Path(base_path)


LOCAL_VIDEO_LIBRARY: Dict[VisualIntent, List[str]] = {
    VisualIntent.CALM: [],
    VisualIntent.FAST: [],
    VisualIntent.SERIOUS: [],
    VisualIntent.REFLECTIVE: [],
    VisualIntent.TENSION: [],
    VisualIntent.NEUTRAL: [],
    VisualIntent.ASPIRATIONAL: [],
    VisualIntent.FINANCIAL: [],
}


def populate_local_library() -> Dict[VisualIntent, List[str]]:
    """
    Scan local video library and populate LOCAL_VIDEO_LIBRARY.
    Returns updated library dictionary.
    """
    library_path = get_local_video_library_path()
    updated_library: Dict[VisualIntent, List[str]] = {
        intent: [] for intent in VisualIntent
    }
    
    if not library_path.exists():
        return updated_library
    
    # Scan each intent subdirectory
    for intent in VisualIntent:
        intent_dir = library_path / intent.value
        if intent_dir.exists() and intent_dir.is_dir():
            # Find all video files (mp4, mov, avi, etc.)
            video_extensions = {'.mp4', '.mov', '.avi', '.mkv', '.webm'}
            videos = [
                str(video_file)
                for video_file in intent_dir.iterdir()
                if video_file.suffix.lower() in video_extensions
            ]
            updated_library[intent] = videos
    
    return updated_library


# Safe base videos - reusable background footage
# These are fallback videos that work for any topic
SAFE_BASE_VIDEOS: Dict[VisualIntent, List[str]] = {
    VisualIntent.CALM: [
        os.getenv("CALM_BASE_VIDEO", "./assets/safe_base/calm_nature.mp4"),
    ],
    VisualIntent.FAST: [
        os.getenv("FAST_BASE_VIDEO", "./assets/safe_base/city_timelapse.mp4"),
    ],
    VisualIntent.SERIOUS: [
        os.getenv("SERIOUS_BASE_VIDEO", "./assets/safe_base/professional_bg.mp4"),
    ],
    VisualIntent.REFLECTIVE: [
        os.getenv("REFLECTIVE_BASE_VIDEO", "./assets/safe_base/rainy_window.mp4"),
    ],
    VisualIntent.TENSION: [
        os.getenv("TENSION_BASE_VIDEO", "./assets/safe_base/dark_atmosphere.mp4"),
    ]
}


def get_queries_for_intent(intent: VisualIntent) -> List[str]:
    """
    Get deterministic list of search queries for a visual intent.
    
    Args:
        intent: The visual intent enum
        
    Returns:
        List of search query strings
    """
    return INTENT_QUERY_MAP.get(intent, [])


def get_local_videos_for_intent(intent: VisualIntent) -> List[str]:
    """
    Get local video paths for a visual intent.
    
    Args:
        intent: The visual intent enum
        
    Returns:
        List of local video file paths
    """
    # Refresh library on each call to pick up new videos
    library = populate_local_library()
    return library.get(intent, [])


def get_safe_base_videos_for_intent(intent: VisualIntent) -> List[str]:
    """
    Get safe base video paths for a visual intent.
    
    Args:
        intent: The visual intent enum
        
    Returns:
        List of safe base video file paths
    """
    videos = SAFE_BASE_VIDEOS.get(intent, [])
    # Filter out videos that don't exist
    return [v for v in videos if os.path.exists(v)]


# Configuration flags
ENABLE_LLM_FALLBACK = os.getenv("ENABLE_LLM_FALLBACK", "true").lower() == "true"
