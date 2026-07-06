import os
import logging
from pathlib import Path
from typing import Optional
from elevenlabs.client import ElevenLabs
from elevenlabs import VoiceSettings
from tools.tts.base import BaseTTSProvider
from core.exceptions import AudioGenerationError

logger = logging.getLogger(__name__)

class ElevenLabsTTS(BaseTTSProvider):
    """
    ElevenLabs Text-to-Speech Implementation.
    """
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("ELEVENLABS_API_KEY")
        if not self.api_key:
            logger.warning("ELEVENLABS_API_KEY not set. ElevenLabs TTS will fail if used.")
            
    def generate_audio(
        self,
        text: str,
        output_path: str,
        voice_id: Optional[str] = None,
        language: str = "en",
        preset: Optional[str] = None,
    ) -> str:
        """
        Generate audio using ElevenLabs API.

        ``preset`` is accepted for interface parity with the other providers
        but is not used (ElevenLabs selects voices by ``voice_id``).
        """
        try:
            if not self.api_key:
                raise ValueError("ElevenLabs API key is missing")

            client = ElevenLabs(api_key=self.api_key)
            
            # Default to a standard voice if not provided
            # "gMRjEAcWCvjoyqIfZqlp" is likely a specific voice ID used in the original code
            voice_id = voice_id or os.getenv("ELEVENLABS_VOICE_ID", "gMRjEAcWCvjoyqIfZqlp")
            
            logger.info(f"Generating voiceover with ElevenLabs (Voice ID: {voice_id})")
            
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            
            audio_stream = client.text_to_speech.convert(
                text=text,
                voice_id=voice_id,
                voice_settings=VoiceSettings(
                    stability=0.5,
                    similarity_boost=0.75,
                    style=0.0,
                    use_speaker_boost=True,
                ),
            )
            
            audio_bytes = b"".join(audio_stream)
            
            with open(output_path, "wb") as f:
                f.write(audio_bytes)
                
            return output_path
            
        except Exception as e:
            raise AudioGenerationError(f"ElevenLabs TTS failed: {str(e)}") from e
