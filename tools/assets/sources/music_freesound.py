"""
tools/assets/sources/music_freesound.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Freesound music source. Logic adapted from the original
``AudioFetcher._fetch_from_freesound``, generalized to return ranked
:class:`Asset` candidates.

Freesound's text search supports a ``sort`` param; ``created_desc`` gives the
newest uploads, which is how "latest" is honored at this source.
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

_SEARCH_URL = "https://freesound.org/apiv2/search/text/"
_DISCOVER_TIMEOUT = 10


class FreesoundMusicSource(AssetSource):
    asset_type = AssetType.MUSIC
    name = "freesound"

    def available(self) -> bool:
        return configured("FREESOUND_API_KEY") is not None

    def _query_for(self, query: AssetQuery) -> str:
        if query.keywords:
            return " ".join(query.keywords[:3])
        theme = AudioTheme.validate(query.theme or "") or AudioTheme.NEUTRAL
        queries = get_search_queries_for_theme(theme)
        return queries[0] if queries else "background music"

    def discover(self, query: AssetQuery) -> List[Asset]:
        token = configured("FREESOUND_API_KEY")
        if not token:
            return []

        lo = query.min_duration if query.min_duration is not None else 10.0
        hi = query.max_duration if query.max_duration is not None else 60.0
        sort = "created_desc" if query.order == "latest" else "downloads_desc"
        params = {
            "query": self._query_for(query),
            "token": token,
            "fields": "id,name,previews,duration,num_downloads,created,license",
            "page_size": max(query.limit, 5),
            "sort": sort,
            "filter": f"duration:[{lo} TO {hi}]",
        }
        resp = requests.get(_SEARCH_URL, params=params, timeout=_DISCOVER_TIMEOUT)
        resp.raise_for_status()
        results = resp.json().get("results", []) or []

        assets: List[Asset] = []
        for r in results:
            url = (r.get("previews") or {}).get("preview-hq-mp3")
            if not url:
                continue
            assets.append(
                Asset(
                    asset_type=AssetType.MUSIC,
                    source=self.name,
                    source_id=str(r.get("id", url)),
                    title=r.get("name", "") or "Freesound track",
                    url=url,
                    theme=query.theme,
                    duration=float(r.get("duration", 0) or 0) or None,
                    popularity=float(r.get("num_downloads", 0) or 0),
                    published_at=r.get("created"),
                    attribution=f"Freesound ({r.get('license', 'see source')})",
                )
            )
        logger.info("freesound discovered %d track(s) for '%s'", len(assets), params["query"])
        return assets


__all__ = ["FreesoundMusicSource"]
