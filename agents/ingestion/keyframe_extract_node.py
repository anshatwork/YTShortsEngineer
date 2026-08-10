"""
agents/ingestion/keyframe_extract_node.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Stage 3 — grab one representative keyframe per scene (CAS-cached). For an image
asset the "keyframe" is the image itself. Degrade-not-fail: a scene whose
keyframe can't be produced simply carries no ``keyframe_path``.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List

from agents.ingestion._logging_utils import node_stage
from tools.vision import extract_keyframe


def _kf_dir(content_hash: str) -> Path:
    root = Path(os.getenv("OUTPUT_DIR", "output")).resolve()
    d = root / "kg" / content_hash / "keyframes"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _keyframe_extract_impl(state: Dict[str, Any]) -> Dict[str, Any]:
    scenes: List[Dict[str, Any]] = list(state.get("scenes") or [])
    media_type = state.get("media_type", "video")
    source = state.get("source_path")
    content_hash = state.get("content_hash") or "unknown"

    if media_type == "image" and source:
        for sc in scenes:
            sc["keyframe_path"] = source
            sc["t_s"] = 0.0
        return {"scenes": scenes}

    if media_type not in ("video",) or not source:
        return {"scenes": scenes}  # nothing visual to sample

    out_dir = _kf_dir(content_hash)
    for sc in scenes:
        mid = (float(sc["start_s"]) + float(sc["end_s"])) / 2.0
        dest = out_dir / f"scene_{sc['scene_index']:04d}.jpg"
        path = extract_keyframe(source, mid, dest)
        if path:
            sc["keyframe_path"] = path
            sc["t_s"] = round(mid, 3)
    return {"scenes": scenes}


def keyframe_extract_node(state: Dict[str, Any]) -> Dict[str, Any]:
    with node_stage(state, "keyframe_extract"):
        return _keyframe_extract_impl(state)


__all__ = ["keyframe_extract_node"]
