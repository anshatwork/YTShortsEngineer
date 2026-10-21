"""
tools/embeddings/local.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~
Local (GPU-default) embedder — the recommended production default.

* text  → ``sentence-transformers`` (bge/e5 family). Default ``BAAI/bge-small-en-v1.5``
  (384-dim), overridable via ``EMBEDDING_MODEL_TEXT``.
* image → ``open_clip`` (OpenCLIP). Default ViT-B/32 / laion2b (512-dim), giving a
  shared text↔image space for cross-modal search. Overridable via
  ``EMBEDDING_MODEL_IMAGE`` (``arch:pretrained``).

Heavy deps are imported lazily and models are loaded once (cached on the
instance), mirroring how ``tools/llm`` only imports a provider's SDK when that
provider is actually selected. If the deps are missing the factory falls back to
:class:`~tools.embeddings.hashing.HashEmbedder` (degrade-not-fail).
"""

from __future__ import annotations

import logging
import os
from typing import Any, List, Optional, Sequence

from tools.embeddings.base import BaseEmbedder

logger = logging.getLogger(__name__)


class LocalEmbedder(BaseEmbedder):
    """sentence-transformers (text) + OpenCLIP (image), loaded lazily."""

    def __init__(self) -> None:
        self.text_model_id = os.getenv("EMBEDDING_MODEL_TEXT", "BAAI/bge-small-en-v1.5")
        self.image_model_id = os.getenv("EMBEDDING_MODEL_IMAGE", "ViT-B-32:laion2b_s34b_b79k")
        self.text_dim = int(os.getenv("EMBEDDING_DIM_TEXT", "384"))
        self.image_dim = int(os.getenv("EMBEDDING_DIM_IMAGE", "512"))
        self._text_model: Optional[Any] = None
        self._clip: Optional[Any] = None
        self._clip_preprocess: Optional[Any] = None
        self._clip_tokenizer: Optional[Any] = None

    # -- text --------------------------------------------------------------

    def _get_text_model(self) -> Any:
        if self._text_model is None:
            from sentence_transformers import SentenceTransformer  # lazy

            self._text_model = SentenceTransformer(self.text_model_id)
        return self._text_model

    def embed_text(self, texts: Sequence[str]) -> List[List[float]]:
        model = self._get_text_model()
        vecs = model.encode(
            list(texts), normalize_embeddings=True, convert_to_numpy=True
        )
        return [v.tolist() for v in vecs]

    # -- image -------------------------------------------------------------

    def _get_clip(self):
        if self._clip is None:
            import open_clip  # lazy

            arch, _, pretrained = self.image_model_id.partition(":")
            model, _, preprocess = open_clip.create_model_and_transforms(
                arch, pretrained=pretrained or None
            )
            model.eval()
            self._clip = model
            self._clip_preprocess = preprocess
            self._clip_tokenizer = open_clip.get_tokenizer(arch)
        return self._clip

    def embed_image(self, image_paths: Sequence[str]) -> List[List[float]]:
        import torch  # lazy
        from PIL import Image

        model = self._get_clip()
        tensors = []
        for path in image_paths:
            img = Image.open(path).convert("RGB")
            tensors.append(self._clip_preprocess(img))
        if not tensors:
            return []
        batch = torch.stack(tensors)
        with torch.no_grad():
            feats = model.encode_image(batch)
            feats = feats / feats.norm(dim=-1, keepdim=True)
        return [row.tolist() for row in feats.cpu()]


__all__ = ["LocalEmbedder"]
