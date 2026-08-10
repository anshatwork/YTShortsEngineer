"""
agents/ingestion/decode_probe_node.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Stage 1 — identify the asset: content hash (the cross-store stable key), media
type, duration and a base ``MediaAsset`` node. The content hash makes ingestion
idempotent — re-ingesting the same bytes MERGEs onto the same node (design §6).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

from agents.ingestion._logging_utils import node_stage
from core.cache.keys import hash_file
from tools.vision import probe_duration

_VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}
_AUDIO_EXT = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}
_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
_DOC_EXT = {".pdf", ".docx", ".txt", ".md"}
_SLIDE_EXT = {".ppt", ".pptx", ".key"}


def _infer_media_type(path: str) -> str:
    ext = Path(path).suffix.lower()
    if ext in _VIDEO_EXT:
        return "video"
    if ext in _AUDIO_EXT:
        return "audio"
    if ext in _IMAGE_EXT:
        return "image"
    if ext in _SLIDE_EXT:
        return "slide"
    if ext in _DOC_EXT:
        return "document"
    return "video"  # sensible default for this product


def _decode_probe_impl(state: Dict[str, Any]) -> Dict[str, Any]:
    source = state.get("source_path")
    if not source or not os.path.exists(source):
        return {"error": f"source_path missing or not found: {source!r}"}

    media_type = state.get("media_type") or _infer_media_type(source)
    content_hash = hash_file(source)
    duration = probe_duration(source) if media_type in ("video", "audio") else 0.0

    media_asset: Dict[str, Any] = {
        "asset_id": state.get("asset_id"),
        "content_hash": content_hash,
        "media_type": media_type,
        "uri": state.get("uri") or source,
        "title": state.get("title") or state.get("filename") or Path(source).stem,
        "duration_s": round(duration, 3),
    }
    return {
        "content_hash": content_hash,
        "media_type": media_type,
        "duration_s": round(duration, 3),
        "media_asset": media_asset,
    }


def decode_probe_node(state: Dict[str, Any]) -> Dict[str, Any]:
    with node_stage(state, "decode_probe"):
        return _decode_probe_impl(state)


__all__ = ["decode_probe_node"]
