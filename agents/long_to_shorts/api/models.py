"""
agents/long_to_shorts/api/models.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Pydantic request and response schemas for the LongToShorts FastAPI server.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional, Tuple
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Shared type aliases
# ---------------------------------------------------------------------------

JobStatusLiteral = Literal["queued", "running", "done", "failed"]
EditOperation = Literal["tts", "music", "split_screen"]
VoicePreset = Literal["default", "finance", "finance_energetic"]
PrivacyStatus = Literal["private", "unlisted", "public"]


# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------

class JobRequest(BaseModel):
    """Body for POST /jobs."""

    # --- Source (exactly one of the two should be provided) ---
    youtube_url: Optional[str] = Field(
        default=None,
        description="YouTube video URL to download and process.",
        examples=["https://www.youtube.com/watch?v=dQw4w9WgXcQ"],
    )
    video_path: Optional[str] = Field(
        default=None,
        description="Absolute path to a local video file (alternative to youtube_url).",
    )
    transcript: Optional[str] = Field(
        default=None,
        description=(
            "Pre-supplied transcript text or path to a .txt file. "
            "Only used in local video mode. If omitted, Whisper auto-transcribes."
        ),
    )
    srt_path: Optional[str] = Field(
        default=None,
        description=(
            "Path to an .srt subtitle file (e.g. returned by POST /edit/uploads). "
            "Only used in local video mode. When provided, subtitles are burned "
            "from this file and the transcript is derived from it (no Whisper). "
            "If omitted, SubtitlesNode falls back to per-clip Whisper transcription."
        ),
    )

    # --- Pipeline options ---
    top_n: int = Field(default=3, ge=1, le=20, description="Max number of clips to extract.")
    add_subtitles: bool = Field(default=False, description="Burn subtitles into each clip.")
    add_top_text: bool = Field(default=False, description="Overlay hook text at top of each clip.")
    add_intro: bool = Field(default=True, description="Prepend title-card intro (IntroAttachNode).")
    clip_mode: Literal["portrait", "fullscreen"] = Field(
        default="portrait",
        description=(
            "'portrait' = 9:16 (1080×1920) reframing. "
            "'fullscreen' = native resolution, no reframing."
        ),
    )

    class Config:
        json_schema_extra = {
            "example": {
                "youtube_url": "https://www.youtube.com/watch?v=wJ4i_wRctq8",
                "top_n": 3,
                "add_subtitles": False,
                "add_top_text": True,
                "add_intro": True,
                "clip_mode": "portrait",
            }
        }


# ---------------------------------------------------------------------------
# Response – per-clip result
# ---------------------------------------------------------------------------

class ClipResult(BaseModel):
    """Mirrors `ClipObject` from agents/state.py – returned inside JobStatus."""

    clip_id: str
    path: Optional[str] = None
    timestamp_range: Tuple[float, float]
    hook_score: float
    title: Optional[str] = None
    summary: Optional[str] = None
    hook_text: Optional[str] = None
    hashtags: Optional[List[str]] = None


# ---------------------------------------------------------------------------
# Response – job status
# ---------------------------------------------------------------------------

class JobStatus(BaseModel):
    """Returned by GET /jobs/{job_id} and POST /jobs."""

    job_id: str
    status: Literal["queued", "running", "done", "failed"]
    created_at: datetime
    updated_at: datetime
    clips: Optional[List[ClipResult]] = Field(
        default=None,
        description="Present only when status == 'done'.",
    )
    error: Optional[str] = Field(
        default=None,
        description="Present only when status == 'failed'.",
    )
    current_node: Optional[str] = Field(
        default=None,
        description=(
            "Name of the pipeline node currently executing while status='running'. "
            "Lets the frontend display real per-stage progress instead of guessing."
        ),
    )


class JobListResponse(BaseModel):
    """Returned by GET /jobs."""

    jobs: List[JobStatus]
    total: int


# ---------------------------------------------------------------------------
# Edit requests / responses (Phase 1 = TTS; later phases add music + split-screen)
# ---------------------------------------------------------------------------

class TTSEditRequest(BaseModel):
    """Body for POST /edit/tts."""

    text: str = Field(..., min_length=1, max_length=5_000)
    voice_preset: VoicePreset = Field(default="default")
    parent_job_id: Optional[str] = Field(
        default=None,
        description="Optional — groups the resulting edit job under a parent clip job in the dashboard.",
    )
    attach_to_clip_id: Optional[str] = Field(
        default=None,
        description=(
            "If set, the generated TTS is prepended as a voice-over intro to the "
            "specified clip (parent_job_id required in this mode). Otherwise a "
            "standalone audio file is produced."
        ),
    )


class MusicEditRequest(BaseModel):
    """Body for POST /edit/add-music."""

    parent_job_id: str = Field(..., description="Parent clip-extraction job id.")
    clip_id: str = Field(..., description="Clip id within the parent job.")
    theme: Optional[str] = Field(
        default=None,
        description="AudioTheme value (e.g. 'professional', 'energetic'). Resolved via core/audio_theme_map.",
    )
    music_path: Optional[str] = Field(
        default=None,
        description="Explicit music file (overrides theme). Path must be readable by the server.",
    )
    music_upload_id: Optional[str] = Field(
        default=None,
        description="Alt: id returned by POST /api/v1/edit/uploads to use an uploaded file.",
    )
    volume_db: float = Field(
        default=-18.0,
        ge=-60.0,
        le=6.0,
        description="Music gain relative to source audio (-18 dB is the default ducked level).",
    )


SplitScreenAudioMode = Literal["fetched_video", "bg_video"]


class SplitScreenEditRequest(BaseModel):
    """Body for POST /edit/split-screen."""

    parent_job_id: str = Field(..., description="Parent clip-extraction job id.")
    clip_id: str = Field(..., description="Clip id within the parent job (renders on top).")

    # Exactly one background source must be supplied
    background_default: bool = Field(
        default=False,
        description="Use $BACKGROUND_VIDEO_PATH (the env-configured gameplay loop).",
    )
    background_path: Optional[str] = Field(
        default=None,
        description="Server-readable absolute path to a local background mp4.",
    )
    background_url: Optional[str] = Field(
        default=None,
        description="YouTube URL — downloaded via yt-dlp at job time.",
    )
    background_upload_id: Optional[str] = Field(
        default=None,
        description="Alt: id returned by POST /api/v1/edit/uploads.",
    )

    audio_mode: SplitScreenAudioMode = Field(
        default="fetched_video",
        description=(
            "'fetched_video' = use the source clip's audio (typical for narrated shorts). "
            "'bg_video' = use the background video's audio."
        ),
    )


class EditJob(BaseModel):
    """Returned by edit endpoints. Mirrors JobStatus but for edit operations."""

    edit_job_id: str
    operation: EditOperation
    parent_job_id: Optional[str] = None
    clip_id: Optional[str] = None
    status: JobStatusLiteral
    created_at: datetime
    updated_at: datetime
    output_path: Optional[str] = Field(
        default=None,
        description="Local filesystem path of the produced artifact (present when status='done').",
    )
    output_url: Optional[str] = Field(
        default=None,
        description="URL the frontend can fetch/stream from (served via /static).",
    )
    error: Optional[str] = None


class EditJobListResponse(BaseModel):
    """Returned by GET /edit/jobs."""

    edit_jobs: List[EditJob]
    total: int


# ---------------------------------------------------------------------------
# YouTube direct-upload (Connect YouTube → publish clips)
# ---------------------------------------------------------------------------

class YouTubeAuthStatus(BaseModel):
    """Returned by GET /youtube/auth/status — is the user's YouTube connected?"""

    connected: bool
    channel_id: Optional[str] = None
    channel_title: Optional[str] = None


