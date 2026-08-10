"""
tools/embeddings/base.py
~~~~~~~~~~~~~~~~~~~~~~~~~~
Provider-agnostic embedding interface — mirrors ``tools/llm/base.py``.

An embedder turns text and images into vectors in a shared (ideally cross-modal)
space so the KG can do text→text, image→image and text→image search from one
index. Providers implement :meth:`embed_text` and :meth:`embed_image`; both return
one vector per input, in order.

Dimensions are provider properties so the schema's vector indexes can be created
to match (see ``core/kg/schema.py`` reading ``EMBEDDING_DIM_TEXT``/``_IMAGE``).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Sequence


class BaseEmbedder(ABC):
    """Abstract base for text+image embedding providers."""

    #: identifier folded into cache keys so different models never collide
    text_model_id: str = "base-text"
    image_model_id: str = "base-image"
    text_dim: int = 384
    image_dim: int = 512

    @abstractmethod
    def embed_text(self, texts: Sequence[str]) -> List[List[float]]:
        """Return one vector (length ``text_dim``) per input string, in order."""
        ...

    def embed_image(self, image_paths: Sequence[str]) -> List[List[float]]:
        """Return one vector (length ``image_dim``) per image path, in order.

        Defaults to raising so a text-only provider degrades explicitly rather
        than silently returning wrong-shaped vectors.
        """
        raise NotImplementedError(
            f"{type(self).__name__} does not support image embeddings"
        )


__all__ = ["BaseEmbedder"]
