"""tools.tts — text-to-speech providers and shared provider selection."""

import logging
import os
from typing import Optional

from tools.tts.base import BaseTTSProvider

logger = logging.getLogger(__name__)

# Values that mean "no key was actually configured". `.env` ships placeholder
# strings (e.g. ELEVENLABS_API_KEY=your_elevenlabs_api_key) that are truthy, so a
# bare os.getenv() presence check would pick a premium provider and then 401.
_PLACEHOLDERS = {
    "",
    "your_elevenlabs_api_key",
    "your_chatterbox_api_key",
    "your_api_key",
    "changeme",
    "none",
    "null",
}


def _real_key(name: str) -> Optional[str]:
    """Return the env value for *name*, or None if unset/blank/placeholder."""
    value = (os.getenv(name) or "").strip()
    return value if value.lower() not in _PLACEHOLDERS else None


def select_tts_provider() -> BaseTTSProvider:
    """Select a TTS provider using a cascading fallback.

    Priority:
      1. ElevenLabs        — premium, if a real ELEVENLABS_API_KEY is set
      2. Chatterbox        — premium alternative, if a real CHATTERBOX_API_KEY is set
      3. edge-tts          — free default (Microsoft neural voices; no key/GPU,
                             falls back to pyttsx3 internally if offline)
      4. Streamlabs Polly  — legacy free path, opt-in via TTS_FREE_PROVIDER=streamlabs

    Returns a ready-to-use provider instance. Callers pass text/preset to
    ``generate_audio``.
    """
    if _real_key("ELEVENLABS_API_KEY"):
        from tools.tts.elevenlabs import ElevenLabsTTS

        logger.info("Selected TTS provider: ElevenLabs (premium)")
        return ElevenLabsTTS()

    if _real_key("CHATTERBOX_API_KEY"):
        from tools.tts.chatterbox import ChatterboxTTS

        logger.info("Selected TTS provider: Chatterbox (premium)")
        return ChatterboxTTS()

    if (os.getenv("TTS_FREE_PROVIDER") or "edge").strip().lower() == "streamlabs":
        from tools.tts.streamlabs_polly import StreamlabsPollyTTS

        logger.info("Selected TTS provider: Streamlabs Polly (free)")
        return StreamlabsPollyTTS()

    from tools.tts.edge_tts import EdgeTTS

    logger.info("Selected TTS provider: edge-tts (free neural)")
    return EdgeTTS()


__all__ = ["select_tts_provider", "BaseTTSProvider"]
