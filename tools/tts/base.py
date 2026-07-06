from abc import ABC, abstractmethod
import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Optional

from core.exceptions import AudioGenerationError

logger = logging.getLogger(__name__)


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
        language: str = "en",
        preset: Optional[str] = None,
    ) -> str:
        """
        Generate audio from text.

        Args:
            text: The text to convert to speech.
            output_path: The file path to save the audio to.
            voice_id: Specific voice ID to use (if supported).
            language: Language code (default: "en").
            preset: Optional content preset name (e.g. "finance"). Providers
                that don't use presets may ignore it.

        Returns:
            str: Path to the generated audio file.
        """
        pass


def _pyttsx3_to_file(
    text: str,
    output_path: str,
    *,
    preset: Optional[str] = None,
    rate: int = 180,
    volume: float = 0.9,
) -> str:
    """Render *text* to *output_path* using the local pyttsx3 engine.

    pyttsx3 (SAPI5 on Windows) emits a **WAV** stream, so we always render to a
    temporary ``.wav`` and then transcode to whatever extension *output_path*
    requests via ffmpeg. This prevents the long-standing bug where a WAV stream
    was written to a ``.mp3`` filename, leaving the browser unable to play it
    and tripping ffmpeg probe/concat in the attach pipeline.

    Raises ``AudioGenerationError`` on any failure — there is no silent
    dummy-file fallback (an unplayable file that passes a size check is worse
    than a clear error).
    """
    try:
        import pyttsx3
    except ImportError as exc:  # pyttsx3 genuinely unavailable
        raise AudioGenerationError(
            "pyttsx3 is not installed; cannot generate local TTS"
        ) from exc

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    tmp_fd, tmp_wav = tempfile.mkstemp(suffix=".wav")
    os.close(tmp_fd)
    try:
        engine = pyttsx3.init()

        # For finance-style presets prefer a deeper/male voice if available.
        if preset and "finance" in preset:
            for voice in engine.getProperty("voices"):
                name = (voice.name or "").lower()
                if "male" in name or "david" in name:
                    engine.setProperty("voice", voice.id)
                    break

        engine.setProperty("rate", rate)
        engine.setProperty("volume", volume)

        logger.info("Using pyttsx3 fallback (rate=%s) -> %s", rate, output_path)
        engine.save_to_file(text, tmp_wav)
        engine.runAndWait()

        if not os.path.exists(tmp_wav) or os.path.getsize(tmp_wav) == 0:
            raise AudioGenerationError("pyttsx3 produced no audio")

        ext = Path(output_path).suffix.lower()
        if ext == ".wav":
            shutil.move(tmp_wav, output_path)
        else:
            import ffmpeg  # local import — keeps module load fast

            out_kwargs = {}
            if ext == ".mp3":
                out_kwargs["acodec"] = "libmp3lame"
            elif ext in (".m4a", ".aac"):
                out_kwargs["acodec"] = "aac"
            (
                ffmpeg
                .input(tmp_wav)
                .output(output_path, **out_kwargs)
                .overwrite_output()
                .run(capture_stdout=True, capture_stderr=True)
            )

        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            raise AudioGenerationError("Failed to write transcoded audio file")
        return output_path

    except AudioGenerationError:
        raise
    except Exception as exc:  # noqa: BLE001 — surface a clean error
        raise AudioGenerationError(f"pyttsx3 TTS failed: {exc}") from exc
    finally:
        # Clean up the temp wav unless we moved it into place.
        try:
            if os.path.exists(tmp_wav) and (
                Path(output_path).resolve() != Path(tmp_wav).resolve()
            ):
                os.remove(tmp_wav)
        except OSError:
            pass
