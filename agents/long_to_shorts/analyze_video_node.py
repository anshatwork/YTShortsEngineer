"""
agents/long_to_shorts/analyze_video_node.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
AnalyzeVideoNode – LLM-powered transcript segmentation and Hook Scoring.

Workflow:
  1.  Chunk the transcript into overlapping ~60-second windows (by char count).
  2.  Send each chunk to the LLM with a structured JSON prompt.
  3.  Parse the response; every segment gets a hook_score (1–10).
  4.  Sort by hook_score descending and keep the top `top_n_clips`.
  5.  Return a list of ClipObject stubs (path / title / summary are None at this stage).
"""

import json
import logging
from typing import Any, Dict, List

from agents.state import ClipObject, LongToShortsState
from tools.llm.ollama import get_chat_model

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Approximate characters per second of speech at a moderate pace (~130 wpm).
_CHARS_PER_SECOND: float = 10.5
# Target segment length in seconds.
_TARGET_SEGMENT_SECONDS: float = 55.0
# Overlap between consecutive windows (seconds) to avoid cutting sentences.
_OVERLAP_SECONDS: float = 10.0
# Minimum segment duration (seconds). Clips shorter than this are unusable for Shorts.
MIN_SEGMENT_SECONDS: float = 45.0

_CHUNK_SIZE: int = int(_TARGET_SEGMENT_SECONDS * _CHARS_PER_SECOND)
_OVERLAP_SIZE: int = int(_OVERLAP_SECONDS * _CHARS_PER_SECOND)

_ANALYSIS_PROMPT = """\
You are a senior viral content strategist specialising exclusively in YouTube Shorts.
Your job is to find the single most scroll-stopping segment in a transcript excerpt.

━━━ HOOK SCORE RUBRIC (1–10) ━━━
10 – Jaw-dropping opening line + clear story arc + strong emotional payoff
 9 – Surprising fact or reveal that demands a share
 8 – Relatable emotional story with a satisfying resolution
 7 – Controversial take or bold opinion that sparks debate
 6 – Genuinely funny moment or unexpected humour
 5 – Useful how-to insight that solves a real problem
 4 – Moderately interesting but lacks a hook or payoff
 3 – Generic information with no emotional trigger
 2 – Rambling or off-topic content
 1 – Purely administrative / completely forgettable

━━━ HOOK TYPE CLASSIFICATION ━━━
Choose exactly ONE from:
  curiosity_gap | surprising_fact | emotional_story | controversy | humor | how_to

━━━ DURATION RULES ━━━
The segment MUST be 45–75 seconds long (end_time − start_time ≥ 45 and ≤ 75).
Do NOT pick a single line or a moment — we need a FULL self-contained story arc.
If the excerpt is shorter than 45 seconds, use the whole excerpt.

━━━ OUTPUT FORMAT ━━━
Return ONLY a valid JSON object — no markdown fences, no commentary — \
with EXACTLY these keys:
  "start_time" : float — start offset in seconds relative to this excerpt (0 = excerpt start)
  "end_time"   : float — end offset in seconds relative to this excerpt (start_time + 45 to 75)
  "hook_score" : float — your score from 1 to 10 (one decimal place)
  "hook_type"  : string — one of the six types above
  "reason"     : string — one sentence explaining WHY this segment scores this high

Transcript excerpt (starts at {offset_seconds:.1f}s into the video):
\"\"\"
{transcript_chunk}
\"\"\"
"""


# ---------------------------------------------------------------------------
# Helper: chunk transcript into overlapping windows
# ---------------------------------------------------------------------------

def _chunk_transcript(transcript: str) -> List[Dict[str, Any]]:
    """
    Split *transcript* into overlapping character windows.

    Returns a list of dicts:
        {"text": str, "offset_seconds": float}
    where *offset_seconds* is the estimated start time of that chunk in the video.
    """
    chunks: List[Dict[str, Any]] = []
    start = 0
    chunk_idx = 0

    while start < len(transcript):
        end = min(start + _CHUNK_SIZE, len(transcript))
        chunk_text = transcript[start:end]
        offset_seconds = (start / _CHARS_PER_SECOND)

        chunks.append({
            "text": chunk_text,
            "offset_seconds": offset_seconds,
            "chunk_idx": chunk_idx,
        })

        chunk_idx += 1
        start += _CHUNK_SIZE - _OVERLAP_SIZE  # slide with overlap

    return chunks


# ---------------------------------------------------------------------------
# Helper: parse LLM JSON response
# ---------------------------------------------------------------------------

def _parse_llm_json(
    raw: str, offset_seconds: float, chunk_duration_seconds: float | None = None
) -> Dict[str, Any]:
    """
    Extract a JSON object from *raw*.
    Adjusts start_time / end_time by adding *offset_seconds*, then
    guarantees the segment is at least MIN_SEGMENT_SECONDS long using a
    bidirectional strategy:

      1. Extend end_time forward to start + MIN_SEGMENT_SECONDS.
      2. If end_time would exceed the chunk boundary, pull start_time back
         so the segment still fills exactly MIN_SEGMENT_SECONDS.

    This means even a segment the LLM places at the very end of a chunk
    will always emerge as a full-length clip.
    Raises ValueError on parse failure.
    """
    # Strip accidental markdown fences
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    text = text.strip("`").strip()

    data = json.loads(text)

    # Adjust times to absolute video position
    start = float(data.get("start_time", 0)) + offset_seconds
    end   = float(data.get("end_time",   60)) + offset_seconds
    data["hook_score"] = max(1.0, min(10.0, float(data.get("hook_score", 5.0))))

    # ------------------------------------------------------------------
    # Guarantee minimum clip duration
    # ------------------------------------------------------------------
    duration = end - start
    if duration < MIN_SEGMENT_SECONDS:
        original = (start, end)

        # Step 1: extend end forward
        end = start + MIN_SEGMENT_SECONDS

        if chunk_duration_seconds is not None:
            chunk_end = offset_seconds + chunk_duration_seconds
            if end > chunk_end:
                # Step 2: chunk too short to extend forward — pull start back
                end   = chunk_end
                start = max(offset_seconds, chunk_end - MIN_SEGMENT_SECONDS)

        logger.debug(
            f"Adjusted short segment {original[0]:.1f}s→{original[1]:.1f}s "
            f"({original[1]-original[0]:.1f}s) to "
            f"{start:.1f}s→{end:.1f}s ({end-start:.1f}s)"
        )

    data["start_time"] = start
    data["end_time"]   = end

    return data


