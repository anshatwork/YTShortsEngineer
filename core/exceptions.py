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
