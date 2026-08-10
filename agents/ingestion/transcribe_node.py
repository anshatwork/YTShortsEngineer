"""
agents/ingestion/transcribe_node.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Stage 4 — obtain the transcript. Reuses the SAME cached helpers the clip pipeline
uses (``run_clipping_workflow.get_transcript`` → cached Whisper), so re-ingesting
a video already transcribed for clipping is a cache hit — expensive understanding
paid for once (design core philosophy).

Preference order: pre-supplied ``timed_transcript`` → pre-supplied ``transcript``
→ cached Whisper. Degrade-not-fail: on any error the transcript is empty and the
graph is still built from the visual/OCR stages.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from agents.ingestion._logging_utils import node_stage

logger = logging.getLogger(__name__)


def _transcribe_impl(state: Dict[str, Any]) -> Dict[str, Any]:
    timed = state.get("timed_transcript")
    transcript = state.get("transcript")

    if timed:
        if not transcript:
            transcript = " ".join(seg.get("text", "") for seg in timed).strip()
        return {"transcript": transcript, "timed_transcript": timed}

    if transcript:
        return {"transcript": transcript}

    media_type = state.get("media_type", "video")
    source = state.get("source_path")
    if media_type not in ("video", "audio") or not source:
        return {"transcript": ""}

    try:
        from run_clipping_workflow import get_transcript

        text = get_transcript(None, source)
        return {"transcript": text or ""}
    except Exception as exc:  # noqa: BLE001 — degrade to no transcript
        logger.info("transcription unavailable (%s); continuing without it.", exc)
        return {"transcript": ""}


def transcribe_node(state: Dict[str, Any]) -> Dict[str, Any]:
    with node_stage(state, "transcribe"):
        return _transcribe_impl(state)


__all__ = ["transcribe_node"]
