"""
Audio Theme Enums
Provides static audio theme enums for background music selection.
Maps to visual intents for deterministic audio selection.
"""

from enum import Enum
from typing import Optional


class AudioTheme(str, Enum):
    """
    Background audio themes mapped to visual intents.
    Each theme represents a distinct mood/atmosphere for background music.
    """
    EERIE = "eerie"                      # Dark, suspenseful (TENSION)
    MYSTERIOUS = "mysterious"             # Intriguing, curious
    PEACEFUL = "peaceful"                 # Calm, relaxing (CALM)
    ENERGETIC = "energetic"               # Upbeat, fast-paced (FAST)
    PROFESSIONAL = "professional"         # Corporate, serious (SERIOUS)
    CONTEMPLATIVE = "contemplative"       # Thoughtful, reflective (REFLECTIVE)
    INSPIRING = "inspiring"               # Motivational, uplifting (ASPIRATIONAL)
    NEUTRAL = "neutral"                   # Generic background (NEUTRAL_EXPLAINER)
    
    @classmethod
    def validate(cls, value: str) -> Optional['AudioTheme']:
        """
        Validate and return AudioTheme enum from string.
        Returns None if invalid.
        
        Args:
            value: String value to validate
            
        Returns:
            AudioTheme enum or None if invalid
        """
        try:
            return cls(value.lower().strip())
        except (ValueError, AttributeError):
            return None
    
    @classmethod
    def get_description(cls, theme: 'AudioTheme') -> str:
        """Get description for an audio theme."""
        descriptions = {
            cls.EERIE: "Dark, suspenseful, tension-building atmosphere,eerie",
            cls.MYSTERIOUS: "Intriguing, curious, enigmatic mood,mysterious",
            cls.PEACEFUL: "Calm, relaxing, soothing background,peaceful",
            cls.ENERGETIC: "Upbeat, fast-paced, exciting energy,energetic",
            cls.PROFESSIONAL: "Corporate, serious, authoritative tone,professional",
            cls.CONTEMPLATIVE: "Thoughtful, reflective, introspective mood,contemplative",
            cls.INSPIRING: "Motivational, uplifting, aspirational feel,inspiring",
            cls.NEUTRAL: "Generic, versatile background music,neutral"
        }
        return descriptions.get(theme, "")
    
    @classmethod
    def list_values(cls) -> list[str]:
        """Return list of valid string values."""
        return [theme.value for theme in cls]


def validate_audio_theme(value: str) -> tuple[bool, Optional[AudioTheme]]:
    """
    Validate audio theme string.
    Returns (is_valid, enum_value or None)
    
    Args:
        value: String to validate
        
    Returns:
        Tuple of (is_valid, AudioTheme or None)
    """
    validated = AudioTheme.validate(value)
    return (validated is not None, validated)
