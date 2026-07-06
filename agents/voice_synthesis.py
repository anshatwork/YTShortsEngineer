import re
from typing import Dict, Any
from agents.base import BaseAgent
from workflows.state import ShortsState
from tools.tts import select_tts_provider
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

            # Select provider with cascading fallback (shared with the edit API):
            # ElevenLabs (premium) → Chatterbox (premium alt) → Streamlabs Polly (free).
            tts_provider = select_tts_provider()

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
