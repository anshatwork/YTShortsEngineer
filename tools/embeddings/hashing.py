"""
tools/embeddings/hashing.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Dependency-free deterministic embedder.

This is the **degrade-not-fail** fallback: when the local ML stack
(sentence-transformers / open_clip / torch) is not installed, or
``EMBEDDING_PROVIDER=hash`` is set, ingestion still produces stable vectors so the
graph, its vector indexes and the tests all work end-to-end. The vectors are
deterministic hashes of the input — useful for exact/near-exact matching and for
testing the whole pipeline, but NOT semantically meaningful. Swap in the local or
an API provider for real semantic search.

Vectors are L2-normalized (unit length) so a cosine index behaves sensibly, and
image "embeddings" hash the file's content bytes.
"""

from __future__ import annotations

import hashlib
import math
from typing import List, Sequence

from tools.embeddings.base import BaseEmbedder


def _hash_vector(seed: bytes, dim: int) -> List[float]:
    """Deterministically expand *seed* into a unit-length vector of length *dim*."""
    out: List[float] = []
    counter = 0
    while len(out) < dim:
        digest = hashlib.sha256(seed + counter.to_bytes(4, "big")).digest()
        # each byte → a float in [-1, 1)
        for b in digest:
            out.append((b / 127.5) - 1.0)
            if len(out) >= dim:
                break
        counter += 1
    norm = math.sqrt(sum(x * x for x in out)) or 1.0
    return [x / norm for x in out]


class HashEmbedder(BaseEmbedder):
    """Deterministic, dependency-free embedder (fallback / tests)."""

    text_model_id = "hash-v1"
    image_model_id = "hash-img-v1"

    def __init__(self, *, text_dim: int = 384, image_dim: int = 512) -> None:
        self.text_dim = text_dim
        self.image_dim = image_dim

    def embed_text(self, texts: Sequence[str]) -> List[List[float]]:
        return [_hash_vector(t.encode("utf-8"), self.text_dim) for t in texts]

    def embed_image(self, image_paths: Sequence[str]) -> List[List[float]]:
        vectors: List[List[float]] = []
        for path in image_paths:
            try:
                with open(path, "rb") as fh:
                    seed = hashlib.sha256(fh.read()).digest()
            except OSError:
                seed = str(path).encode("utf-8")
            vectors.append(_hash_vector(seed, self.image_dim))
        return vectors


__all__ = ["HashEmbedder"]
