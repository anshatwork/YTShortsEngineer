"""
agents/ingestion/scene_detect_node.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Stage 2 — segment a video into scenes (the temporal spine of the graph). For
non-video assets it emits a single scene covering the whole asset so downstream
keyframe/OCR/embed stages still run. Degrade-not-fail: any failure yields one
whole-asset scene.
"""

from __future__ import annotations

from typing import Any, Dict, List

from agents.ingestion._logging_utils import node_stage
from tools.vision import detect_scenes


def _scene_detect_impl(state: Dict[str, Any]) -> Dict[str, Any]:
    media_type = state.get("media_type", "video")
    source = state.get("source_path")
    duration = float(state.get("duration_s") or 0.0)

    if media_type == "video" and source:
        intervals = detect_scenes(source)
    else:
        intervals = [(0.0, duration)]

    scenes: List[Dict[str, Any]] = [
        {"scene_index": i, "start_s": start, "end_s": end}
        for i, (start, end) in enumerate(intervals)
    ]
    return {"scenes": scenes}


def scene_detect_node(state: Dict[str, Any]) -> Dict[str, Any]:
    with node_stage(state, "scene_detect"):
        return _scene_detect_impl(state)


__all__ = ["scene_detect_node"]
