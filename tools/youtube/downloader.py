import os
import logging
from pathlib import Path
import yt_dlp
from core.exceptions import VideoDownloadError

logger = logging.getLogger(__name__)

def fetch_video_title(video_url: str) -> str | None:
    """Best-effort lookup of a video's title (metadata only, no download).

    Returns the title string, or ``None`` on any failure — this never raises,
    so callers can use it inline without guarding the whole flow.
    """
    try:
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
        title = (info or {}).get("title")
        return title.strip() if isinstance(title, str) and title.strip() else None
    except Exception as exc:  # noqa: BLE001 — title is non-essential
        logger.warning("Could not fetch video title for %s: %s", video_url, exc)
        return None


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


def download_audio(video_url: str, output_path: str) -> str:
    """Download only the audio track of a YouTube video as an mp3.

    Used to pull a trending song's audio for use as background music (the
    YouTube music source — see tools/assets/sources/music_youtube.py). Picks the
    best audio-only stream and transcodes to mp3 via ffmpeg, reusing the same
    anti-bot options as :func:`download_video`.

    Args:
        video_url:   YouTube watch URL.
        output_path: Destination path for the mp3. The ``.mp3`` extension is
                     enforced (yt-dlp's FFmpegExtractAudio rewrites the suffix),
                     so pass either ``foo`` or ``foo.mp3``.

    Returns:
        str: Path to the downloaded mp3 (always ends in ``.mp3``).
    """
    # FFmpegExtractAudio replaces whatever container yt-dlp downloaded with .mp3,
    # so normalise the target up front and hand yt-dlp the stem as the template.
    final_path = output_path if output_path.lower().endswith(".mp3") else f"{output_path}.mp3"
    stem = final_path[: -len(".mp3")]

    try:
        logger.info("Downloading audio from %s", video_url)
        Path(final_path).parent.mkdir(parents=True, exist_ok=True)

        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": stem + ".%(ext)s",
            "quiet": True,
            "no_warnings": True,
            "overwrites": True,
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }
            ],
            # Anti-bot detection measures (mirrors download_video).
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "referer": "https://www.youtube.com/",
            "retries": 10,
            "fragment_retries": 10,
            "skip_unavailable_fragments": True,
            "extractor_args": {
                "youtube": {
                    "player_client": ["android", "web"],
                    "player_skip": ["webpage", "configs"],
                }
            },
            "http_headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-us,en;q=0.5",
                "Sec-Fetch-Mode": "navigate",
            },
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])

        if not os.path.exists(final_path):
            raise VideoDownloadError(f"Audio download completed but file not found at {final_path}")

        logger.info("Successfully downloaded audio to %s", final_path)
        return final_path

    except yt_dlp.utils.DownloadError as e:
        error_msg = str(e)
        if "403" in error_msg or "Forbidden" in error_msg:
            logger.error("YouTube blocked the audio download (rate limiting or bot detection).")
            raise VideoDownloadError(
                "YouTube audio download blocked (403 Forbidden). Try again later or use a different track."
            ) from e
        raise VideoDownloadError(f"Audio download failed: {e}") from e
    except Exception as e:
        raise VideoDownloadError(f"Audio download failed: {e}") from e

