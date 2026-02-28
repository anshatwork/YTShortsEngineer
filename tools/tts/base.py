from abc import ABC, abstractmethod
import os
from pathlib import Path
from typing import Optional

class BaseTTSProvider(ABC):
    """
    Abstract Base Class for Text-to-Speech Providers.
    """
    
    @abstractmethod
    def generate_audio(
        self,
        text: str,
        output_path: str,
        voice_id: Optional[str] = None,
        language: str = "en"
    ) -> str:
        """
        Generate audio from text.
        
        Args:
            text: The text to convert to speech.
            output_path: The file path to save the audio to.
            voice_id: Specific voice ID to use (if supported).
            language: Language code (default: "en").
            
        Returns:
            str: Path to the generated audio file.
        """
        pass
