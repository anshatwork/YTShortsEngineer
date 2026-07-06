import asyncio
import logging
from pathlib import Path
from typing import Optional

from tools.tts.base import BaseTTSProvider, _pyttsx3_to_file
from core.exceptions import AudioGenerationError

logger = logging.getLogger(__name__)


class EdgeTTS(BaseTTSProvider):
    """Free, high-quality neural TTS via Microsoft Edge's read-aloud voices.

    Uses the ``edge-tts`` package, which streams audio from Microsoft's public
    Edge endpoint. No API key, no GPU, and near-premium quality — this is the
    preferred free default over the robotic pyttsx3/SAPI5 voice.

    Falls back to ``_pyttsx3_to_file`` on any failure (e.g. offline) so audio
    generation degrades gracefully rather than hard-failing.
    """

    # Map the canonical VoicePreset names to Edge neural voices.
    VOICE_PRESETS = {
        "finance": {
            "voice": "en-US-ChristopherNeural",  # warm, authoritative male
            "rate": "-5%",
        },
        "finance_energetic": {
            "voice": "en-US-AriaNeural",  # bright, engaging female
            "rate": "+0%",
        },
        "default": {
            "voice": "en-US-GuyNeural",  # natural, neutral male
            "rate": "+0%",
        },
    }

    def generate_audio(
        self,
        text: str,
        output_path: str,
        voice_id: Optional[str] = None,
        language: str = "en",
        preset: Optional[str] = None,
    ) -> str:
        config = self.VOICE_PRESETS.get(preset or "default", self.VOICE_PRESETS["default"])
        voice = voice_id or config["voice"]
        rate = config.get("rate", "+0%")

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        try:
            import edge_tts

            logger.info(
                "Generating voiceover with edge-tts (voice: %s, rate: %s)", voice, rate
            )

            async def _synthesize() -> None:
                communicate = edge_tts.Communicate(text, voice, rate=rate)
                await communicate.save(output_path)

            _run_async(_synthesize())

            if not Path(output_path).exists() or Path(output_path).stat().st_size == 0:
                raise AudioGenerationError("edge-tts produced no audio")

            logger.info("Generated audio via edge-tts at %s", output_path)
            return output_path

        except Exception as exc:  # noqa: BLE001 — degrade to local TTS
            logger.warning("edge-tts failed: %s", exc)
            logger.info("Falling back to pyttsx3 for local TTS")
            return _pyttsx3_to_file(text, output_path, preset=preset)


def _run_async(coro) -> None:
    """Run *coro* to completion whether or not an event loop is already running.

    TTS generation runs in a FastAPI ``BackgroundTasks`` worker thread (no loop),
    so ``asyncio.run`` is the normal path; the running-loop branch is a safety net.
    """
    try:
        asyncio.run(coro)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(coro)
        finally:
            loop.close()
