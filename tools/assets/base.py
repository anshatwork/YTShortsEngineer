"""
tools/assets/base.py
~~~~~~~~~~~~~~~~~~~~~
The :class:`AssetSource` provider interface.

A *source* knows how to (a) discover candidate assets for a query (metadata
only, cheap) and (b) download a chosen asset's bytes to a local file. The
retrieval layer treats every source uniformly, so adding a new external
integration — a music site, a b-roll API, a news feed — means subclassing this
once and registering it. This is the seam that makes the layer extensible and
"agentic": each source is an independent capability the system can compose.
"""

from __future__ import annotations

import hashlib
import logging
import tempfile
from abc import ABC, abstractmethod
from typing import List, Optional

from tools.assets.backoff import get_with_backoff, is_bad, mark_bad
from tools.assets.models import Asset, AssetQuery, AssetType

logger = logging.getLogger(__name__)

# Shared download timeout (seconds). Discovery calls use shorter timeouts set by
# each source; the file download can take longer.
_DOWNLOAD_TIMEOUT = 30


class AssetSource(ABC):
    """Base class for a single external asset provider.

    Subclasses set :attr:`asset_type` and :attr:`name`, implement
    :meth:`discover`, and may override :meth:`available` / :meth:`fetch`.
    """

    asset_type: AssetType
    name: str

    def available(self) -> bool:
        """Whether this source can be used right now (e.g. API key present).

        Sources that fail this check are skipped by the registry, so a missing
        key degrades gracefully instead of erroring.
        """
        return True

    @abstractmethod
    def discover(self, query: AssetQuery) -> List[Asset]:
        """Return candidate assets matching *query* (metadata only, no download).

        Implementations should populate ``url`` with a directly downloadable
        link and set ``popularity`` / ``published_at`` / ``tags`` when the
        source exposes them, so ranking has signal to work with.
        """
        raise NotImplementedError

    def fetch(self, asset: Asset) -> Optional[str]:
        """Download ``asset.url`` to a temp file and return its path (or None).

        The default implementation is a plain HTTP GET (with backoff), which
        covers Pixabay and Freesound preview URLs. Sources needing auth headers
        or yt-dlp can override this.

        Downloads that fail after retries are negative-cached by ``cache_key``,
        so a persistently broken asset (e.g. a track whose storage node 500s) is
        skipped on future cycles instead of being re-fetched every time.
        """
        # Skip assets we already know are broken/rate-limited this window.
        if is_bad(asset.cache_key):
            logger.debug("[%s] skipping known-bad asset %s (negative cache)", self.name, asset.cache_key)
            return None
        try:
            resp = get_with_backoff(asset.url, timeout=_DOWNLOAD_TIMEOUT)

            url_hash = hashlib.md5(asset.url.encode()).hexdigest()[:8]
            ext = ".wav" if ".wav" in asset.url.lower() else ".mp3"
            prefix = f"{asset.theme or asset.asset_type.value}_{url_hash}_"

            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=ext, prefix=prefix)
            tmp.write(resp.content)
            tmp.close()
            logger.info("[%s] downloaded %s -> %s", self.name, asset.cache_key, tmp.name)
            return tmp.name
        except Exception as exc:  # noqa: BLE001 — a single source failing is non-fatal
            # Blocklist for the negative-cache TTL so we stop retrying it every cycle.
            mark_bad(asset.cache_key)
            logger.warning(
                "[%s] download failed for %s (negative-cached): %s",
                self.name, asset.cache_key, exc,
            )
            return None


__all__ = ["AssetSource"]