class YouTubeUploadRequest(BaseModel):
    """Body for POST /youtube/upload — publish an existing clip to YouTube."""

    parent_job_id: str = Field(..., description="Parent clip-extraction job id.")
    clip_id: str = Field(..., description="Clip id within the parent job to publish.")
    title: str = Field(..., min_length=1, max_length=100, description="Video title.")
    description: str = Field(default="", max_length=5_000)
    tags: List[str] = Field(default_factory=list, description="YouTube tags.")
    privacy_status: PrivacyStatus = Field(
        default="private",
        description=(
            "Visibility on YouTube. Defaults to 'private'. Note: unverified "
            "OAuth apps are forced to 'private' regardless of this value."
        ),
    )
    category_id: str = Field(
        default="22",
        description="YouTube category id (22 = 'People & Blogs').",
    )
    made_for_kids: bool = Field(
        default=False,
        description="Sets status.selfDeclaredMadeForKids on the upload.",
    )


class YouTubeUploadJob(BaseModel):
    """Returned by the /youtube/upload + /youtube/uploads endpoints."""

    upload_id: str
    parent_job_id: Optional[str] = None
    clip_id: Optional[str] = None
    status: JobStatusLiteral
    created_at: datetime
    updated_at: datetime
    title: Optional[str] = None
    privacy_status: Optional[PrivacyStatus] = None
    video_id: Optional[str] = Field(
        default=None, description="YouTube video id (present when status='done')."
    )
    video_url: Optional[str] = Field(
        default=None, description="Watch URL (present when status='done')."
    )
    error: Optional[str] = None


class YouTubeUploadListResponse(BaseModel):
    """Returned by GET /youtube/uploads."""

    uploads: List[YouTubeUploadJob]
    total: int
