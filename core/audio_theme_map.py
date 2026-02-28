"""
Audio Theme Mapping
Static, deterministic mapping from visual intents to audio themes.
Ensures consistent audio selection based on script tone.
"""

from core.visual_intents import VisualIntent
from core.audio_themes import AudioTheme
from typing import Dict


# Deterministic intent → audio theme mapping
# Each visual intent maps to exactly one audio theme
INTENT_TO_AUDIO_THEME: Dict[VisualIntent, AudioTheme] = {
    VisualIntent.TENSION: AudioTheme.EERIE,
    VisualIntent.CALM: AudioTheme.PEACEFUL,
    VisualIntent.FAST: AudioTheme.ENERGETIC,
    VisualIntent.SERIOUS: AudioTheme.PROFESSIONAL,
    VisualIntent.REFLECTIVE: AudioTheme.CONTEMPLATIVE,
    VisualIntent.ASPIRATIONAL: AudioTheme.INSPIRING,
    VisualIntent.NEUTRAL: AudioTheme.NEUTRAL,
    VisualIntent.FINANCIAL: AudioTheme.PROFESSIONAL  # Financial content uses professional audio
}


def get_audio_theme_for_intent(intent: VisualIntent) -> AudioTheme:
    """
    Get audio theme for a visual intent (deterministic mapping).
    
    Args:
        intent: The visual intent enum
        
    Returns:
        Corresponding audio theme (defaults to NEUTRAL if not found)
    """
    return INTENT_TO_AUDIO_THEME.get(intent, AudioTheme.NEUTRAL)


def get_search_queries_for_theme(theme: AudioTheme) -> list[str]:
    """
    Get search queries for audio APIs based on theme.
    Used by AudioFetcher to query Pixabay/Freesound.
    
    Args:
        theme: The audio theme enum
        
    Returns:
        List of search query strings
    """
    queries = {
        AudioTheme.EERIE: [
            "dark ambient eerie",
            "suspense tension music",
            "horror atmosphere background",
            "ominous cinematic"
        ],
        AudioTheme.MYSTERIOUS: [
            "mysterious enigmatic music",
            "curious investigation background",
            "intrigue suspense light",
            "puzzle mystery theme"
        ],
        AudioTheme.PEACEFUL: [
            "calm peaceful nature",
            "relaxing ambient meditation",
            "soft gentle background",
            "tranquil serene music"
        ],
        AudioTheme.ENERGETIC: [
            "upbeat energetic music",
            "fast paced action",
            "dynamic exciting background",
            "motivational workout"
        ],
        AudioTheme.PROFESSIONAL: [
            "corporate professional background",
            "business presentation music",
            "serious authoritative",
            "news documentary theme"
        ],
        AudioTheme.CONTEMPLATIVE: [
            "thoughtful reflective music",
            "introspective ambient",
            "contemplative piano",
            "meditative peaceful"
        ],
        AudioTheme.INSPIRING: [
            "inspiring motivational music",
            "uplifting aspirational",
            "success achievement theme",
            "hopeful optimistic background"
        ],
        AudioTheme.NEUTRAL: [
            "neutral background music",
            "generic ambient loop",
            "versatile instrumental",
            "simple background track"
        ]
    }
    return queries.get(theme, ["background music"])
