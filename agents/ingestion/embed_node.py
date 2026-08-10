"""
agents/ingestion/embed_node.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Stage 7 — attach vectors to the searchable nodes (transcript chunks + text blocks
= text; scene keyframes = image; the asset summary = text). Uses the cached,
content-addressable embedding wrappers so each vector is computed once and reused
across re-ingests. Degrade-not-fail: any embedding failure leaves the affected
items un-vectored (they remain reachable via graph traversal).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from agents.ingestion._logging_utils import node_stage

logger = logging.getLogger(__name__)


def _embed_impl(state: Dict[str, Any]) -> Dict[str, Any]:
    from tools.embeddings import embed_image_cached, embed_text_cached

    chunks: List[Dict[str, Any]] = state.get("transcript_chunks") or []
    blocks: List[Dict[str, Any]] = state.get("text_blocks") or []
    scenes: List[Dict[str, Any]] = state.get("scenes") or []
    media_asset: Dict[str, Any] = dict(state.get("media_asset") or {})

    # --- text: chunks + ocr blocks + asset summary ---
    try:
        if chunks:
            for c, v in zip(chunks, embed_text_cached([c["text"] for c in chunks])):
                c["embedding"] = v
        if blocks:
            for b, v in zip(blocks, embed_text_cached([b["text"] for b in blocks])):
                b["embedding"] = v
        summary_text = " ".join(
            filter(None, [media_asset.get("title"), (chunks[0]["text"] if chunks else "")])
        ).strip()
        if summary_text:
            media_asset["summary"] = media_asset.get("summary") or summary_text[:500]
            media_asset["embedding"] = embed_text_cached([summary_text])[0]
    except Exception as exc:  # noqa: BLE001
        logger.info("text embedding degraded (%s).", exc)

    # --- image: scene keyframes (shared CLIP space) ---
    try:
        kf_scenes = [s for s in scenes if s.get("keyframe_path")]
        if kf_scenes:
            vecs = embed_image_cached([s["keyframe_path"] for s in kf_scenes])
            for s, v in zip(kf_scenes, vecs):
                s["embedding"] = v
    except Exception as exc:  # noqa: BLE001
        logger.info("image embedding degraded (%s).", exc)

    return {
        "transcript_chunks": chunks,
        "text_blocks": blocks,
        "scenes": scenes,
        "media_asset": media_asset,
    }


def embed_node(state: Dict[str, Any]) -> Dict[str, Any]:
    with node_stage(state, "embed"):
        return _embed_impl(state)


__all__ = ["embed_node"]
