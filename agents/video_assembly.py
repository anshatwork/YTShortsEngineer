from typing import Dict, Any, Optional
from pathlib import Path
from moviepy.audio.io.AudioFileClip import AudioFileClip
from moviepy.video.io.VideoFileClip import VideoFileClip

from agents.base import BaseAgent
from workflows.state import ShortsState
from core.config import settings
from tools.youtube.downloader import download_video
from tools.video_editing.processor import extract_word_timestamps
from tools.video_editing.caption_generator import create_caption_clips
from tools.video_editing.layout_engine import compose_video

class VideoAssemblyAgent(BaseAgent):
    """
    Agent responsible for assembling the final video based on composition settings.
    """
    
    def run(self, state: ShortsState) -> Dict[str, Any]:
        try:
            self.logger.info("Starting flexible video assembly")
            
            selected_video = state.get("selected_video")
            voiceover_path = state.get("voiceover_audio_path")
            background_path = state.get("background_video_path")
            
            # Handle overlay_style mapping to video_mode and audio_mode
            overlay_style = state.get("overlay_style")
            if overlay_style == "background_only":
                # Background video only with voiceover and captions
                video_mode = "bg_video"
                audio_mode = "voiceover"
                self.logger.info("Using overlay_style='background_only': bg_video + voiceover + captions")
            else:
                # Use explicit modes from state or defaults
                audio_mode = state.get("audio_mode", "voiceover")
                video_mode = state.get("video_mode", "split_screen")
            
            # --- 1. Downloader / Asset Check ---
            downloaded_video_path = None
            if video_mode in ["split_screen", "fetched_video"] or audio_mode == "fetched_video":
                if not selected_video:
                    raise ValueError(f"Selected video metadata required for mode: {video_mode}/{audio_mode}")
                
                video_url = selected_video["url"]
                video_id = selected_video["video_id"]
                download_path = settings.OUTPUT_DIR / f"{video_id}.mp4"
                
                if not download_path.exists():
                    self.logger.info(f"Downloading video: {video_id}")
                    downloaded_video_path = download_video(video_url, str(download_path))
                else:
                    self.logger.info(f"Video already exists: {download_path}")
                    downloaded_video_path = str(download_path)
            
            # --- 1b. Background Video Validation ---
            if video_mode in ["split_screen", "bg_video"] or audio_mode == "bg_video":
                if not background_path:
                    raise ValueError(f"Background video path required for mode: {video_mode}/{audio_mode}")
                
                bg_path = Path(background_path)
                if not bg_path.exists():
                    raise FileNotFoundError(f"Background video not found at: {background_path}")
                
                self.logger.info(f"Using background video: {background_path}")

            # --- 2. Captions / Timestamps (Voiceover only) ---
            word_timestamps = []
            caption_clips = []
            if audio_mode == "voiceover" and voiceover_path:
                self.logger.info("Extracting word timestamps for voiceover...")
                word_timestamps = extract_word_timestamps(voiceover_path, model_name=settings.WHISPER_MODEL)
                
                with AudioFileClip(voiceover_path) as audio_clip:
                    voiceover_duration = audio_clip.duration
                
                caption_clips = create_caption_clips(word_timestamps, voiceover_duration)

            # --- 3. Final Assembly ---
            self.logger.info(f"Composing video with Audio Mode: {audio_mode}, Video Mode: {video_mode}")
            
            output_filename = f"final_{state.get('broad_topic', 'shorts')[:10]}_{video_mode}.mp4"
            final_path = settings.OUTPUT_DIR / output_filename
            
            final_video_path = compose_video(
                fetched_video_path=downloaded_video_path,
                background_video_path=background_path,
                voiceover_path=voiceover_path,
                caption_clips=caption_clips,
                output_path=str(final_path),
                audio_mode=audio_mode,
                video_mode=video_mode,
                target_width=settings.VIDEO_WIDTH,
                target_height=settings.VIDEO_HEIGHT
            )
            
            self.logger.info(f"Video assembly complete: {final_video_path}")
            
            return {
                "downloaded_video_path": downloaded_video_path,
                "word_timestamps": word_timestamps,
                "final_video_path": final_video_path,
                "review_status": "pending",
                "current_step": "awaiting_review"
            }
            
        except Exception as e:
            self.logger.error(f"Video assembly failed: {str(e)}")
            raise Exception(f"Failed to assemble video: {str(e)}")