# ---------------------------------------------------------------------------
# Helper: fallback synthetic segments
# ---------------------------------------------------------------------------

def _make_synthetic_segments(
    transcript: str, top_n: int
) -> List[Dict[str, Any]]:
    """
    When LLM analysis fails entirely, divide the transcript into evenly-spaced
    60-second segments so the rest of the pipeline can still run.
    """
    total_seconds = len(transcript) / _CHARS_PER_SECOND
    segment_len = 60.0
    segments = []
    t = 0.0
    idx = 0
    while t + segment_len <= total_seconds and idx < top_n:
        segments.append({
            "start_time": t,
            "end_time": t + segment_len,
            "hook_score": 5.0,
            "reason": "synthetic fallback segment",
        })
        t += segment_len * 0.8  # 20 % overlap
        idx += 1
    return segments[:top_n]


# ---------------------------------------------------------------------------
# Node function
# ---------------------------------------------------------------------------

def analyze_video_node(state: LongToShortsState) -> Dict[str, Any]:
    """
    LangGraph node: score transcript segments and return top ClipObject stubs.

    Input state keys used:
        transcript   – full text transcript of the long video
        top_n_clips  – how many top clips to keep (default: 5)
        source_video_path – propagated to each ClipObject

    Output state keys:
        analyzed_segments – List[ClipObject] sorted by hook_score desc
        current_step
    """
    transcript: str = state.get("transcript", "")
    top_n: int = state.get("top_n_clips", 5)
    source_path: str = state.get("source_video_path", "")

    if not transcript.strip():
        logger.error("AnalyzeVideoNode: transcript is empty.")
        return {"analyzed_segments": [], "current_step": "analysis_failed",
                "error": "Empty transcript provided."}

    logger.info(
        f"AnalyzeVideoNode: analysing {len(transcript)} chars, "
        f"requesting top-{top_n} clips."
    )

    chunks = _chunk_transcript(transcript)
    logger.info(f"AnalyzeVideoNode: split into {len(chunks)} chunks.")

    # Collect raw scored segments from LLM
    raw_segments: List[Dict[str, Any]] = []
    llm_available = True

    try:
        llm = get_chat_model()
    except Exception as exc:
        logger.warning(f"AnalyzeVideoNode: LLM unavailable ({exc}). Using synthetic fallback.")
        llm_available = False

    if llm_available:
        for chunk in chunks:
            prompt_text = _ANALYSIS_PROMPT.format(
                offset_seconds=chunk["offset_seconds"],
                transcript_chunk=chunk["text"],
            )
            try:
                from langchain_core.messages import HumanMessage
                response = llm.invoke([HumanMessage(content=prompt_text)])
                raw_text = response.content if hasattr(response, "content") else str(response)
                chunk_duration = len(chunk["text"]) / _CHARS_PER_SECOND
                segment = _parse_llm_json(
                    raw_text,
                    chunk["offset_seconds"],
                    chunk_duration_seconds=chunk_duration,
                )
                raw_segments.append(segment)
                logger.debug(
                    f"  Chunk {chunk['chunk_idx']}: score={segment['hook_score']:.1f} "
                    f"({segment['start_time']:.1f}s → {segment['end_time']:.1f}s)"
                )
            except Exception as exc:
                logger.warning(
                    f"AnalyzeVideoNode: failed to parse chunk {chunk['chunk_idx']}: {exc}"
                )

    # Fallback if LLM yielded nothing
    if not raw_segments:
        logger.warning("AnalyzeVideoNode: no segments from LLM; using synthetic fallback.")
        raw_segments = _make_synthetic_segments(transcript, top_n)

    # Sort and keep top-N
    raw_segments.sort(key=lambda s: s["hook_score"], reverse=True)
    top_segments = raw_segments[:top_n]

    # Build ClipObject stubs
    clip_objects: List[ClipObject] = []
    for i, seg in enumerate(top_segments):
        clip: ClipObject = {
            "clip_id": f"clip_{i + 1:03d}",
            "source_video_path": source_path,
            "path": None,
            "timestamp_range": (seg["start_time"], seg["end_time"]),
            "hook_score": seg["hook_score"],
            "title": None,
            "summary": None,
        }
        clip_objects.append(clip)
        logger.info(
            f"  Selected clip_{i + 1:03d}: score={seg['hook_score']:.1f}  "
            f"{seg['start_time']:.1f}s → {seg['end_time']:.1f}s  | {seg.get('reason', '')}"
        )

    logger.info(f"AnalyzeVideoNode: selected {len(clip_objects)} segments.")
    return {
        "analyzed_segments": clip_objects,
        "current_step": "analysis_complete",
    }
