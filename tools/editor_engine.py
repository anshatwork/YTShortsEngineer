"""
Video Editing Engine for YouTube Shorts Creator
Handles video download, voiceover generation, timestamp extraction,
caption creation, and final video assembly.
"""

import os
import logging
from typing import List, Dict, Any, Optional
from pathlib import Path

import yt_dlp
import whisper

# MoviePy 2.x Imports
from moviepy import VideoFileClip, AudioFileClip, CompositeVideoClip, TextClip, ColorClip
from moviepy.video import fx as vfx

from elevenlabs.client import ElevenLabs
from elevenlabs import VoiceSettings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def download_video(video_url: str, output_path: str) -> str:
    try:
        logger.info(f"Downloading video from {video_url}")
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        ydl_opts = {
            "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "outtmpl": output_path,
            "quiet": False,
            "no_warnings": False,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])

        return output_path

    except Exception as e:
        raise RuntimeError(f"Video download failed: {e}") from e


def generate_voiceover(
    script: str,
    output_path: str,
    api_key: Optional[str] = None,
    voice_id: Optional[str] = None,
) -> str:
    try:
        logger.info("Generating voiceover with ElevenLabs")

        api_key = api_key or os.getenv("ELEVENLABS_API_KEY")
        voice_id = voice_id or os.getenv(
            "ELEVENLABS_VOICE_ID", "gMRjEAcWCvjoyqIfZqlp"
        )

        if not api_key:
            raise ValueError("ELEVENLABS_API_KEY is missing")

        client = ElevenLabs(api_key=api_key)

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        audio_stream = client.text_to_speech.convert(
            text=script,
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
        raise RuntimeError(f"Voiceover generation failed: {e}") from e


def extract_word_timestamps(
    audio_path: str, model_name: str = "base"
) -> List[Dict[str, Any]]:
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
        raise RuntimeError(f"Timestamp extraction failed: {e}") from e


def create_caption_clips(
    timestamps: List[Dict[str, Any]],
    video_duration: float,
) -> List[TextClip]:
    try:
        clips: List[TextClip] = []

        for ts in timestamps:
            word = ts.get("word")
            if not word:
                continue

            start = float(ts["start"])
            end = min(float(ts["end"]), video_duration)
            duration = max(end - start, 0.01)

            emphasis = len(word) > 6 or word.isupper()

            clip = TextClip(
                text=word.upper(),
                font=r"C:\Windows\Fonts\impact.ttf",
                font_size=70 if emphasis else 60,
                color="yellow" if emphasis else "white",
                stroke_color="black",
                stroke_width=3,
                method="caption",
                text_align="center",
                size=(900, None),
            )

            clip = (
                clip
                .with_position("center")
                .with_start(start)
                .with_duration(duration)
            )

            if emphasis:
                clip = clip.resized(
                    lambda t, d=duration: 1 + 0.05 * (1 - abs(t - d / 2) / (d / 2))
                )

            clips.append(clip)

        return clips

    except Exception as e:
        raise RuntimeError(f"Caption creation failed: {e}") from e


def assemble_split_screen_video(
    trendy_video_path: str,
    background_video_path: Optional[str],
    voiceover_path: str,
    caption_clips: List[TextClip],
    output_path: str,
    target_width: int = 1080,
    target_height: int = 1920,
) -> str:
    try:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        # ---- AUDIO ----
        voiceover = AudioFileClip(voiceover_path)
        duration = voiceover.duration
        half_h = target_height // 2

        # ---- TOP VIDEO ----
        top = VideoFileClip(trendy_video_path)

        if top.duration < duration:
            # loops() is the method in 2.x or we can use fx
            # In 2.x it's often imported from vfx
            top = top.with_effects([vfx.Loop(duration=duration)])
        else:
            top = top.subclipped(0, duration)
        
        top = top.resized(height=half_h)

        if top.w > target_width:
            top = top.with_effects([
                vfx.Crop(x_center=top.w // 2, width=target_width)
            ])
        else:
            top = top.resized(width=target_width)

        top = top.with_position((0, 0))

        # ---- BOTTOM VIDEO ----
        if background_video_path and os.path.exists(background_video_path):
            bottom = VideoFileClip(background_video_path)

            if bottom.duration < duration:
                bottom = bottom.with_effects([vfx.Loop(duration=duration)])
            else:
                bottom = bottom.subclipped(0, duration)

            bottom = bottom.resized(height=half_h)

            if bottom.w > target_width:
                bottom = bottom.with_effects([
                    vfx.Crop(x_center=bottom.w // 2, width=target_width)
                ])
            else:
                bottom = bottom.resized(width=target_width)
        else:
            bottom = ColorClip(
                size=(target_width, half_h),
                color=(20, 20, 20),
                duration=duration,
            )

        bottom = bottom.with_position((0, half_h))

        # ---- COMPOSITE ----
        final = CompositeVideoClip(
            [top, bottom] + caption_clips,
            size=(target_width, target_height),
        ).with_audio(voiceover)

        # ---- CPU ENCODING (SAFE DEFAULT) ----
        final.write_videofile(
            output_path,
            fps=30,
            codec="libx264",
            audio_codec="aac",
            preset="medium",
            threads=4,
            ffmpeg_params=[
                "-pix_fmt", "yuv420p",
                "-movflags", "+faststart",
            ],
            logger=None,
        )

        # ---- CLEANUP ----
        top.close()
        bottom.close()
        voiceover.close()
        final.close()

        return output_path

    except Exception as e:
        raise RuntimeError(f"Video assembly failed: {e}") from e
