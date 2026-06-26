"""
tools/assets/sources/music_pixabay.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Pixabay music source. Logic adapted from the original
``AudioFetcher._fetch_from_pixabay``, generalized to return ranked
:class:`Asset` candidates instead of a single random download.

Pixabay's audio search supports ``order=latest|popular``, which is how we honor
the caller's "latest" intent at the source.
"""

from __future__ import annotations

import logging
from typing import List

import requests

from tools.assets.base import AssetSource
from tools.assets.models import Asset, AssetQuery, AssetType
from tools.assets.sources._env import configured
from core.audio_themes import AudioTheme
from core.audio_theme_map import get_search_queries_for_theme

logger = logging.getLogger(__name__)

_API_URL = "https://pixabay.com/api/"
_DISCOVER_TIMEOUT = 10


class PixabayMusicSource(AssetSource):
    asset_type = AssetType.MUSIC
    name = "pixabay"

    def available(self) -> bool:
        return configured("PIXABAY_API_KEY") is not None

    def _query_for(self, query: AssetQuery) -> str:
        # Prefer the caller's keywords; fall back to the theme's curated queries.
        if query.keywords:
            return " ".join(query.keywords[:3])
        theme = AudioTheme.validate(query.theme or "") or AudioTheme.NEUTRAL
        queries = get_search_queries_for_theme(theme)
        return queries[0] if queries else "background music"

    def discover(self, query: AssetQuery) -> List[Asset]:
        key = configured("PIXABAY_API_KEY")
        if not key:
            return []

        order = "latest" if query.order == "latest" else "popular"
        params = {
            "key": key,
            "q": self._query_for(query),
            "type": "music",
            "per_page": max(query.limit, 5),
            "order": order,
        }
        resp = requests.get(_API_URL, params=params, timeout=_DISCOVER_TIMEOUT)
        resp.raise_for_status()
        hits = resp.json().get("hits", []) or []

        assets: List[Asset] = []
        for hit in hits:
            url = hit.get("previewURL") or hit.get("audio")
            if not url:
                continue
            assets.append(
                Asset(
                    asset_type=AssetType.MUSIC,
                    source=self.name,
                    source_id=str(hit.get("id", url)),
                    title=hit.get("tags", "") or "Pixabay track",
                    url=url,
                    tags=[t.strip() for t in str(hit.get("tags", "")).split(",") if t.strip()],
                    theme=query.theme,
                    duration=float(hit.get("duration", 0) or 0) or None,
                    popularity=float(hit.get("downloads", 0) or 0),
                    attribution="Music from Pixabay",
                    metadata={"user": hit.get("user")},
                )
            )
        logger.info("pixabay discovered %d track(s) for '%s'", len(assets), params["q"])
        return assets


__all__ = ["PixabayMusicSource"]
