"""
tools.assets
~~~~~~~~~~~~~
Generalized asset discovery & retrieval layer.

AI nodes call :func:`retrieve` with an :class:`AssetQuery` to get the best
external assets (background music today; b-roll, images, SFX, topics, news by
design) for a generation task. The layer discovers from pluggable
:class:`~tools.assets.base.AssetSource` providers, caches results on disk with a
freshness TTL, ranks them, and returns the top matches — minimizing repeat
external searches via cache-first retrieval.

Example::

    from tools.assets import retrieve, AssetQuery, AssetType

    tracks = retrieve(
        AssetQuery(asset_type=AssetType.MUSIC, theme="energetic", order="latest"),
        k=1,
    )
"""

from tools.assets.models import Asset, AssetQuery, AssetType
from tools.assets.retrieval import record_feedback, retrieve

__all__ = ["retrieve", "record_feedback", "Asset", "AssetQuery", "AssetType"]
