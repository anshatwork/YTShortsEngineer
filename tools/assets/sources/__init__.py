"""
tools/assets/sources
~~~~~~~~~~~~~~~~~~~~~~
Built-in :class:`AssetSource` providers and their registration.

:func:`ensure_sources_registered` is idempotent and called lazily by the
registry, so importing the asset layer has no import-time side effects beyond
defining classes. Adding a new source = create the module here and append it to
the ``_BUILTIN_SOURCES`` list (order = tier priority).
"""

from __future__ import annotations

from tools.assets.registry import register_source
from tools.assets.sources.music_freesound import FreesoundMusicSource
from tools.assets.sources.music_jamendo import JamendoMusicSource
from tools.assets.sources.music_pixabay import PixabayMusicSource

# Order matters — tried in this order during discovery (= tier priority).
# Jamendo is the primary free trending-music tier; Pixabay/Freesound remain as
# fallbacks when their keys are configured.
_BUILTIN_SOURCES = [
    JamendoMusicSource(),
    PixabayMusicSource(),
    FreesoundMusicSource(),
]

_registered = False


def ensure_sources_registered() -> None:
    """Register built-in sources exactly once."""
    global _registered
    if _registered:
        return
    for source in _BUILTIN_SOURCES:
        register_source(source)
    _registered = True


__all__ = ["ensure_sources_registered"]
