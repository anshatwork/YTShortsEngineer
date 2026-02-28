"""
tools/youtube/transcript.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Fetch a YouTube video transcript without Whisper or OAuth.

Uses the `youtube-transcript-api` library which works for any video
that has auto-generated or manually provided captions.

Public surface
--------------
    extract_video_id(url_or_id)  → str
    fetch_transcript(url_or_id)  → str          (plain text, pipeline-ready)
    fetch_timed_segments(url_or_id) → list[dict] (preserves start/duration)
"""

import logging
import re
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse, parse_qs

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Video ID extraction
# ---------------------------------------------------------------------------

_YT_ID_RE = re.compile(
    r"(?:v=|youtu\.be/|/v/|/embed/|/shorts/)([A-Za-z0-9_-]{11})"
)


def extract_video_id(url_or_id: str) -> str:
    """
    Return the 11-character YouTube video ID from a URL or bare ID.

    Supports:
        https://www.youtube.com/watch?v=<ID>
        https://youtu.be/<ID>
        https://www.youtube.com/shorts/<ID>
        https://www.youtube.com/embed/<ID>
        <ID>  (bare 11-char ID passed directly)

    Raises:
        ValueError: If no valid ID can be extracted.
    """
    url_or_id = url_or_id.strip()

    # Bare ID: exactly 11 valid base64url chars
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", url_or_id):
        return url_or_id

    # Try ?v= query param first (most common)
    parsed = urlparse(url_or_id)
    qs = parse_qs(parsed.query)
    if "v" in qs and qs["v"]:
        return qs["v"][0]

    # Regex fallback for path-based URLs (youtu.be/..., /shorts/..., etc.)
    match = _YT_ID_RE.search(url_or_id)
    if match:
        return match.group(1)

    raise ValueError(
        f"Cannot extract a YouTube video ID from: {url_or_id!r}. "
        "Expected a YouTube URL or an 11-character video ID."
    )


# ---------------------------------------------------------------------------
# Transcript fetching
# ---------------------------------------------------------------------------

def fetch_timed_segments(
    url_or_id: str,
    languages: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Return transcript as a list of timed segment dicts.

    Each segment:
        {
            "text":     str,   # Caption text
            "start":    float, # Start time in seconds
            "duration": float, # Duration in seconds
        }

    Compatible with youtube-transcript-api v0.x (class-method API) and
    v1.x (instance-method API).

    Args:
        url_or_id:  YouTube URL or bare video ID.
        languages:  Preferred languages in priority order (default: ["en"]).

    Raises:
        RuntimeError: If `youtube-transcript-api` is not installed or the
                      transcript cannot be fetched.
    """
    try:
        from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound
    except ImportError as exc:
        raise RuntimeError(
            "youtube-transcript-api is not installed. "
            "Run: pip install youtube-transcript-api"
        ) from exc

    video_id = extract_video_id(url_or_id)
    if languages is None:
        languages = ["en"]

    logger.info(f"Fetching transcript for video ID: {video_id} (languages={languages})")

    def _fetch(vid: str, langs: List[str]) -> List[Dict[str, Any]]:
        """Call fetch() (v1.x instance API) or get_transcript() (v0.x class API)."""
        api = YouTubeTranscriptApi()
        if hasattr(api, "fetch"):
            # v1.x: instance method; returns a FetchedTranscript (iterable of dicts)
            result = api.fetch(vid, languages=langs)
            return [{"text": s.text, "start": s.start, "duration": s.duration} for s in result]
        # v0.x: class-method fallback
        return YouTubeTranscriptApi.get_transcript(vid, languages=langs)  # type: ignore[attr-defined]

    def _list_languages(vid: str) -> List[str]:
        """Return all available language codes for *vid*."""
        api = YouTubeTranscriptApi()
        if hasattr(api, "list"):
            # v1.x
            return [t.language_code for t in api.list(vid)]
        # v0.x
        return [t.language_code for t in YouTubeTranscriptApi.list_transcripts(vid)]  # type: ignore[attr-defined]

    try:
        segments = _fetch(video_id, languages)
        logger.info(f"Fetched {len(segments)} transcript segments.")
        return segments
    except TranscriptsDisabled:
        raise RuntimeError(
            f"Transcripts are disabled for video '{video_id}'. "
            "The video owner has turned off captions."
        )
    except NoTranscriptFound:
        # Try any available language as fallback before giving up
        logger.warning(
            f"No transcript found in languages={languages} for '{video_id}'. "
            "Attempting to list all available transcripts …"
        )
        try:
            available = _list_languages(video_id)
            logger.info(f"Available language codes: {available}")
            if available:
                segments = _fetch(video_id, available)
                logger.info(
                    f"Fetched transcript in '{available[0]}' ({len(segments)} segments)."
                )
                return segments
        except Exception as fallback_exc:
            logger.error(f"Fallback transcript fetch failed: {fallback_exc}")
        raise RuntimeError(
            f"No transcript available for video '{video_id}'. "
            f"Tried languages: {languages}. "
            "The video may be private, or captions may not exist."
        )
    except Exception as exc:
        raise RuntimeError(
            f"Failed to fetch transcript for video '{video_id}': {exc}"
        ) from exc


def fetch_transcript(
    url_or_id: str,
    languages: Optional[List[str]] = None,
) -> str:
    """
    Return the full transcript as a single plain-text string.

    Suitable as a drop-in replacement for the Whisper-produced transcript
    consumed by the Long-to-Shorts pipeline.

    Args:
        url_or_id:  YouTube URL or bare video ID.
        languages:  Preferred languages (default: ["en"]).

    Returns:
        Single string with all caption text joined by spaces.

    Raises:
        RuntimeError: On any fetch failure (see fetch_timed_segments).
    """
    segments = fetch_timed_segments(url_or_id, languages=languages)
    text = " ".join(seg["text"].strip() for seg in segments if seg.get("text"))
    logger.info(f"Transcript assembled: {len(text)} characters.")
    return text
