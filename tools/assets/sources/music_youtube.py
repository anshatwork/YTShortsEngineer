"""
tools/assets/sources/music_youtube.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
YouTube trending-music source — a *browsable* music provider.

Unlike the royalty-free sources (Jamendo/Pixabay/Freesound), this surfaces the
real, currently-trending songs from YouTube's Music chart so a creator can
manually pick one for a clip. Those tracks are **copyrighted commercial music**:
using one as background audio in a Short that is uploaded back to YouTube can
trigger Content ID claims (mute / demonetize / strike). That risk is carried in
every asset's ``attribution`` and surfaced in the UI.

By design this source is **NOT registered** in ``tools/assets/sources/__init__``
— it never participates in automatic per-clip music recommendation, the
mood-bucket refresh, or keyword ``/music/search``. It is instantiated explicitly
by the trending endpoint (and the commit path) in ``music_routes.py``, so
copyrighted tracks only ever enter the library on an explicit, manual pick.

Discovery uses the YouTube Data API ``videos.list?chart=mostPopular`` (1 quota
unit); audio is pulled with yt-dlp (0 Data-API quota).
"""

from __future__ import annotations

import logging
import os
import tempfile
from typing import List, Optional

from tools.assets.base import AssetSource
from tools.assets.models import Asset, AssetQuery, AssetType
from tools.assets.sources._env import configured

logger = logging.getLogger(__name__)

# Shown to creators and stored on every track so the copyright risk follows the
# song into the editor and any later UI.
COPYRIGHT_WARNING = (
    "⚠ Copyrighted — may be claimed, muted, or struck by Content ID if your "
    "Short is uploaded to YouTube."
)


class YouTubeMusicSource(AssetSource):
    """Trending YouTube songs for manual selection (copyrighted; never auto-applied)."""

    asset_type = AssetType.MUSIC
    name = "youtube"

    def available(self) -> bool:
        # Reuses the same key the rest of the YouTube tooling uses.
        return configured("YT_API_KEY") is not None

    def discover(self, query: AssetQuery) -> List[Asset]:
        """Return YouTube songs as Assets (metadata only).

        Two modes, chosen by the query:
        - **keyword search** when ``query.keywords`` are present — costs 100 quota
          units (``search.list``);
        - **trending chart** otherwise — costs 1 unit (``videos.list?chart``).

        ``query.limit`` caps the number of entries; ``YT_TRENDING_REGION`` (default
        ``US``) chooses the region.
        """
        if not self.available():
            return []

        from tools.youtube.search import YouTubeSearchTool

        region = os.getenv("YT_TRENDING_REGION", "US")
        tool = YouTubeSearchTool()
        keywords = " ".join(k.strip() for k in (query.keywords or []) if k.strip()).strip()
        if keywords:
            tracks = tool.search_music(
                keywords,
                max_results=max(query.limit, 10),
                order=query.order,
                region_code=region,
            )
        else:
            tracks = tool.trending_music(
                max_results=max(query.limit, 10),
                region_code=region,
            )

        assets: List[Asset] = []
        for t in tracks:
            video_id = t.get("video_id")
            if not video_id:
                continue
            channel = t.get("channel") or "Unknown"
            assets.append(
                Asset(
                    asset_type=AssetType.MUSIC,
                    source=self.name,
                    source_id=str(video_id),
                    title=t.get("title") or "Untitled",
                    url=t.get("url") or f"https://www.youtube.com/watch?v={video_id}",
                    tags=[],
                    theme=query.theme,
                    duration=float(t.get("duration_seconds") or 0) or None,
                    popularity=float(t.get("view_count") or 0),
                    published_at=t.get("published_at"),
                    attribution=f"{channel} — via YouTube. {COPYRIGHT_WARNING}",
                    metadata={
                        "artist": channel,
                        "video_id": str(video_id),
                        "thumbnail": t.get("thumbnail", ""),
                        "copyright_warning": COPYRIGHT_WARNING,
                    },
                )
            )
        logger.info("youtube discovered %d trending track(s) (region=%s)", len(assets), region)
        return assets

    def fetch(self, asset: Asset) -> Optional[str]:
        """Download the song's audio via yt-dlp and return the mp3 path (or None)."""
        from tools.youtube.downloader import download_audio

        try:
            tmp = tempfile.NamedTemporaryFile(
                delete=False, suffix=".mp3", prefix=f"youtube_{asset.source_id}_"
            )
            tmp.close()
            path = download_audio(asset.url, tmp.name)
            logger.info("[youtube] downloaded audio %s -> %s", asset.cache_key, path)
            return path
        except Exception as exc:  # noqa: BLE001 — a single track failing is non-fatal
            logger.warning("[youtube] audio download failed for %s: %s", asset.cache_key, exc)
            return None


__all__ = ["YouTubeMusicSource", "COPYRIGHT_WARNING"]
