"""
tools/assets/models.py
~~~~~~~~~~~~~~~~~~~~~~~
Core data models for the generalized asset discovery & retrieval layer.

An *asset* is any external resource an AI node may want to attach to generated
content: background music (the only type wired up today), and — by design —
b-roll, images, sound effects, trending topics, news, etc. New asset types are
added simply by extending :class:`AssetType` and registering an
:class:`~tools.assets.base.AssetSource`; nothing else in the layer changes.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class AssetType(str, Enum):
    """Kinds of external assets the layer can discover and retrieve.

    Only ``MUSIC`` has providers wired up today. The rest are reserved to show
    the layer is type-agnostic — adding one means implementing an
    :class:`AssetSource` for it and registering it.
    """

    MUSIC = "music"
    BROLL = "broll"
    IMAGE = "image"
    SFX = "sfx"
    TOPIC = "topic"
    NEWS = "news"


@dataclass
class Asset:
    """A normalized record for a single discoverable external asset.

    The same shape covers every ``AssetType``; type-specific extras live in
    :attr:`metadata`. ``discovered_at`` is *our* freshness signal (epoch seconds
    when we first cached it), distinct from :attr:`published_at` which is the
    source's own publish timestamp.
    """

    asset_type: AssetType
    source: str                                 # provider name, e.g. "pixabay"
    source_id: str                              # provider-local id (stable)
    title: str
    url: str                                    # remote/preview URL to download
    local_path: Optional[str] = None            # set once downloaded into cache
    tags: List[str] = field(default_factory=list)
    theme: Optional[str] = None                 # AudioTheme value for music; bucket key
    duration: Optional[float] = None            # seconds, when known
    popularity: float = 0.0                     # source signal (downloads/views/likes)
    published_at: Optional[str] = None          # source recency (ISO string), when known
    discovered_at: float = 0.0                  # epoch when WE cached it (freshness)
    attribution: Optional[str] = None           # license/credit string when required
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def cache_key(self) -> str:
        """Stable dedupe key across discovery runs."""
        return f"{self.source}:{self.source_id}"

    def to_index(self) -> Dict[str, Any]:
        """Serialise to a JSON-friendly dict for the on-disk metadata index."""
        return {
            "asset_type": self.asset_type.value,
            "source": self.source,
            "source_id": self.source_id,
            "title": self.title,
            "url": self.url,
            "local_path": self.local_path,
            "tags": self.tags,
            "theme": self.theme,
            "duration": self.duration,
            "popularity": self.popularity,
            "published_at": self.published_at,
            "discovered_at": self.discovered_at,
            "attribution": self.attribution,
            "metadata": self.metadata,
        }

    @classmethod
    def from_index(cls, data: Dict[str, Any]) -> "Asset":
        """Rebuild an Asset from a JSON index entry (inverse of to_index)."""
        return cls(
            asset_type=AssetType(data["asset_type"]),
            source=data["source"],
            source_id=data["source_id"],
            title=data.get("title", ""),
            url=data.get("url", ""),
            local_path=data.get("local_path"),
            tags=list(data.get("tags", [])),
            theme=data.get("theme"),
            duration=data.get("duration"),
            popularity=float(data.get("popularity", 0.0)),
            published_at=data.get("published_at"),
            discovered_at=float(data.get("discovered_at", 0.0)),
            attribution=data.get("attribution"),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class AssetQuery:
    """A request for assets of one type, with optional ranking hints.

    ``theme`` doubles as the cache *bucket* key (e.g. an AudioTheme value for
    music). ``order`` biases both the provider query and local ranking;
    ``"latest"`` is the default so callers get fresh assets unless they ask
    otherwise.
    """

    asset_type: AssetType
    theme: Optional[str] = None
    keywords: List[str] = field(default_factory=list)
    order: str = "latest"                       # "latest" | "popular" | "relevance"
    min_duration: Optional[float] = None
    max_duration: Optional[float] = None
    limit: int = 5                              # how many to discover/keep per bucket
    user_id: Optional[str] = None              # personalization hook (unused in v1)
    include_vocals: bool = False               # songs search: allow vocal tracks + name search

    @property
    def bucket(self) -> str:
        """Cache partition key within an asset type."""
        return self.theme or "default"


__all__ = ["AssetType", "Asset", "AssetQuery"]


def _now() -> float:
    return time.time()
