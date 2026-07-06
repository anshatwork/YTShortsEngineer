import os
import logging
import time
from pathlib import Path
from typing import Optional
import requests
from tools.tts.base import BaseTTSProvider, _pyttsx3_to_file
from core.exceptions import AudioGenerationError

logger = logging.getLogger(__name__)

class StreamlabsPollyTTS(BaseTTSProvider):
    """
    Streamlabs Polly Text-to-Speech Implementation.
    Uses Streamlabs' undocumented Amazon Polly proxy endpoint.
    
    WARNING: This is an unofficial, undocumented API that may:
    - Be rate limited without notice
    - Break or be discontinued at any time
    - Have no official support
    
    Best used as a free fallback when premium TTS services are unavailable.
    """
    
    # Streamlabs Polly endpoint (undocumented, community-discovered)
    API_URL = "https://streamlabs.com/polly/speak"
    
    # Voice presets for different content types
    VOICE_PRESETS = {
        "finance": {
            "voice": "Matthew",  # US English, Male, Neural - Professional, authoritative
            "engine": "neural",
            "rate": "95%",  # Slightly slower for complex info
            "pitch": "medium"
        },
        "finance_energetic": {
            "voice": "Joanna",  # US English, Female, Neural - Clear, engaging
            "engine": "neural",
            "rate": "100%",
            "pitch": "medium"
        },
        "default": {
            "voice": "Matthew",
            "engine": "neural",
            "rate": "100%",
            "pitch": "medium"
        }
    }
    
    def generate_audio(
        self,
        text: str,
        output_path: str,
        voice_id: Optional[str] = None,
        language: str = "en",
        preset: Optional[str] = None
    ) -> str:
        """
        Generate audio using Streamlabs Polly API with optional presets.
        
        Args:
            text: Text to convert to speech
            output_path: Path to save the audio file
            voice_id: Optional voice ID (overrides preset)
            language: Language code (default: "en")
            preset: Optional preset name ("finance", "finance_energetic", etc.)
        
        Returns:
            Path to generated audio file
        """
        try:
            logger.info(f"Generating voiceover with Streamlabs Polly (preset: {preset or 'default'})")
            
            # Apply preset if specified
            config = self.VOICE_PRESETS.get(preset or "default", self.VOICE_PRESETS["default"])
            voice = voice_id or config.get("voice")
            
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            
            # Try Streamlabs Polly API first
            try:
                # Prepare request payload
                payload = {
                    "voice": voice,
                    "text": text
                }
                
                logger.info(f"Calling Streamlabs Polly API with voice: {voice}")
                logger.debug(f"Text length: {len(text)} characters")
                
                # Make API request with timeout
                response = requests.post(
                    self.API_URL,
                    json=payload,
                    timeout=30,
                    headers={
                        "Content-Type": "application/json",
                        "User-Agent": "Mozilla/5.0"  # Some APIs require user agent
                    }
                )
                
                # Check response status
                if response.status_code == 200:
                    # Check if response is audio
                    content_type = response.headers.get('Content-Type', '')
                    
                    if 'audio' in content_type or len(response.content) > 1000:
                        # Save audio file
                        with open(output_path, "wb") as f:
                            f.write(response.content)
                        
                        logger.info(f"Generated audio via Streamlabs Polly at {output_path}")
                        logger.debug(f"Audio size: {len(response.content)} bytes")
                        return output_path
                    else:
                        # Response might be JSON error
                        logger.warning(f"Streamlabs Polly returned non-audio response: {response.text[:200]}")
                        raise Exception("Invalid audio response from Streamlabs Polly")
                
                elif response.status_code == 403:
                    logger.warning("Streamlabs Polly API returned 403 (Forbidden)")
                    logger.warning("The API endpoint may be restricted, changed, or require authentication")
                    logger.info("This is expected for the undocumented Streamlabs API")
                    raise Exception("API access forbidden (403)")
                
                elif response.status_code == 429:
                    logger.warning("Streamlabs Polly rate limit exceeded")
                    raise Exception("Rate limit exceeded")
                
                else:
                    logger.warning(f"Streamlabs Polly API returned status {response.status_code}")
                    if response.text:
                        logger.debug(f"Response: {response.text[:200]}")
                    raise Exception(f"API returned status {response.status_code}")
                    
            except requests.exceptions.Timeout:
                logger.warning("Streamlabs Polly API request timed out (30s)")
                raise Exception("API timeout")
                
            except requests.exceptions.RequestException as e:
                logger.warning(f"Streamlabs Polly API request failed: {e}")
                raise Exception(f"API request failed: {e}")
            
        except Exception as api_error:
            # Fallback to pyttsx3 — renders a real audio file at the requested
            # extension (WAV transcoded to MP3 etc.) or raises a clean error.
            logger.warning(f"Streamlabs Polly failed: {api_error}")
            logger.info("Falling back to pyttsx3 for local TTS")

            # Convert the preset's "NN%" rate string to a pyttsx3 rate.
            rate_str = config.get("rate", "100%").rstrip('%')
            rate = int(float(rate_str) * 1.8)
            return _pyttsx3_to_file(text, output_path, preset=preset, rate=rate)
