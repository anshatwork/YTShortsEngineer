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

    # TTS free-provider selection. Default "edge" uses Microsoft Edge neural
    # voices (edge-tts). Set to "streamlabs" to use the legacy Streamlabs Polly
    # path instead. Read via os.getenv() in tools/tts; declared here for docs.
    TTS_FREE_PROVIDER: str = Field(default="edge", description="Free TTS backend: edge | streamlabs")
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
    # Asset-download resilience (tools/assets/backoff.py) — retry transient
    # errors and negative-cache persistently broken assets so the warmer stops
    # re-fetching the same failing track every cycle.
    ASSET_MAX_RETRIES: int = Field(default=2, description="Retries for transient asset download/discover errors (429 / 5xx / connection)")
    ASSET_BACKOFF_BASE_SECONDS: float = Field(default=0.5, description="Base delay for asset backoff (base * 2**attempt + jitter)")
    ASSET_NEGATIVE_CACHE_TTL_HOURS: float = Field(default=6.0, description="How long a failing asset (cache_key) stays blocklisted before it's retried")
    # Paths
    BASE_DIR: Path = Path(__file__).parent.parent
    OUTPUT_DIR: Path = Field(default_factory=lambda: Path("output"))
    ASSETS_DIR: Path = Field(default_factory=lambda: Path("assets"))
    CLIPS_OUTPUT_DIR: Path = Field(default_factory=lambda: Path("output/clips"))
    BACKGROUND_VIDEO_PATH: Optional[str] = Field(None, description="Path to background video")
    
    # Long-to-Shorts clipping
    TOP_N_CLIPS: int = Field(default=5, description="Max clips to extract per video")
    
    # Model Configuration
    LLM_PROVIDER: str = Field(default="claude", description="LLM backend: claude | ollama | openrouter | glm | hf")
    LLM_LOCAL_ONLY: bool = Field(default=False, description="Force all LLM calls onto local Ollama, ignoring LLM_PROVIDER + BYOK (no hosted provider ever)")
    CLAUDE_MODEL: str = Field(default="claude-sonnet-4-6", description="Claude model id")
    # GLM (Z.ai) — free-tier provider. Read via os.getenv() in tools/llm/glm.py;
    # declared here for documentation (extra='ignore' tolerates them in .env).
    GLM_API_KEY: Optional[str] = Field(None, description="Z.ai GLM API key (free tier)")
    GLM_MODEL: str = Field(default="glm-4.5-flash", description="GLM model id (free: glm-4.5-flash | glm-4.7-flash)")
    OPENROUTER_API_KEY: Optional[str] = Field(None, description="OpenRouter API key")
    OPENROUTER_BASE_URL: str = Field(default="https://openrouter.ai/api/v1", description="OpenRouter API base URL")
    OPENROUTER_MODEL: str = Field(default="openrouter/free", description="OpenRouter model id")
    OPENROUTER_MAX_TOKENS: int = Field(default=1024, description="OpenRouter output token cap")
    OPENROUTER_TIMEOUT: float = Field(default=60.0, description="OpenRouter request timeout")
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

    # ── Knowledge Graph (core/kg) + Embeddings (tools/embeddings) ─────────
    # The persistent multimodal knowledge graph and its embedding stack. All of
    # these are ALSO read via os.getenv() at their use sites (core/kg/driver.py,
    # core/kg/schema.py, tools/embeddings) so the layer works even if Settings
    # fails to load, and stays purely additive (KG_ENABLED defaults off).
    KG_ENABLED: bool = Field(default=False, description="Master switch for the knowledge-graph layer")
    NEO4J_URI: Optional[str] = Field(None, description="Bolt URI of Neo4j/Memgraph, e.g. bolt://localhost:7687")
    NEO4J_USER: str = Field(default="neo4j", description="Neo4j username")
    NEO4J_PASSWORD: Optional[str] = Field(None, description="Neo4j password")
    NEO4J_DATABASE: Optional[str] = Field(None, description="Neo4j database name (None = default)")
    KG_VECTOR_SIMILARITY: str = Field(default="cosine", description="Vector index similarity: cosine | euclidean")
    EMBEDDING_PROVIDER: str = Field(default="local", description="Embedding backend: local | hash")
    EMBEDDING_FALLBACK: bool = Field(default=True, description="Degrade to the hash embedder if local deps/model fail")
    EMBEDDING_MODEL_TEXT: str = Field(default="BAAI/bge-small-en-v1.5", description="Local text-embedding model id")
    EMBEDDING_MODEL_IMAGE: str = Field(default="ViT-B-32:laion2b_s34b_b79k", description="OpenCLIP image model 'arch:pretrained'")
    EMBEDDING_DIM_TEXT: int = Field(default=384, description="Text embedding dimensionality (must match the model + vector index)")
    EMBEDDING_DIM_IMAGE: int = Field(default=512, description="Image embedding dimensionality (must match the model + vector index)")

    # ── MCP connector (agents/long_to_shorts/api/mcp_server) ──────────────
    # Remote MCP server mounted at /mcp so the pipeline can be added as a custom
    # connector in Claude.ai / ChatGPT. These are read via os.getenv() in the
    # mcp_* modules (declared here for documentation). MCP_PUBLIC_URL is the
    # public https base of this server (e.g. https://api.example.com) — required
    # for the Supabase OAuth flow. MCP_JWT_ALGORITHM must match the Supabase Auth
    # signing algorithm (ES256/RS256 recommended; HS256 legacy).
    MCP_ENABLED: bool = Field(default=True, description="Mount the MCP connector at /mcp")
    MCP_PUBLIC_URL: Optional[str] = Field(None, description="Public https base url of this server (for MCP OAuth)")
    MCP_JWT_ALGORITHM: str = Field(default="ES256", description="Supabase Auth JWT alg: ES256 | RS256 | HS256")

    # ── Inference scheduler (core/inference, tools/llm/inference) ─────────
    # The single choke point for LLM calls. On a single-GPU Ollama box keep
    # INFERENCE_MAX_CONCURRENCY=1 to serialise inference and avoid VRAM thrash.
    # Model tiers route task classes to the smallest sufficient local model.
    # All read via os.getenv() at their use sites; declared here for docs.
    INFERENCE_SCHEDULER_ENABLED: bool = Field(default=True, description="Route existing pipeline LLM calls through the scheduler (safety valve: 0 = direct get_llm)")
    INFERENCE_MAX_CONCURRENCY: int = Field(default=1, description="Concurrent inference workers; 1 on a single GPU")
    INFERENCE_QUEUE_MAXSIZE: int = Field(default=256, description="Inference queue bound (backpressure)")
    INFERENCE_MAX_RETRIES: int = Field(default=2, description="Retries per LLM call on transient failure")
    INFERENCE_MODEL_SMALL: Optional[str] = Field(None, description="Ollama tag for fast metadata/scoring (e.g. qwen2.5:3b)")
    INFERENCE_MODEL_MEDIUM: Optional[str] = Field(None, description="Ollama tag for evaluation/analysis (e.g. qwen2.5:7b-instruct)")
    INFERENCE_MODEL_LARGE: Optional[str] = Field(None, description="Ollama tag for planning (largest local model)")
    INFERENCE_WARM_ENABLED: bool = Field(default=False, description="Warm-pool + idle model eviction (Ollama only)")
    INFERENCE_IDLE_TIMEOUT_S: int = Field(default=300, description="Unload the resident model after this idle time (frees VRAM)")
    INFERENCE_WARM_KEEPALIVE: str = Field(default="10m", description="Ollama keep_alive for a warmed model")

    # ── Autonomous Publishing Agent (agents/publishing, publishing_*) ─────
    # The human makes two decisions (approve source, approve upload); the rest
    # runs autonomously. Read via os.getenv() at use sites; declared for docs.
    PUBLISH_DISCOVER_TOP_N: int = Field(default=5, description="Ranked source-video candidates presented for approval")
    PUBLISH_SCORE_KEEP: int = Field(default=3, description="Top-scoring clips that advance from scoring into evaluation")
    PUBLISH_MAX_REVISIONS: int = Field(default=2, description="Max generator→eval revision cycles before best-effort")
    EVAL_PASS_THRESHOLD: int = Field(default=70, description="Overall eval score (1-100) required to pass without revision")
    EVAL_MIN_DIMENSION: int = Field(default=3, description="Any single eval dimension below this forces a revision")
    YOUTUBE_DAILY_QUOTA: int = Field(default=10000, description="YouTube Data API daily unit budget for discovery accounting")
    YT_QUOTA_RESERVE: int = Field(default=2000, description="Units kept in reserve for interactive discovery; the background trending crawler skips when remaining drops below this")
    YT_SEARCH_CACHE_TTL_HOURS: float = Field(default=6.0, description="TTL for the in-process YouTube search result cache; a repeat query within the window costs 0 quota units")
    YT_MAX_RETRIES: int = Field(default=3, description="Retry attempts for transient YouTube API errors (rate-limit / 5xx). Daily-quota errors are never retried.")
    YT_BACKOFF_BASE_SECONDS: float = Field(default=1.0, description="Base delay for exponential backoff (base * 2**attempt + jitter) on retryable YouTube API errors")
    CREDITS_COST_PUBLISH: int = Field(default=10, description="Credits debited to start an autonomous publishing run")

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
