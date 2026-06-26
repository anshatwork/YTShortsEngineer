"""
core.cache
~~~~~~~~~~
Unified, content-addressable artifact cache.

Public surface::

    from core.cache import get_cache

    cache = get_cache()
    meta  = cache.get_or_compute_json("probe", 1, {"sha": file_hash}, compute_fn)
    res   = cache.materialize_blob("clip", 1, key_inputs, dest_path, producer, ext=".mp4")

See :mod:`core.cache.cache` for semantics and :mod:`core.cache.keys` for how
deterministic keys are derived.
"""

from core.cache.cache import ArtifactCache, BlobResult, get_cache
from core.cache.keys import hash_file, hash_text, make_key

__all__ = [
    "ArtifactCache",
    "BlobResult",
    "get_cache",
    "hash_file",
    "hash_text",
    "make_key",
]
