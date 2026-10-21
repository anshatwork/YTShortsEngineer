"""
agents/ingestion/ocr_node.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Stage 6 — read on-screen text from scene keyframes (OCR). Optional: if no OCR
backend is installed this produces no ``TextBlock`` records and ingestion carries
on (degrade-not-fail). Powers queries like "screenshots containing error
messages".
"""

from __future__ import annotations

from typing import Any, Dict, List

from agents.ingestion._logging_utils import node_stage
from core.cache.keys import hash_text
from tools.vision import ocr_available, ocr_image


def _ocr_impl(state: Dict[str, Any]) -> Dict[str, Any]:
    if not ocr_available():
        return {"text_blocks": []}

    scenes: List[Dict[str, Any]] = state.get("scenes") or []
    blocks: List[Dict[str, Any]] = []
    for sc in scenes:
        kf = sc.get("keyframe_path")
        if not kf:
            continue
        t_s = float(sc.get("t_s", sc.get("start_s", 0.0)))
        for b in ocr_image(kf):
            text = (b.get("text") or "").strip()
            if not text:
                continue
            block_key = hash_text(f"{sc['scene_index']}|{t_s}|{b.get('bbox')}|{text}")
            blocks.append({
                "block_key": block_key,
                "text": text,
                "bbox": b.get("bbox"),
                "confidence": b.get("confidence"),
                "t_s": round(t_s, 3),
                "scene_index": sc["scene_index"],
            })
    return {"text_blocks": blocks}


def ocr_node(state: Dict[str, Any]) -> Dict[str, Any]:
    with node_stage(state, "ocr"):
        return _ocr_impl(state)


__all__ = ["ocr_node"]
