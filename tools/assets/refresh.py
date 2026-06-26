"""
tools/assets/refresh.py
~~~~~~~~~~~~~~~~~~~~~~~~~
Background warming of the music cache.

:func:`refresh_music_cache` walks every :class:`~core.audio_themes.AudioTheme`
and asks :func:`tools.assets.retrieve` for a small pool per theme. ``retrieve``
is cache-first, so this only hits the network for stale/empty buckets; the net
effect is that themed buckets stay warm and ``/edit/add-music`` never waits on a
cold fetch. It is a plain blocking function so it can be handed to the existing
``ThreadPoolTaskQueue`` (see ``agents/long_to_shorts/api/app.py`` lifespan).
"""

from __future__ import annotations

import logging
import os

from core.audio_themes import AudioTheme
from tools.assets import AssetQuery, AssetType, retrieve
from tools.assets.registry import get_sources

logger = logging.getLogger(__name__)


def _tracks_per_theme(explicit: int | None = None) -> int:
    if explicit is not None:
        return explicit
    try:
        return int(os.getenv("MUSIC_CACHE_TRACKS_PER_THEME", "8"))
    except ValueError:
        return 8


def music_sources_available() -> bool:
    """True when at least one music source is usable (has a real credential)."""
    return len(get_sources(AssetType.MUSIC, available_only=True)) > 0


def refresh_music_cache(tracks_per_theme: int | None = None) -> dict[str, int]:
    """Warm every theme bucket; return ``{theme: track_count}``.

    No-ops (and logs once) when no music source is configured, so a deployment
    without any keys doesn't spew per-theme network failures on every tick.
    """
    if not music_sources_available():
        logger.info(
            "music cache refresh skipped — no music source configured "
            "(set JAMENDO_CLIENT_ID / PIXABAY_API_KEY / FREESOUND_API_KEY)"
        )
        return {}

    per_theme = _tracks_per_theme(tracks_per_theme)
    summary: dict[str, int] = {}
    for theme in AudioTheme:
        try:
            results = retrieve(
                AssetQuery(
                    asset_type=AssetType.MUSIC,
                    theme=theme.value,
                    order="popular",
                    limit=per_theme,
                ),
                k=per_theme,
            )
            summary[theme.value] = len(results)
        except Exception as exc:  # noqa: BLE001 — one theme failing is non-fatal
            logger.warning("music cache refresh failed for theme '%s': %s", theme.value, exc)
            summary[theme.value] = 0

    total = sum(summary.values())
    logger.info(
        "music cache refresh complete — %d track(s) across %d theme(s): %s",
        total, len(summary), summary,
    )
    return summary


__all__ = ["refresh_music_cache", "music_sources_available"]
