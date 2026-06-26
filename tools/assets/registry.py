"""
tools/assets/registry.py
~~~~~~~~~~~~~~~~~~~~~~~~~~
A tiny in-process registry mapping :class:`AssetType` -> ordered list of
:class:`AssetSource` providers.

Order matters: sources are tried in registration order, mirroring the old
``AudioFetcher`` tier order (Pixabay before Freesound). Built-in sources are
registered on first use via :func:`tools.assets.sources.ensure_sources_registered`.
"""

from __future__ import annotations

import logging
from typing import Dict, List

from tools.assets.base import AssetSource
from tools.assets.models import AssetType

logger = logging.getLogger(__name__)

_REGISTRY: Dict[AssetType, List[AssetSource]] = {}


def register_source(source: AssetSource) -> None:
    """Register *source* under its declared ``asset_type`` (idempotent by name)."""
    sources = _REGISTRY.setdefault(source.asset_type, [])
    if any(s.name == source.name for s in sources):
        return  # already registered — avoid duplicates on repeated imports
    sources.append(source)
    logger.debug("registered asset source '%s' for type %s", source.name, source.asset_type.value)


def get_sources(asset_type: AssetType, available_only: bool = True) -> List[AssetSource]:
    """Return registered sources for *asset_type*.

    When ``available_only`` (default), sources whose :meth:`available` is False
    (e.g. missing API key) are filtered out so callers only see usable ones.
    """
    from tools.assets.sources import ensure_sources_registered

    ensure_sources_registered()
    sources = _REGISTRY.get(asset_type, [])
    if available_only:
        return [s for s in sources if s.available()]
    return list(sources)


def clear_registry() -> None:
    """Reset the registry (test helper)."""
    _REGISTRY.clear()


__all__ = ["register_source", "get_sources", "clear_registry"]
