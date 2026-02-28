"""
Visual Intent and Hook Style Enums
Provides static, deterministic enums for script generation and video selection.
"""

from enum import Enum
from typing import Optional


class HookStyle(str, Enum):
    """
    Fixed hook styles for script generation.
    LLM must select from these options only.
    """
    CURIOSITY = "curiosity"
    FEAR = "fear"
    IDENTITY = "identity"
    CONTRADICTION = "contradiction"
    
    @classmethod
    def validate(cls, value: str) -> Optional['HookStyle']:
        """
        Validate and return HookStyle enum from string.
        Returns None if invalid.
        """
        try:
            return cls(value.lower().strip())
        except (ValueError, AttributeError):
            return None
    
    @classmethod
    def get_description(cls, style: 'HookStyle') -> str:
        """Get description for a hook style."""
        descriptions = {
            cls.CURIOSITY: "Start with a weird fact or questions",
            cls.FEAR: '"Stop doing this..." or "This is why you\'re failing..."',
            cls.IDENTITY: '"If you are X, you need to hear this..."',
            cls.CONTRADICTION: '"Everything you know about X is wrong."'
        }
        return descriptions.get(style, "")
    
    @classmethod
    def list_values(cls) -> list[str]:
        """Return list of valid string values."""
        return [style.value for style in cls]


class VisualIntent(str, Enum):
    """
    Fixed visual intents for video selection.
    LLM must select based on script TONE, not topic keywords.
    """
    CALM = "calm"
    FAST = "fast"
    SERIOUS = "serious"
    REFLECTIVE = "reflective"
    TENSION = "tension"
    NEUTRAL = "neutral_explainer"
    ASPIRATIONAL = "aspirational"
    FINANCIAL = "financial"  # NEW: Financial/business content

    @classmethod
    def validate(cls, value: str) -> Optional['VisualIntent']:
        """
        Validate and return VisualIntent enum from string.
        Returns None if invalid.
        """
        try:
            return cls(value.lower().strip())
        except (ValueError, AttributeError):
            return None
    
    @classmethod
    def get_description(cls, intent: 'VisualIntent') -> str:
        """Get description for a visual intent."""
        descriptions = {
            cls.CALM: "Slow, reflective, peaceful delivery",
            cls.FAST: "Energetic, rapid-fire, exciting delivery",
            cls.SERIOUS: "Professional, authoritative, educational tone",
            cls.REFLECTIVE: "Thoughtful, introspective, contemplative",
            cls.TENSION: "Suspenseful, dramatic, urgent",
            cls.NEUTRAL: "Calm, neutral, informative delivery",
            cls.ASPIRATIONAL: "Uplifting, motivational, inspiring delivery",
            cls.FINANCIAL: "Professional, data-driven, business-focused delivery"
        }
        return descriptions.get(intent, "")
    
    @classmethod
    def list_values(cls) -> list[str]:
        """Return list of valid string values."""
        return [intent.value for intent in cls]


def validate_hook_style(value: str) -> tuple[bool, Optional[HookStyle]]:
    """
    Validate hook style string.
    Returns (is_valid, enum_value or None)
    """
    validated = HookStyle.validate(value)
    return (validated is not None, validated)


def validate_visual_intent(value: str) -> tuple[bool, Optional[VisualIntent]]:
    """
    Validate visual intent string.
    Returns (is_valid, enum_value or None)
    """
    validated = VisualIntent.validate(value)
    return (validated is not None, validated)
