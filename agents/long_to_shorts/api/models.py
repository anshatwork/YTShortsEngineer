"""
agents/long_to_shorts/api/models.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Pydantic request and response schemas for the LongToShorts FastAPI server.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import List, Literal, Optional, Tuple
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Shared type aliases
# ---------------------------------------------------------------------------

JobStatusLiteral = Literal["queued", "running", "done", "failed"]
EditOperation = Literal["tts", "music", "split_screen", "thumbnail"]
VoicePreset = Literal["default", "finance", "finance_energetic"]
PrivacyStatus = Literal["private", "unlisted", "public"]
# Thumbnail caption styling. "auto" lets the LLM pick the style/colors; the others
# are explicit user choices (see tools/thumbnail.py).
ThumbnailStyle = Literal["auto", "bubble", "highlight", "box", "plain"]
ThumbnailFont = Literal["auto", "impact", "arial", "condensed"]


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
    video_filename: Optional[str] = Field(
        default=None,
        description=(
            "Original local filename (used to label the job; only for local video "
            "mode). The stored video_path has a generated UUID name, so this "
            "carries the user's real filename for display."
        ),
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
    subtitle_position: Literal["top", "middle", "bottom"] = Field(
        default="bottom",
        description="Vertical placement of burned subtitles (only used when add_subtitles).",
    )
    subtitle_size: Literal["small", "medium", "large"] = Field(
        default="medium",
        description="Font size preset for burned subtitles (only used when add_subtitles).",
    )
    add_top_text: bool = Field(default=False, description="Overlay hook text at top of each clip.")
    add_thumbnail: bool = Field(
        default=False,
        description=(
            "Generate an AI-directed thumbnail image for each clip (ThumbnailNode). "
            "The LLM writes the headline and picks the styling; ffmpeg grabs the best "
            "clip frame (Pixabay image-search fallback)."
        ),
    )
    thumbnail_style: ThumbnailStyle = Field(
        default="auto",
        description=(
            "Caption style for generated thumbnails (applies to all clips in the job). "
            "'auto' lets the LLM choose; bubble/highlight/box/plain force a look."
        ),
    )
    add_intro: bool = Field(default=True, description="Prepend title-card intro (IntroAttachNode).")
    add_music: bool = Field(
        default=False,
        description=(
            "Mix the latest mood-matched background music under each clip "
            "(MusicAttachNode). The track is auto-discovered from the clip's mood."
        ),
    )
    music_volume_db: float = Field(
        default=-18.0,
        description="Background-music gain in dB relative to the clip audio (negative = quieter).",
    )
    clip_mode: Literal["portrait", "fullscreen"] = Field(
        default="portrait",
        description=(
            "'portrait' = 9:16 (1080×1920) reframing. "
            "'fullscreen' = native resolution, no reframing."
        ),
    )
    user_context: Optional[str] = Field(
        default=None,
        max_length=500,
        description=(
            "Optional creator guidance describing the video. When provided, it "
            "steers LLM segment selection, titles, summaries, hooks, and "
            "thumbnail headlines toward what the creator wants."
        ),
        examples=["deep dive on AI agents — focus on the technical payoff"],
    )

    class Config:
        json_schema_extra = {
            "example": {
                "youtube_url": "https://www.youtube.com/watch?v=wJ4i_wRctq8",
                "top_n": 3,
                "add_subtitles": False,
                "add_top_text": True,
                "add_intro": True,
                "add_music": False,
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
    # AI-directed thumbnail (populated by ThumbnailNode). Absolute path; the
    # frontend converts it to a /static URL the same way it does for `path`.
    thumbnail_path: Optional[str] = None
    # Background-music recommendation (populated by ContentGenNode)
    music_theme: Optional[str] = None
    music_title: Optional[str] = None
    music_source: Optional[str] = None
    music_attribution: Optional[str] = None


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
    video_title: Optional[str] = Field(
        default=None,
        description=(
            "Human-readable name for the job — the source video's title once known, "
            "otherwise a derived label (YouTube video id or local filename stem)."
        ),
    )


# Match an 11-char YouTube video id in the common URL shapes, without importing
# the heavier youtube tooling (keeps the in-memory store path light).
_YT_ID_RE = re.compile(
    r"(?:v=|/shorts/|/embed/|youtu\.be/)([0-9A-Za-z_-]{11})"
)


def derive_job_title(request: "JobRequest") -> Optional[str]:
    """An instant, human-readable label for a freshly created job.

    Used as the displayed name until the real video title is fetched during the
    run. Returns the YouTube video id for URL jobs, the filename stem for local
    video jobs, or None when neither is available.
    """
    if request.youtube_url:
        m = _YT_ID_RE.search(request.youtube_url)
        return m.group(1) if m else request.youtube_url
    if request.video_path:
        # Prefer the user's original filename; video_path has a generated UUID name.
        name = request.video_filename or request.video_path
        return Path(name).stem
    return None


class JobListResponse(BaseModel):
    """Returned by GET /jobs."""

    jobs: List[JobStatus]
    total: int


# ---------------------------------------------------------------------------
# Discover — trending long-form video sourcing (powers the /discover UI)
# ---------------------------------------------------------------------------

DiscoverOrder = Literal["relevance", "viewCount", "date"]


class DiscoverRequest(BaseModel):
    """Body for POST /discover."""

    topics: List[str] = Field(
        default_factory=list,
        description="Curated topic keys to sample from (see GET /discover/topics).",
        examples=[["ai", "tech"]],
    )
    custom_queries: List[str] = Field(
        default_factory=list,
        description="Free-text search queries, appended to the curated topic queries.",
        examples=[["langgraph tutorial"]],
    )
    conversational_query: Optional[str] = Field(
        default=None,
        description=(
            "Natural-language search request (e.g. 'recent AI agent deep dives "
            "under an hour'). When set, the server uses an LLM to interpret it into "
            "topics, queries, sort order, recency and a duration window — then "
            "searches in one shot and echoes back what it understood."
        ),
        examples=["recent AI agent deep dives under an hour"],
    )
    days_ago: int = Field(
        default=7, ge=1, le=365,
        description="Only include videos published within this many days.",
    )
    max_results_per_query: int = Field(
        default=5, ge=1, le=10,
        description="Max videos returned per search query.",
    )
    order: DiscoverOrder = Field(
        default="relevance",
        description="YouTube sort order. 'viewCount' surfaces trending.",
    )
    min_duration_minutes: Optional[int] = Field(
        default=None, ge=0, le=600,
        description="Only include videos at least this long (minutes). Floored at 20.",
    )
    max_duration_minutes: Optional[int] = Field(
        default=None, ge=0, le=600,
        description="Only include videos at most this long (minutes). None = no cap.",
    )


class DiscoverInterpretation(BaseModel):
    """Structured search params an LLM infers from a conversational query.

    Doubles as the ``output_format`` schema passed to ``get_llm().parse(...)`` and
    as the object echoed back in :class:`DiscoverResponse` so the UI can sync its
    controls to what the model understood.
    """

    topics: List[str] = Field(
        default_factory=list,
        description="Curated topic keys that fit the request (subset of the bank).",
    )
    custom_queries: List[str] = Field(
        default_factory=list,
        description="Concrete free-text YouTube search queries for the request.",
    )
    order: DiscoverOrder = Field(
        default="relevance",
        description="Sort order. 'viewCount' for trending/popular, 'date' for newest.",
    )
    days_ago: Optional[int] = Field(
        default=None, ge=1, le=3650,
        description=(
            "Recency window in days inferred from phrasing. null = no time "
            "constraint (evergreen/historical topics like past events or tutorials)."
        ),
    )
    min_duration_minutes: Optional[int] = Field(
        default=None,
        description="Lower duration bound in minutes, if the request implies one.",
    )
    max_duration_minutes: Optional[int] = Field(
        default=None,
        description="Upper duration bound in minutes, if the request implies one.",
    )
    summary: str = Field(
        default="",
        description="One-line 'Understood: …' recap of the interpreted request.",
    )


class DiscoverVideo(BaseModel):
    """A single candidate video — mirrors the dict from tools/youtube/search.py."""

    video_id: str
    title: str
    description: str = ""
    thumbnail: str = ""
    url: str
    channel: str = ""
    published_at: str = ""
    duration_seconds: int = 0
    duration_label: str = ""
    view_count: int = 0
    like_count: int = 0
    comment_count: int = 0


class DiscoverResponse(BaseModel):
    """Returned by POST /discover."""

    videos: List[DiscoverVideo]
    queries_used: List[str]
    total: int
    interpretation: Optional[DiscoverInterpretation] = Field(
        default=None,
        description=(
            "What the LLM inferred from a conversational_query (None for plain "
            "topic/keyword searches). Lets the UI show 'Understood: …' and sync "
            "its filter controls."
        ),
    )


class DiscoverTopicsResponse(BaseModel):
    """Returned by GET /discover/topics."""

    topics: List[str]


class UserInterestProfile(BaseModel):
    """Interests an LLM infers from a user's clip-job history.

    Doubles as the ``output_format`` schema passed to ``get_llm().parse(...)``
    when personalizing trending suggestions (see discover_routes).
    """

    keywords: List[str] = Field(
        default_factory=list,
        description="Concrete topic/keyword phrases the user tends to clip about.",
    )
    topics: List[str] = Field(
        default_factory=list,
        description="Broad themes (e.g. 'ai', 'tech', 'productivity').",
    )
    summary: str = Field(
        default="",
        description="One-line plain-language recap of what this creator focuses on.",
    )


class DiscoverSuggestion(BaseModel):
    """A single personalized trending pick: a pooled video + why it was chosen."""

    video: DiscoverVideo
    reason: str = Field(default="", description="Why this was suggested to the user.")
    discovered_at: datetime = Field(
        ..., description="When the crawler first added this video to the pool."
    )


class DiscoverSuggestionsResponse(BaseModel):
    """Returned by GET /discover/suggestions."""

    suggestions: List[DiscoverSuggestion]
    new_count: int = Field(
        default=0,
        description="How many suggestions are newer than the user's last_seen_at.",
    )
    generated_at: datetime
    last_seen_at: Optional[datetime] = Field(
        default=None, description="When the user last opened their suggestions."
    )
    interest_summary: Optional[str] = Field(
        default=None, description="Plain-language recap of the inferred interests."
    )


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
    video_upload_id: Optional[str] = Field(
        default=None,
        description=(
            "Lay the TTS narration over this uploaded video (id from POST /edit/uploads). "
            "The video's own audio is dropped and the video is looped/trimmed to the "
            "narration length. Mutually exclusive with attach_to_clip_id and video_url."
        ),
    )
    video_url: Optional[str] = Field(
        default=None,
        description=(
            "Lay the TTS narration over this YouTube video (downloaded via yt-dlp). "
            "The video's own audio is dropped and the video is looped/trimmed to the "
            "narration length. Mutually exclusive with attach_to_clip_id and video_upload_id."
        ),
    )


class TtsScriptRequest(BaseModel):
    """Body for POST /edit/tts/script — expand a summary into a narration script."""

    summary: str = Field(..., min_length=1, max_length=2_000)
    target_seconds: int = Field(
        default=30, ge=5, le=180,
        description="Approximate spoken length to size the script to.",
    )
    tone: Optional[str] = Field(
        default=None,
        description="Optional tone hint, e.g. 'energetic', 'calm', 'authoritative'.",
    )


class TtsScriptResponse(BaseModel):
    """Returned by POST /edit/tts/script."""

    script: str


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
    music_start_sec: float = Field(
        default=0.0,
        ge=0.0,
        description="Seconds into the song to start the clip-length window (e.g. the chorus). 0 = from the start.",
    )


class MusicTrack(BaseModel):
    """A single cached music track, as exposed by GET /music/tracks.

    ``path`` is the server-side file path — pass it straight back as
    ``MusicEditRequest.music_path`` to use the track. ``preview_url`` is the
    browser-streamable URL (served from the /library mount today; a blob-store
    URL once BLOB_STORE_BACKEND points at S3/MinIO).
    """

    track_id: str = Field(..., description="Stable id (Asset cache_key: 'source:source_id').")
    title: str = Field(..., description="Display title.")
    theme: str = Field(..., description="Audio theme bucket this track lives in.")
    source: str = Field(..., description="Provider name: jamendo | pixabay | freesound | youtube | user | local.")
    duration: Optional[float] = Field(default=None, description="Length in seconds, when known.")
    attribution: Optional[str] = Field(default=None, description="License/credit string to display (carries the copyright warning for youtube tracks).")
    preview_url: str = Field(..., description="Browser-streamable URL for inline preview.")
    path: str = Field(..., description="Server file path; use as MusicEditRequest.music_path.")
    deletable: bool = Field(default=False, description="True for user-added tracks the UI may delete.")


class MusicTrackListResponse(BaseModel):
    """Returned by GET /music/tracks."""

    tracks: List[MusicTrack]
    total: int = Field(..., description="Number of tracks returned.")


class MusicThemeCount(BaseModel):
    theme: str
    count: int


class MusicThemesResponse(BaseModel):
    """Returned by GET /music/themes."""

    themes: List[MusicThemeCount]


class MusicRefreshResponse(BaseModel):
    """Returned by POST /music/refresh."""

    queued: bool = Field(..., description="Whether a refresh was enqueued.")
    detail: str


class MusicSearchResult(BaseModel):
    """A single free-catalog song candidate from GET /music/search (not yet cached).

    ``preview_url`` is the provider's remote URL — playable inline and used as
    ``download_url`` when the user adds the track via POST /music/songs.
    """

    source: str = Field(..., description="Provider name: jamendo | pixabay | freesound | youtube.")
    source_id: str = Field(..., description="Provider-local id (for youtube this is the video id).")
    title: str
    artist: Optional[str] = Field(default=None, description="Artist/creator (channel for youtube), when known.")
    duration: Optional[float] = Field(default=None, description="Length in seconds, when known.")
    attribution: Optional[str] = Field(default=None, description="License/credit string.")
    preview_url: str = Field(..., description="Remote URL to preview the track inline (watch URL for youtube).")
    download_url: str = Field(..., description="Remote URL to fetch when adding the track.")
    already_cached: bool = Field(default=False, description="True if already in the songs library.")
    thumbnail: Optional[str] = Field(default=None, description="Thumbnail image URL, when known (youtube).")
    copyright_warning: Optional[str] = Field(
        default=None,
        description=(
            "Set for copyrighted sources (youtube): a creator-facing warning that the "
            "track may be claimed/muted/struck by Content ID if the Short is uploaded. "
            "Royalty-free sources leave this null."
        ),
    )


class MusicInterpretation(BaseModel):
    """Structured catalog-search params an LLM infers from a conversational
    "vibe" request on the music surface.

    Doubles as the ``output_format`` schema passed to ``get_llm().parse(...)``
    and as the object echoed back in :class:`MusicSearchResponse` so the UI can
    show what the model understood.
    """

    query: str = Field(
        default="",
        description=(
            "A concise free-catalog search phrase (title/genre/instrument words), "
            "e.g. 'upbeat lo-fi instrumental'."
        ),
    )
    order: str = Field(
        default="popular",
        description="'popular' (trending), 'latest' (newest), or 'relevance'.",
    )
    summary: str = Field(
        default="",
        description="One-line 'Understood: …' recap of the interpreted vibe.",
    )


class MusicSearchResponse(BaseModel):
    """Returned by GET /music/search."""

    results: List[MusicSearchResult]
    total: int
    interpretation: Optional[MusicInterpretation] = Field(
        default=None,
        description="Set only for conversational searches — what the LLM understood.",
    )
    query_used: Optional[str] = Field(
        default=None,
        description="The effective keyword phrase the catalogs were searched with.",
    )


class AddSongRequest(BaseModel):
    """Body for POST /music/songs — commit a searched track into the songs library."""

    source: str = Field(..., description="Provider name from the search result.")
    source_id: str = Field(..., description="Provider-local id from the search result.")
    title: str = Field(..., description="Display title.")
    download_url: str = Field(..., description="Remote URL to download (must be an allowlisted host).")
    duration: Optional[float] = Field(default=None)
    attribution: Optional[str] = Field(default=None)


class ThumbnailEditRequest(BaseModel):
    """Body for POST /edit/generate-thumbnail."""

    parent_job_id: str = Field(..., description="Parent clip-extraction job id.")
    clip_id: str = Field(..., description="Clip id within the parent job.")
    headline: Optional[str] = Field(
        default=None,
        description="Override the LLM-written headline text (≤30 chars). Omit to let the LLM decide.",
    )
    accent_color: Optional[str] = Field(
        default=None,
        description="Override the accent/fill color as a hex string (e.g. '#FF2D55'). Omit for LLM default.",
    )
    text_color: Optional[str] = Field(
        default=None,
        description="Override the headline text color as a hex string. Omit for auto-contrast.",
    )
    style: ThumbnailStyle = Field(
        default="auto",
        description="Caption style: 'auto' (LLM picks) or bubble/highlight/box/plain.",
    )
    font: ThumbnailFont = Field(
        default="auto",
        description="Headline font: 'auto' (Impact) or impact/arial/condensed.",
    )


SplitScreenAudioMode = Literal["fetched_video", "bg_video"]


class SplitScreenEditRequest(BaseModel):
    """Body for POST /edit/split-screen.

    Foreground (top half) comes from EITHER an existing clip (parent_job_id + clip_id)
    OR a standalone uploaded video (foreground_upload_id).
    """

    parent_job_id: Optional[str] = Field(
        default=None, description="Parent clip-extraction job id (clip-foreground mode)."
    )
    clip_id: Optional[str] = Field(
        default=None, description="Clip id within the parent job (renders on top)."
    )
    foreground_upload_id: Optional[str] = Field(
        default=None,
        description="Standalone mode: id from POST /edit/uploads to use as the top-half video.",
    )

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
