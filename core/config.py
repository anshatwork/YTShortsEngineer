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
    ELEVENLABS_API_KEY: Optional[str] = Field(None, description="ElevenLabs API Key")
    YT_API_KEY: Optional[str] = Field(None, description="YouTube API Key")
    
    # ElevenLabs Configuration
    ELEVENLABS_VOICE_ID: Optional[str] = Field(None, description="ElevenLabs Voice ID")
    PIXABAY_API_KEY: Optional[str] = Field(None, description="Pixabay API Key")
    GEMINI_API_KEY: Optional[str] = Field(None, description="Google Gemini API Key (optional, for multimodal upgrade)")
    # Paths
    BASE_DIR: Path = Path(__file__).parent.parent
    OUTPUT_DIR: Path = Field(default_factory=lambda: Path("output"))
    ASSETS_DIR: Path = Field(default_factory=lambda: Path("assets"))
    CLIPS_OUTPUT_DIR: Path = Field(default_factory=lambda: Path("output/clips"))
    BACKGROUND_VIDEO_PATH: Optional[str] = Field(None, description="Path to background video")
    
    # Long-to-Shorts clipping
    TOP_N_CLIPS: int = Field(default=5, description="Max clips to extract per video")
    
    # Model Configuration
    LLM_MODEL_ID: str = "zai-org/GLM-4.7"
    WHISPER_MODEL: str = "base"
    
    # Rendering
    VIDEO_WIDTH: int = 1080
    VIDEO_HEIGHT: int = 1920    
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
