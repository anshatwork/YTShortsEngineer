import logging
import whisper
from typing import List, Dict, Any
from core.exceptions import AudioGenerationError

logger = logging.getLogger(__name__)

def extract_word_timestamps(
    audio_path: str, model_name: str = "base"
) -> List[Dict[str, Any]]:
    """
    Extract word-level timestamps from an audio file using OpenAI Whisper.
    
    Args:
        audio_path: Path to the audio file.
        model_name: Whisper model size (tiny, base, small, medium, large).
        
    Returns:
        List of dictionaries containing word, start, and end times.
    """
    try:
        logger.info(f"Extracting timestamps using Whisper model: {model_name}")

        model = whisper.load_model(model_name)
        result = model.transcribe(
            audio_path,
            word_timestamps=True,
            language="en",
        )

        words: List[Dict[str, Any]] = []

        for segment in result.get("segments", []):
            for w in segment.get("words", []):
                words.append(
                    {
                        "word": w.get("word", "").strip(),
                        "start": w.get("start", 0.0),
                        "end": w.get("end", 0.0),
                    }
                )

        return words

    except Exception as e:
        raise AudioGenerationError(f"Timestamp extraction failed: {e}") from e
