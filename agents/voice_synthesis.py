import os
import re
from typing import Dict, Any
from agents.base import BaseAgent
from workflows.state import ShortsState
from tools.tts.elevenlabs import ElevenLabsTTS
from tools.tts.chatterbox import ChatterboxTTS
from core.config import settings

class VoiceSynthesisAgent(BaseAgent):
    """
    Agent responsible for generating voiceovers.
    """
    
    def _clean_script_for_tts(self, script: str) -> str:
        """
        Remove structure markers from script for TTS generation.
        Keeps only the actual content to be spoken.
        
        Args:
            script: Raw script with [HOOK], [BRIDGE], [CORE SCRIPT] markers
            
        Returns:
            Clean script text without markers
        """
        # First, handle escaped newlines (literal \n characters from LLM output)
        # Convert literal \n to actual newlines
        if '\\n' in script:
            self.logger.debug("Detected escaped newlines in script, converting to actual newlines")
            script = script.replace('\\n', '\n')
        
        # Remove all structure markers (including trailing whitespace/newlines)
        cleaned = re.sub(r'\[HOOK\]\s*\n?', '', script)
        cleaned = re.sub(r'\[BRIDGE\]\s*\n?', '', cleaned)
        cleaned = re.sub(r'\[CORE SCRIPT\]\s*\n?', '', cleaned)
        
        # Normalize whitespace:
        # 1. First, preserve paragraph breaks by protecting double newlines
        cleaned = re.sub(r'\n\s*\n', '<<PARAGRAPH>>', cleaned)
        
        # 2. Convert single newlines to spaces (for natural TTS flow)
        cleaned = re.sub(r'\n', ' ', cleaned)
        
        # 3. Restore paragraph breaks as double newlines
        cleaned = cleaned.replace('<<PARAGRAPH>>', '\n\n')
        
        # 4. Clean up multiple spaces
        cleaned = re.sub(r' +', ' ', cleaned)
        
        # 5. Final trim
        cleaned = cleaned.strip()
        
        return cleaned
    
    def run(self, state: ShortsState) -> Dict[str, Any]:
        try:
            self.logger.info("Generating voiceover")
            
            script = state.get("script")
            if not script:
                raise ValueError("No script found in state for voice synthesis")
            
            # Clean script by removing structure markers
            clean_script = self._clean_script_for_tts(script)
            self.logger.info(f"Cleaned script for TTS (removed structure markers)")
            self.logger.debug(f"Original length: {len(script)} chars, Cleaned length: {len(clean_script)} chars")
            self.logger.debug(f"Original script preview: {script[:100]}...")
            self.logger.debug(f"Cleaned script preview: {clean_script[:100]}...")
                
            output_path = settings.OUTPUT_DIR / f"voiceover_{state.get('broad_topic', 'shorts')[:10]}.mp3"
            
            # Select Provider with Cascading Fallback
            # Priority: ElevenLabs (premium) → Streamlabs Polly (free) → Chatterbox (premium alt) → pyttsx3 (local)
            
            # Priority 1: ElevenLabs (premium, requires key)
            if os.getenv("ELEVENLABS_API_KEY"):
                tts_provider = ElevenLabsTTS()
                self.logger.info("Selected TTS Provider: ElevenLabs (Premium)")
                
            # Priority 2: Streamlabs Polly (free, no key needed)
            elif not os.getenv("CHATTERBOX_API_KEY"):
                from tools.tts.streamlabs_polly import StreamlabsPollyTTS
                tts_provider = StreamlabsPollyTTS()
                self.logger.info("Selected TTS Provider: Streamlabs Polly (Free)")
                
            # Priority 3: Chatterbox (premium alternative, requires key)
            elif os.getenv("CHATTERBOX_API_KEY"):
                tts_provider = ChatterboxTTS()
                self.logger.info("Selected TTS Provider: Chatterbox (Premium)")
                
            # Priority 4: Streamlabs Polly as final fallback (will use pyttsx3 internally if API fails)
            else:
                from tools.tts.streamlabs_polly import StreamlabsPollyTTS
                tts_provider = StreamlabsPollyTTS()
                self.logger.info("Selected TTS Provider: Streamlabs Polly (Fallback)")
                
            audio_path = tts_provider.generate_audio(
                text=clean_script,  # Use cleaned script instead of raw script
                output_path=str(output_path)
            )
            
            self.logger.info(f"Voiceover generated at: {audio_path}")
            
            return {
                "voiceover_audio_path": audio_path,
                "current_step": "voiceover_generated"
            }
            
        except Exception as e:
            self.logger.error(f"Voice synthesis failed: {str(e)}")
            raise Exception(f"Failed to generate voiceover: {str(e)}")
