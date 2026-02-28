import os
import logging
import time
from pathlib import Path
from typing import Optional
from tools.tts.base import BaseTTSProvider
from core.exceptions import AudioGenerationError

logger = logging.getLogger(__name__)

class ChatterboxTTS(BaseTTSProvider):
    """
    Chatterbox Text-to-Speech Implementation with voice presets.
    This is a placeholder for the actual Chatterbox API integration.
    """
    
    # Add voice presets for different content types
    VOICE_PRESETS = {
        "finance": {
            "voice_id": "professional_male_deep",  # Adjust based on Chatterbox's voice catalog
            "stability": 0.7,  # More stable = more authoritative
            "clarity": 0.8,    # High clarity for numbers/data
            "pace": "moderate",  # Not too fast for complex info
            "tone": "confident",
            "rate": 150  # Slower for finance (default ~200)
        },
        "finance_energetic": {
            "voice_id": "professional_female_clear",
            "stability": 0.6,
            "clarity": 0.9,
            "pace": "slightly_fast",
            "tone": "engaging",
            "rate": 170
        },
        "default": {
            "voice_id": "default",
            "stability": 0.5,
            "clarity": 0.75,
            "pace": "normal",
            "tone": "neutral",
            "rate": 180
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
        Generate audio using Chatterbox TTS API with optional presets.
        
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
            logger.info(f"Generating voiceover with Chatterbox (preset: {preset or 'default'})")
            
            # Apply preset if specified
            config = self.VOICE_PRESETS.get(preset or "default", self.VOICE_PRESETS["default"])
            voice_id = voice_id or config.get("voice_id")
            
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            
            # Check for Chatterbox API configuration
            api_key = os.getenv("CHATTERBOX_API_KEY")
            api_url = os.getenv("CHATTERBOX_API_URL", "https://api.chatterboxtts.com/v1/synthesize")
            
            if api_key:
                # Use actual Chatterbox API
                logger.info("Using Chatterbox TTS API")
                try:
                    import requests
                    
                    # Prepare API request
                    headers = {
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json"
                    }
                    
                    payload = {
                        "text": text,
                        "voice_id": voice_id,
                        "language": language,
                        "stability": config.get("stability", 0.5),
                        "clarity": config.get("clarity", 0.75),
                        "speed": config.get("rate", 180) / 200.0  # Normalize to 0.0-1.0 range
                    }
                    
                    logger.info(f"Calling Chatterbox API with voice: {voice_id}")
                    response = requests.post(api_url, headers=headers, json=payload, timeout=60)
                    
                    if response.status_code == 200:
                        # Save audio file
                        with open(output_path, "wb") as f:
                            f.write(response.content)
                        logger.info(f"Generated audio via Chatterbox API at {output_path}")
                        return output_path
                    else:
                        logger.warning(f"Chatterbox API returned status {response.status_code}: {response.text}")
                        logger.warning("Falling back to pyttsx3")
                        
                except Exception as api_error:
                    logger.warning(f"Chatterbox API call failed: {api_error}")
                    logger.warning("Falling back to pyttsx3")
            else:
                logger.info("CHATTERBOX_API_KEY not found, using pyttsx3 fallback")
            
            # Fallback to pyttsx3
            try:
                import pyttsx3
                engine = pyttsx3.init()
                
                # Adjust pyttsx3 based on preset
                voices = engine.getProperty('voices')
                
                # Try to find appropriate voice based on preset
                if preset and "finance" in preset:
                    # Try to find a male/deeper voice for finance
                    for voice in voices:
                        if 'male' in voice.name.lower() or 'david' in voice.name.lower():
                            engine.setProperty('voice', voice.id)
                            break
                
                # Set speech rate based on preset
                rate = config.get("rate", 180)
                engine.setProperty('rate', rate)
                engine.setProperty('volume', 0.9)
                
                logger.info(f"Using pyttsx3 with rate={rate}, voice={voice_id}")
                
                engine.save_to_file(text, output_path)
                engine.runAndWait()
                logger.info(f"Generated audio at {output_path}")
                
            except ImportError:
                logger.warning("pyttsx3 not found, creating dummy file")
                with open(output_path, "wb") as f:
                    f.write(b"DUMMY AUDIO CONTENT")
            
            if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
                raise AudioGenerationError("Failed to generate audio file")

            return output_path
            
        except Exception as e:
            raise AudioGenerationError(f"Chatterbox TTS failed: {str(e)}") from e
