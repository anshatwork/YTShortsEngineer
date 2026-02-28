import os
import logging
from pathlib import Path
from typing import List, Optional, Union
from moviepy import VideoFileClip, AudioFileClip, CompositeVideoClip, TextClip, ColorClip
from moviepy.video import fx as vfx
from core.exceptions import RenderingError

logger = logging.getLogger(__name__)

def compose_video(
    fetched_video_path: Optional[str],
    background_video_path: Optional[str],
    voiceover_path: Optional[str],
    caption_clips: List[TextClip],
    output_path: str,
    audio_mode: str = "voiceover",
    video_mode: str = "split_screen",
    target_width: int = 1080,
    target_height: int = 1920,
) -> str:
    """
    Flexible video composition engine.
    
    Args:
        fetched_video_path: Path to the downloaded video.
        background_video_path: Path to the background video.
        voiceover_path: Path to the TTS audio.
        caption_clips: List of TextClip objects.
        output_path: Destination path.
        audio_mode: "voiceover", "fetched_video", "bg_video"
        video_mode: "split_screen", "fetched_video", "bg_video"
    """
    try:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        half_h = target_height // 2

        # 1. Prepare Audio
        audio_clip = None
        if audio_mode == "voiceover" and voiceover_path:
            audio_clip = AudioFileClip(voiceover_path)
        elif audio_mode == "fetched_video" and fetched_video_path:
            audio_clip = VideoFileClip(fetched_video_path).audio
        elif audio_mode == "bg_video" and background_video_path:
            audio_clip = VideoFileClip(background_video_path).audio
        
        if not audio_clip:
            raise RenderingError(f"No audio source found for mode: {audio_mode}")
            
        duration = audio_clip.duration

        # 2. Prepare Video Tracks
        video_tracks = []
        
        # Helper to process and resize clips
        def process_clip(path, height, pos):
            clip = VideoFileClip(path)
            if clip.duration < duration:
                clip = clip.with_effects([vfx.Loop(duration=duration)])
            else:
                clip = clip.subclipped(0, duration)
            
            clip = clip.resized(height=height)
            if clip.w > target_width:
                clip = clip.with_effects([vfx.Crop(x_center=clip.w // 2, width=target_width)])
            else:
                clip = clip.resized(width=target_width)
            
            return clip.with_position(pos)

        if video_mode == "split_screen":
            if not fetched_video_path or not background_video_path:
                raise RenderingError("Split screen requires both fetched and background videos")
            
            top = process_clip(fetched_video_path, half_h, (0, 0))
            bottom = process_clip(background_video_path, half_h, (0, half_h))
            video_tracks.extend([top, bottom])
            
        elif video_mode == "fetched_video":
            if not fetched_video_path:
                raise RenderingError("Fetched video mode requires a fetched video path")
            full = process_clip(fetched_video_path, target_height, (0, 0))
            video_tracks.append(full)
            
        elif video_mode == "bg_video":
            if not background_video_path:
                raise RenderingError("Background video mode requires a background video path")
            full = process_clip(background_video_path, target_height, (0, 0))
            video_tracks.append(full)

        # 3. Add Captions (only if audio is voiceover)
        if audio_mode == "voiceover":
            video_tracks.extend(caption_clips)

        # 4. Composite
        final = CompositeVideoClip(
            video_tracks,
            size=(target_width, target_height),
        ).with_audio(audio_clip)

        # 5. Write File
        final.write_videofile(
            output_path,
            fps=30,
            codec="libx264",
            audio_codec="aac",
            preset="medium",
            threads=4,
            ffmpeg_params=["-pix_fmt", "yuv420p", "-movflags", "+faststart"],
            logger=None,
        )

        # Cleanup
        for track in video_tracks:
            if hasattr(track, 'close'): track.close()
        audio_clip.close()
        final.close()

        return output_path

    except Exception as e:
        raise RenderingError(f"Video composition failed: {e}") from e
