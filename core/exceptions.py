class ShortsEngineError(Exception):
    """Base exception for YouTube Shorts Engine"""
    pass

class VideoDownloadError(ShortsEngineError):
    """Raised when video download fails"""
    pass

class AudioGenerationError(ShortsEngineError):
    """Raised when TTS or audio processing fails"""
    pass

class ScriptGenerationError(ShortsEngineError):
    """Raised when LLM script generation fails"""
    pass

class RenderingError(ShortsEngineError):
    """Raised when video rendering fails"""
    pass

class ConfigurationError(ShortsEngineError):
    """Raised when configuration is invalid"""
    pass

class KnowledgeGraphError(ShortsEngineError):
    """Raised when a knowledge-graph operation fails (driver, migration, query)."""
    pass

class EmbeddingError(ShortsEngineError):
    """Raised when an embedding provider cannot produce vectors."""
    pass

class QuotaExceededError(ShortsEngineError):
    """Raised when a third-party API's quota is exhausted and the call cannot
    proceed (e.g. the YouTube Data API daily unit budget). Distinct from a
    transient rate-limit: this is not retryable within the reset window, so
    callers should degrade (e.g. serve from cache) rather than back off."""
    pass
