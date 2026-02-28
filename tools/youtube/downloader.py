import os
import logging
from pathlib import Path
import yt_dlp
from core.exceptions import VideoDownloadError

logger = logging.getLogger(__name__)

def download_video(video_url: str, output_path: str) -> str:
    """
    Download a video from a URL using yt-dlp.
    
    Args:
        video_url: URL of the video to download.
        output_path: Destination path for the downloaded file.
        
    Returns:
        str: Path to the downloaded video.
    """
    try:
        logger.info(f"Downloading video from {video_url}")
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        ydl_opts = {
            "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "outtmpl": output_path,
            "quiet": False,
            "no_warnings": False,
            "overwrites": True,
            
            # Anti-bot detection measures
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "referer": "https://www.youtube.com/",
            
            # Network options
            "retries": 10,
            "fragment_retries": 10,
            "skip_unavailable_fragments": True,
            
            # Extractor options to bypass restrictions
            "extractor_args": {
                "youtube": {
                    "player_client": ["android", "web"],
                    "player_skip": ["webpage", "configs"],
                }
            },
            
            # Additional headers
            "http_headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-us,en;q=0.5",
                "Sec-Fetch-Mode": "navigate",
            },
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])
            
        if not os.path.exists(output_path):
             raise VideoDownloadError(f"Download completed but file not found at {output_path}")

        logger.info(f"Successfully downloaded video to {output_path}")
        return output_path

    except yt_dlp.utils.DownloadError as e:
        error_msg = str(e)
        if "403" in error_msg or "Forbidden" in error_msg:
            logger.error("YouTube blocked the download. This may be due to rate limiting or bot detection.")
            raise VideoDownloadError(
                "YouTube download blocked (403 Forbidden). Try again later or use a different video."
            ) from e
        raise VideoDownloadError(f"Video download failed: {e}") from e
    except Exception as e:
        raise VideoDownloadError(f"Video download failed: {e}") from e

