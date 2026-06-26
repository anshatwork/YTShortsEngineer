import logging

from core.logging_config import configure_logging


def setup_logger(name: str, log_level: str = "INFO") -> logging.Logger:
    """
    Return a named logger wired into the central logging configuration.

    Historically this attached its own console/file handlers. That is now
    handled once by ``core.logging_config.configure_logging`` (context-aware
    formatting, rotating ``logs/app.log``, per-job files, third-party noise
    control), so this helper just ensures the base config exists and returns
    the named logger. Kept for backwards compatibility with existing callers.

    Args:
        name: The name of the logger (usually __name__).
        log_level: Level for THIS logger (root/app levels are managed centrally).

    Returns:
        Configured logger instance.
    """
    configure_logging()
    logger = logging.getLogger(name)
    level = getattr(logging, log_level.upper(), logging.INFO)
    logger.setLevel(level)
    return logger
