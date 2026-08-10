"""
agents/ingestion/chunk_transcript_node.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Stage 5 — window the transcript into timestamped ``TranscriptChunk`` records
(the temporal, searchable text units). Mirrors the windowing idea in
``analyze_video_node``: prefer real timestamps from ``timed_transcript``; else
estimate them proportionally over the probed duration.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List

from agents.ingestion._logging_utils import node_stage


def _target_seconds() -> float:
    try:
        return float(os.getenv("KG_CHUNK_SECONDS", "30"))
    except ValueError:
        return 30.0


def _chunks_from_timed(timed: List[Dict[str, Any]], window: float) -> List[Dict[str, Any]]:
    chunks: List[Dict[str, Any]] = []
    buf: List[str] = []
    start = None
    last_end = 0.0
    idx = 0
    for seg in timed:
        s = float(seg.get("start", 0.0))
        d = float(seg.get("duration", 0.0))
        text = (seg.get("text") or "").strip()
        if start is None:
            start = s
        buf.append(text)
        last_end = s + d
        if last_end - start >= window and buf:
            chunks.append({
                "chunk_index": idx, "start_s": round(start, 3),
                "end_s": round(last_end, 3), "text": " ".join(buf).strip(),
            })
            idx += 1
            buf, start = [], None
    if buf and start is not None:
        chunks.append({
            "chunk_index": idx, "start_s": round(start, 3),
            "end_s": round(last_end, 3), "text": " ".join(buf).strip(),
        })
    return [c for c in chunks if c["text"]]


def _chunks_from_text(text: str, duration: float, window: float) -> List[Dict[str, Any]]:
    words = text.split()
    if not words:
        return []
    # Estimate words-per-window from an assumed ~2.5 words/sec speaking rate.
    per_window = max(30, int(window * 2.5))
    n_windows = max(1, (len(words) + per_window - 1) // per_window)
    span = (duration / n_windows) if duration else window
    chunks: List[Dict[str, Any]] = []
    for i in range(n_windows):
        seg_words = words[i * per_window:(i + 1) * per_window]
        if not seg_words:
            continue
        chunks.append({
            "chunk_index": i,
            "start_s": round(i * span, 3),
            "end_s": round((i + 1) * span, 3),
            "text": " ".join(seg_words),
        })
    return chunks


def _chunk_transcript_impl(state: Dict[str, Any]) -> Dict[str, Any]:
    window = _target_seconds()
    timed = state.get("timed_transcript")
    if timed:
        return {"transcript_chunks": _chunks_from_timed(timed, window)}
    text = (state.get("transcript") or "").strip()
    if text:
        return {
            "transcript_chunks": _chunks_from_text(
                text, float(state.get("duration_s") or 0.0), window
            )
        }
    return {"transcript_chunks": []}


def chunk_transcript_node(state: Dict[str, Any]) -> Dict[str, Any]:
    with node_stage(state, "chunk_transcript"):
        return _chunk_transcript_impl(state)


__all__ = ["chunk_transcript_node"]
