"""
tools/assets/sources/music_jamendo.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Jamendo music source — the primary "free trending music" tier.

Jamendo exposes a large catalogue of Creative-Commons-licensed tracks with a
real popularity signal (``popularity_total``) and a release date, so it serves
both "trending" (``order="popular"``) and "latest" (``order="latest"``) intents.
It needs only a free ``client_id`` (no per-request quota cost for search), which
makes it a good keyless-feeling default versus Pixabay/Freesound.

API: https://developer.jamendo.com/v3.0/tracks
The ``audiodownload`` field is a direct, downloadable MP3, so the base
:meth:`AssetSource.fetch` (plain HTTP GET) works unchanged.
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

_API_URL = "https://api.jamendo.com/v3.0/tracks/"
_DISCOVER_TIMEOUT = 10


class JamendoMusicSource(AssetSource):
    asset_type = AssetType.MUSIC
    name = "jamendo"

    def available(self) -> bool:
        return configured("JAMENDO_CLIENT_ID") is not None

    def _tags_for(self, query: AssetQuery) -> str:
        """Build a Jamendo ``fuzzytags`` string (space-separated keywords).

        Prefer the caller's keywords; else derive from the theme's curated
        queries. Jamendo matches loosely against track tags, so a handful of
        descriptive words works well.
        """
        if query.keywords:
            words = query.keywords
        else:
            theme = AudioTheme.validate(query.theme or "") or AudioTheme.NEUTRAL
            queries = get_search_queries_for_theme(theme)
            # Flatten the first couple of curated phrases into individual tags.
            words = " ".join(queries[:2]).split() if queries else ["background", "music"]
        # De-dupe while preserving order, cap to keep the query tight.
        seen: list[str] = []
        for w in words:
            wl = w.lower()
            if wl not in seen:
                seen.append(wl)
        return " ".join(seen[:5])

    def discover(self, query: AssetQuery) -> List[Asset]:
        client_id = configured("JAMENDO_CLIENT_ID")
        if not client_id:
            return []

        order = "releasedate_desc" if query.order == "latest" else "popularity_total"
        params = {
            "client_id": client_id,
            "format": "json",
            "limit": max(query.limit, 5),
            "order": order,
            "audioformat": "mp32",
            "include": "musicinfo licenses",
            "audiodlformat": "mp32",
        }
        if query.include_vocals:
            # Songs mode: full-text search (matches artist + title) and allow vocals,
            # so named/trending songs surface instead of only instrumental beds.
            params["search"] = " ".join(query.keywords) or self._tags_for(query)
        else:
            # Mood mode: instrumental beds matched by curated theme tags.
            params["fuzzytags"] = self._tags_for(query)
            params["vocalinstrumental"] = "instrumental"
        if query.min_duration is not None:
            params["durationbetween"] = (
                f"{int(query.min_duration)}_{int(query.max_duration or 600)}"
            )

        resp = requests.get(_API_URL, params=params, timeout=_DISCOVER_TIMEOUT)
        resp.raise_for_status()
        body = resp.json() or {}

        # Jamendo signals API-level errors inside the JSON envelope (HTTP 200).
        headers = body.get("headers", {})
        if headers.get("status") != "success":
            raise RuntimeError(
                f"jamendo error: {headers.get('error_message') or headers.get('code')}"
            )

        results = body.get("results", []) or []
        assets: List[Asset] = []
        for r in results:
            url = r.get("audiodownload") or r.get("audio")
            if not url:
                continue
            license_url = r.get("license_ccurl") or "see source"
            artist = r.get("artist_name") or "Unknown artist"
            tags = []
            musicinfo = r.get("musicinfo") or {}
            tags_block = musicinfo.get("tags") or {}
            for key in ("genres", "instruments", "vartags"):
                tags.extend(tags_block.get(key, []) or [])
            assets.append(
                Asset(
                    asset_type=AssetType.MUSIC,
                    source=self.name,
                    source_id=str(r.get("id", url)),
                    title=r.get("name", "") or "Jamendo track",
                    url=url,
                    tags=[str(t) for t in tags][:12],
                    theme=query.theme,
                    duration=float(r.get("duration", 0) or 0) or None,
                    popularity=float(r.get("stats", {}).get("rate_listened_total", 0) or 0)
                    if isinstance(r.get("stats"), dict)
                    else 0.0,
                    published_at=r.get("releasedate"),
                    attribution=f"{artist} — Jamendo (CC: {license_url})",
                    metadata={"artist": artist, "license_ccurl": license_url},
                )
            )
        term = params.get("search") or params.get("fuzzytags") or ""
        logger.info("jamendo discovered %d track(s) for '%s'", len(assets), term)
        return assets


__all__ = ["JamendoMusicSource"]
