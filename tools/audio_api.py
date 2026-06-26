"""
Audio API Integration  (backward-compatible shim)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Historically this module owned the 4-tier audio fallback (local cache →
Pixabay → Freesound → silent). That logic now lives in the generalized asset
layer (:mod:`tools.assets`), where music is just one ``AssetType`` among many
and discovery is cache-first, freshness-aware, and ranked.

``AudioFetcher`` is kept as a thin shim so existing callers — the
``/edit/add-music`` endpoint (``edit_runner._fetch_music_for_theme``), the
legacy ShortsState node, and tests — keep working unchanged. New code should
call :func:`tools.assets.retrieve` directly.
"""

import logging
from typing import Optional

from core.audio_themes import AudioTheme
from tools.assets import AssetQuery, AssetType, retrieve
from tools.assets.store import AssetStore

logger = logging.getLogger(__name__)


class AudioFetcher:
    """Backward-compatible facade over the generalized asset layer.

    Delegates theme-based music fetching to :func:`tools.assets.retrieve`
    (cache-first + live Pixabay/Freesound fallback, ranked by "latest").
    """

    def __init__(self):
        self._store = AssetStore()

    def fetch_audio_for_theme(self, theme: AudioTheme) -> Optional[str]:
        """Return a local path to a background-music file for *theme*, or None.

        Preserves the original contract: a usable file path on success, or
        ``None`` when every tier fails (caller decides how to degrade).
        """
        logger.info("Fetching audio for theme: %s", theme.value)
        results = retrieve(
            AssetQuery(asset_type=AssetType.MUSIC, theme=theme.value, order="latest"),
            k=1,
        )
        if results and results[0].local_path:
            logger.info("✓ resolved track for '%s': %s", theme.value, results[0].local_path)
            return results[0].local_path
        logger.warning(
            "✗ no track available for theme '%s' → proceeding without background audio",
            theme.value,
        )
        return None

    def cleanup_cache(self):
        """Evict oldest cached music if the cache exceeds its size cap."""
        self._store.cleanup(AssetType.MUSIC)
