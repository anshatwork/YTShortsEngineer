import os
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field

class Settings(BaseSettings):
    """
    Application configuration using Pydantic Settings.
    Reads from environment variables and .env file.
    """
    # API Keys
    HUGGINGFACE_API_KEY: str = Field(..., description="HuggingFace API Key")
    ANTHROPIC_API_KEY: Optional[str] = Field(None, description="Anthropic / Claude API Key")
    ELEVENLABS_API_KEY: Optional[str] = Field(None, description="ElevenLabs API Key")
    YT_API_KEY: Optional[str] = Field(None, description="YouTube API Key")
    
    # ElevenLabs Configuration
    ELEVENLABS_VOICE_ID: Optional[str] = Field(None, description="ElevenLabs Voice ID")
    PIXABAY_API_KEY: Optional[str] = Field(None, description="Pixabay API Key")
    FREESOUND_API_KEY: Optional[str] = Field(None, description="Freesound API Key (fallback music tier)")
    JAMENDO_CLIENT_ID: Optional[str] = Field(None, description="Jamendo client_id — primary free trending-music tier")
    GEMINI_API_KEY: Optional[str] = Field(None, description="Google Gemini API Key (optional, for multimodal upgrade)")

    # ── Music cache (tools/assets) ────────────────────────────────────────
    # The audio cache self-refreshes on a timer so themed buckets stay warm and
    # the /add-music edit never has to wait on a cold network fetch. These are
    # also read via os.getenv() in tools/assets so they work without Settings.
    MUSIC_CACHE_REFRESH_HOURS: int = Field(default=24, description="Interval for the background trending-music refresh")
    MUSIC_CACHE_TRACKS_PER_THEME: int = Field(default=8, description="Tracks to keep warm per audio theme")
    # Paths
    BASE_DIR: Path = Path(__file__).parent.parent
    OUTPUT_DIR: Path = Field(default_factory=lambda: Path("output"))
    ASSETS_DIR: Path = Field(default_factory=lambda: Path("assets"))
    CLIPS_OUTPUT_DIR: Path = Field(default_factory=lambda: Path("output/clips"))
    BACKGROUND_VIDEO_PATH: Optional[str] = Field(None, description="Path to background video")
    
    # Long-to-Shorts clipping
    TOP_N_CLIPS: int = Field(default=5, description="Max clips to extract per video")
    
    # Model Configuration
    LLM_PROVIDER: str = Field(default="claude", description="LLM backend: claude | ollama | hf")
    CLAUDE_MODEL: str = Field(default="claude-sonnet-4-6", description="Claude model id")
    ENABLE_LLM_FALLBACK: bool = Field(default=True, description="Fall back to Ollama when the primary LLM fails")
    LLM_MODEL_ID: str = "zai-org/GLM-4.7"
    WHISPER_MODEL: str = "base"
    
    # Rendering
    VIDEO_WIDTH: int = 1080
    VIDEO_HEIGHT: int = 1920

    # ── Execution layer (core/execution, core/cache) ──────────────────────
    # These are also read directly via os.getenv() in the relevant modules so
    # they work even if Settings fails to load; declared here for documentation.
    CACHE_ENABLED: bool = Field(default=True, description="Master switch for the artifact cache")
    CACHE_DIR: Path = Field(default_factory=lambda: Path("cache"), description="Root for CAS blobs + sqlite index")
    CACHE_INDEX_BACKEND: Optional[str] = Field(None, description="'supabase' | 'sqlite' (auto by JOB_STORE)")
    BLOB_STORE_BACKEND: str = Field(default="local", description="'local' now; 's3' is the production swap")
    EVENT_BUS_BACKEND: str = Field(default="memory", description="'memory' now; 'redis' for distributed fan-out")
    TASK_QUEUE_BACKEND: str = Field(default="threadpool", description="'threadpool' now; celery/temporal later")
    WORKER_THREADS: int = Field(default=2, description="Background pipeline workers")
    PIPELINE_RESUME_ENABLED: bool = Field(default=True, description="Skip already-complete stages on re-run")

    # ── Clip extraction (agents/long_to_shorts/clipping_logic_node) ───────
    # Each clip's encode is split into time-based parts that are encoded in
    # parallel and concatenated losslessly. These are also read via os.getenv()
    # in clipping_logic_node so they work even if Settings fails to load.
    CLIP_WORKER_THREADS: int = Field(default=0, description="Parallel ffmpeg part encoders; 0 -> os.cpu_count()")
    FFMPEG_THREADS_PER_PART: int = Field(default=2, description="libx264 threads per part encode")
    CLIP_PART_TARGET_SECONDS: float = Field(default=20.0, description="Target length of each parallel part")
    CLIP_PART_MIN_SECONDS: float = Field(default=45.0, description="Clips shorter than this are never split")
    CLIP_MAX_PARTS: int = Field(default=8, description="Cap on parts per clip (fan-out limit)")
    CLIP_X264_PRESET: str = Field(default="medium", description="x264 preset; 'veryfast'/'faster' trade size for speed")
    CLIP_FORCE_FPS: int = Field(default=60, description="Output fps; 0 -> preserve source fps")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"  # Ignore extra fields in .env that aren't defined here

# Global settings instance
try:
    settings = Settings()
    # Ensure directories exist
    settings.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    settings.CLIPS_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    # settings.ASSETS_DIR.mkdir(parents=True, exist_ok=True) # Assets might be created later
except Exception as e:
    # Just print warning if .env is missing during init, valid for CI/CD or first run
    print(f"Warning: Failed to load settings: {e}")
    # Create a dummy settings object or handle gracefully if critical keys are missing
    # For now, we'll let it fail later if keys are accessed
    pass
