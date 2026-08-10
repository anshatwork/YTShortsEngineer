"""
tools/embeddings
~~~~~~~~~~~~~~~~~
Provider-agnostic embedding factory — the image/text counterpart of ``tools/llm``.

    from tools.embeddings import get_embedder, embed_text_cached

    emb = get_embedder()
    vecs = emb.embed_text(["hello", "world"])       # list[list[float]]
    img  = emb.embed_image(["/path/frame.jpg"])     # cross-modal (CLIP) space

Provider selection (env ``EMBEDDING_PROVIDER``): ``local`` (default) | ``hash``.
When ``local`` is selected the heavy ML deps are imported lazily and, unless
``EMBEDDING_FALLBACK=0``, any failure (missing torch/sentence-transformers, OOM)
degrades to the dependency-free :class:`~tools.embeddings.hashing.HashEmbedder`
so ingestion never hard-fails — the same fallback philosophy as ``FallbackLLM``.

``embed_text_cached`` / ``embed_image_cached`` memoize per item in the
content-addressable cache (``core/cache``) keyed on (model, content hash), so an
expensive embedding is computed exactly once and reused across re-ingests.
"""

from __future__ import annotations

import logging
import os
from typing import List, Sequence

from core.cache import get_cache, hash_file, hash_text
from tools.embeddings.base import BaseEmbedder

logger = logging.getLogger(__name__)

_EMBED_CACHE_VERSION = 1


def _truthy(name: str, default: str = "true") -> bool:
    return os.getenv(name, default).lower() not in ("0", "false", "no", "")


def _dims() -> dict:
    return {
        "text_dim": int(os.getenv("EMBEDDING_DIM_TEXT", "384")),
        "image_dim": int(os.getenv("EMBEDDING_DIM_IMAGE", "512")),
    }


class FallbackEmbedder(BaseEmbedder):
    """Wrap a primary embedder and degrade to a fallback on any failure."""

    def __init__(self, primary: BaseEmbedder, fallback: BaseEmbedder) -> None:
        self._primary = primary
        self._fallback = fallback
        self.text_model_id = primary.text_model_id
        self.image_model_id = primary.image_model_id
        self.text_dim = primary.text_dim
        self.image_dim = primary.image_dim
        self._degraded = False

    def _note(self, op: str, exc: Exception) -> None:
        if not self._degraded:
            logger.warning(
                "Local embedder failed during %s (%s); using hash fallback. "
                "Install sentence-transformers/open_clip for real embeddings.",
                op, exc,
            )
            self._degraded = True
        # Once degraded, adopt the fallback's model id so cache keys reflect it.
        self.text_model_id = self._fallback.text_model_id
        self.image_model_id = self._fallback.image_model_id

    def embed_text(self, texts: Sequence[str]) -> List[List[float]]:
        try:
            return self._primary.embed_text(texts)
        except Exception as exc:  # noqa: BLE001
            self._note("embed_text", exc)
            return self._fallback.embed_text(texts)

    def embed_image(self, image_paths: Sequence[str]) -> List[List[float]]:
        try:
            return self._primary.embed_image(image_paths)
        except Exception as exc:  # noqa: BLE001
            self._note("embed_image", exc)
            return self._fallback.embed_image(image_paths)


def get_embedder() -> BaseEmbedder:
    """Return the configured embedder (default local, hash fallback)."""
    provider = os.getenv("EMBEDDING_PROVIDER", "local").lower()
    dims = _dims()
    if provider == "hash":
        from tools.embeddings.hashing import HashEmbedder

        return HashEmbedder(**dims)
    if provider == "local":
        from tools.embeddings.hashing import HashEmbedder
        from tools.embeddings.local import LocalEmbedder

        primary = LocalEmbedder()
        if not _truthy("EMBEDDING_FALLBACK"):
            return primary
        return FallbackEmbedder(primary, HashEmbedder(**dims))
    raise ValueError(f"Unknown EMBEDDING_PROVIDER '{provider}' (use local | hash)")


# ---------------------------------------------------------------------------
# Cached, content-addressable wrappers (compute once, reuse across re-ingests)
# ---------------------------------------------------------------------------

def embed_text_cached(texts: Sequence[str], *, embedder: BaseEmbedder | None = None) -> List[List[float]]:
    """Embed *texts*, memoizing each string on (model, text hash) in the CAS."""
    emb = embedder or get_embedder()
    cache = get_cache()
    out: List[List[float]] = []
    for t in texts:
        inputs = {"model": emb.text_model_id, "hash": hash_text(t)}
        vec = cache.get_or_compute_json(
            "kg_embed_text", _EMBED_CACHE_VERSION, inputs,
            lambda t=t: {"v": emb.embed_text([t])[0]},
        )["v"]
        out.append(vec)
    return out


def embed_image_cached(image_paths: Sequence[str], *, embedder: BaseEmbedder | None = None) -> List[List[float]]:
    """Embed images, memoizing each on (model, file content hash) in the CAS."""
    emb = embedder or get_embedder()
    cache = get_cache()
    out: List[List[float]] = []
    for path in image_paths:
        try:
            fh = hash_file(path)
        except OSError:
            fh = hash_text(str(path))
        inputs = {"model": emb.image_model_id, "hash": fh}
        vec = cache.get_or_compute_json(
            "kg_embed_image", _EMBED_CACHE_VERSION, inputs,
            lambda p=path: {"v": emb.embed_image([p])[0]},
        )["v"]
        out.append(vec)
    return out


__all__ = [
    "BaseEmbedder",
    "FallbackEmbedder",
    "get_embedder",
    "embed_text_cached",
    "embed_image_cached",
]
