"""
agents/long_to_shorts/analyze_video_node.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
AnalyzeVideoNode – LLM-powered transcript segmentation and Hook Scoring.

Workflow:
  1.  Probe the source video for its actual duration. This is the hard
      upper bound for any clip we propose.
  2.  Chunk the transcript into overlapping ~60-second windows. When
      ``state["timed_transcript"]`` is present (YouTube captions API),
      each chunk's start/end is a REAL timestamp pulled from the captions.
      Otherwise we estimate from character offsets, calibrated from the
      probed duration when possible.
  3.  Send each chunk to the LLM with a structured JSON prompt.
  4.  Parse the response; every segment gets a hook_score (1–10).
  5.  Filter any segment that lands outside the probed video duration —
      these are unrecoverable downstream.
  6.  Sort by hook_score descending and keep the top `top_n_clips`.
  7.  Return a list of ClipObject stubs (path / title / summary are None at this stage).
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import ffmpeg  # ffmpeg-python — for source duration probe

from agents.long_to_shorts._logging_utils import node_stage
from agents.state import ClipObject, LongToShortsState
from tools.llm.ollama import get_chat_model

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Approximate characters per second of speech at a moderate pace (~130 wpm).
# Only used as a last-resort fallback when neither a timed transcript nor a
# probable video duration is available; both override this estimate.
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
# Source-video duration probe (best-effort, never raises)
# ---------------------------------------------------------------------------

def _probe_duration(path: str) -> Optional[float]:
    """Return the source video duration in seconds, or None on failure.

    Anything that goes wrong here is non-fatal — analyse can still run with
    a CPS estimate. We just lose the hard upper bound on clip timestamps.
    """
    if not path or not Path(path).exists():
        return None
    try:
        info = ffmpeg.probe(path)
        duration = float(info["format"].get("duration", 0))
        return duration if duration > 0 else None
    except Exception as exc:
        logger.warning(f"AnalyzeVideoNode: video probe failed ({exc}); falling back to CPS estimate.")
        return None


# ---------------------------------------------------------------------------
# Chunking — two strategies, identical output shape
# ---------------------------------------------------------------------------

def _chunk_from_timed_segments(
    segments: List[Dict[str, Any]],
    max_duration_seconds: Optional[float],
) -> List[Dict[str, Any]]:
    """Build chunks from YouTube-caption timed segments.

    Each output chunk carries REAL start/end timestamps drawn from the
    captions. Segments past *max_duration_seconds* (the actual length of
    the downloaded video file) are dropped before chunking so the LLM
    never picks content that doesn't exist in the video.

    Output entries: ``{text, offset_seconds, duration_seconds, chunk_idx}``
    """
    if max_duration_seconds is not None:
        original_n = len(segments)
        segments = [
            s for s in segments
            if float(s.get("start", 0)) < max_duration_seconds
        ]
        dropped = original_n - len(segments)
        if dropped:
            logger.warning(
                f"AnalyzeVideoNode: dropped {dropped} caption segment(s) "
                f"past video duration ({max_duration_seconds:.1f}s) — "
                f"the transcript covers more material than the downloaded file."
            )

    if not segments:
        return []

    chunks: List[Dict[str, Any]] = []
    chunk_idx = 0
    i = 0
    n = len(segments)

    while i < n:
        chunk_start_time = float(segments[i]["start"])

        # Accumulate segments until we hit the target chunk length
        j = i
        text_parts: List[str] = []
        last_end_time = chunk_start_time
        while j < n:
            s_start = float(segments[j]["start"])
            s_dur = float(segments[j].get("duration", 0))
            s_end = s_start + s_dur
            if s_start - chunk_start_time > _TARGET_SEGMENT_SECONDS and len(text_parts) > 0:
                break
            text_parts.append(str(segments[j].get("text", "")).strip())
            last_end_time = s_end
            j += 1

        # Clamp the chunk's end to the video duration (so the LLM's relative
        # offsets can't push it past the file's last frame).
        if max_duration_seconds is not None:
            last_end_time = min(last_end_time, max_duration_seconds)

        chunk_text = " ".join(p for p in text_parts if p)
        chunk_duration = max(0.0, last_end_time - chunk_start_time)

        if chunk_duration > 0 and chunk_text:
            chunks.append({
                "text": chunk_text,
                "offset_seconds": chunk_start_time,
                "duration_seconds": chunk_duration,
                "chunk_idx": chunk_idx,
            })
            chunk_idx += 1

        # Slide forward with overlap: rewind by _OVERLAP_SECONDS worth of time
        # by stepping back through the segments until we cover the overlap.
        if j >= n:
            break
        # Advance i to just inside the overlap window
        target_next_start = max(chunk_start_time, last_end_time - _OVERLAP_SECONDS)
        new_i = j
        for k in range(j - 1, i, -1):
            if float(segments[k]["start"]) <= target_next_start:
                new_i = k
                break
        if new_i <= i:  # guarantee forward progress
            new_i = i + 1
        i = new_i

    return chunks


def _chunk_from_text(
    transcript: str,
    chars_per_second: float,
    max_duration_seconds: Optional[float],
) -> List[Dict[str, Any]]:
    """Char-offset chunking, calibrated by the probed video duration when
    possible. Any chunk whose offset would exceed *max_duration_seconds*
    is dropped.
    """
    chunks: List[Dict[str, Any]] = []
    start = 0
    chunk_idx = 0
    cps = max(1.0, chars_per_second)

    while start < len(transcript):
        end = min(start + _CHUNK_SIZE, len(transcript))
        chunk_text = transcript[start:end]
        offset_seconds = start / cps
        duration_seconds = (end - start) / cps

        # Stop once we've walked past the video end
        if max_duration_seconds is not None and offset_seconds >= max_duration_seconds:
            break

        # Clamp the chunk's apparent duration so the LLM can't pick past
        # the video end either.
        if max_duration_seconds is not None:
            duration_seconds = min(duration_seconds, max_duration_seconds - offset_seconds)

        chunks.append({
            "text": chunk_text,
            "offset_seconds": offset_seconds,
            "duration_seconds": duration_seconds,
            "chunk_idx": chunk_idx,
        })

        chunk_idx += 1
        start += _CHUNK_SIZE - _OVERLAP_SIZE  # slide with overlap

    return chunks


# Back-compat alias — preserves the old name in case anything imports it.
_chunk_transcript = _chunk_from_text


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
    transcript: str, top_n: int, max_duration_seconds: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """
    When LLM analysis fails entirely, divide the transcript into evenly-spaced
    60-second segments so the rest of the pipeline can still run.
    """
    if max_duration_seconds is not None and max_duration_seconds > 0:
        total_seconds = max_duration_seconds
    else:
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
        transcript        – full text transcript of the long video
        top_n_clips       – how many top clips to keep (default: 5)
        source_video_path – probed for actual video duration; propagated to clips
        timed_transcript  – preferred chunk source when available (YouTube captions)

    Output state keys:
        analyzed_segments – List[ClipObject] sorted by hook_score desc
        current_step
    """
    with node_stage(state, "analyze_video"):
        return _analyze_video_impl(state)


def _analyze_video_impl(state: LongToShortsState) -> Dict[str, Any]:
    transcript: str = state.get("transcript", "")
    top_n: int = state.get("top_n_clips", 5)
    source_path: str = state.get("source_video_path", "")
    timed_segments: Optional[List[Dict[str, Any]]] = state.get("timed_transcript")

    if not transcript.strip() and not timed_segments:
        logger.error("AnalyzeVideoNode: transcript is empty.")
        return {"analyzed_segments": [], "current_step": "analysis_failed",
                "error": "Empty transcript provided."}

    # --- 1. Probe the actual video duration — hard upper bound for clip timestamps
    video_duration = _probe_duration(source_path)
    if video_duration:
        logger.info(
            f"AnalyzeVideoNode: source video duration = {video_duration:.1f}s "
            f"(clip timestamps will be bounded by this)."
        )

    logger.info(
        f"AnalyzeVideoNode: analysing {len(transcript)} chars, "
        f"requesting top-{top_n} clips."
    )

    # --- 2. Pick a chunking strategy
    if timed_segments:
        chunks = _chunk_from_timed_segments(timed_segments, video_duration)
        logger.info(
            f"AnalyzeVideoNode: chunked from {len(timed_segments)} timed caption "
            f"segments → {len(chunks)} chunks (real timestamps)."
        )
    else:
        # Calibrate CPS from the probed duration when we can, so timestamp
        # estimates don't drift the way the constant did.
        if video_duration and len(transcript) > 0:
            calibrated_cps = len(transcript) / video_duration
            logger.info(
                f"AnalyzeVideoNode: calibrated chars-per-second = {calibrated_cps:.2f} "
                f"(transcript {len(transcript)} chars / video {video_duration:.1f}s); "
                f"default was {_CHARS_PER_SECOND}."
            )
        else:
            calibrated_cps = _CHARS_PER_SECOND
        chunks = _chunk_from_text(transcript, calibrated_cps, video_duration)
        logger.info(f"AnalyzeVideoNode: split into {len(chunks)} chunks.")

    if not chunks:
        logger.error("AnalyzeVideoNode: produced 0 chunks (transcript empty or all past video end).")
        return {"analyzed_segments": [], "current_step": "analysis_failed",
                "error": "No analysable transcript content within the video duration."}

    # --- 3. Collect raw scored segments from LLM
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
                segment = _parse_llm_json(
                    raw_text,
                    chunk["offset_seconds"],
                    chunk_duration_seconds=chunk["duration_seconds"],
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

    # --- 4. Fallback if LLM yielded nothing
    if not raw_segments:
        logger.warning("AnalyzeVideoNode: no segments from LLM; using synthetic fallback.")
        raw_segments = _make_synthetic_segments(transcript, top_n, video_duration)

    # --- 5. Filter out anything still past the video end (belt-and-braces:
    #        a chunk near the boundary plus the +/- MIN_SEGMENT padding in
    #        _parse_llm_json can still nudge a clip past `video_duration`).
    if video_duration:
        before = len(raw_segments)
        raw_segments = [
            s for s in raw_segments
            if s["start_time"] < video_duration
        ]
        # Clamp ends that exceed duration but whose start is still inside
        for s in raw_segments:
            if s["end_time"] > video_duration:
                s["end_time"] = video_duration
            # Drop anything reduced below the minimum useful clip length
        raw_segments = [
            s for s in raw_segments
            if s["end_time"] - s["start_time"] >= MIN_SEGMENT_SECONDS
        ]
        dropped = before - len(raw_segments)
        if dropped:
            logger.warning(
                f"AnalyzeVideoNode: filtered {dropped} segment(s) that fell "
                f"outside the video duration after LLM scoring."
            )

    if not raw_segments:
        logger.error(
            "AnalyzeVideoNode: no segments remain after duration filtering. "
            "The transcript and the downloaded video appear to cover different content."
        )
        return {"analyzed_segments": [], "current_step": "analysis_failed",
                "error": "No transcript content matched the downloaded video duration."}

    # --- 6. Sort and keep top-N
    raw_segments.sort(key=lambda s: s["hook_score"], reverse=True)
    top_segments = raw_segments[:top_n]

    # --- 7. Build ClipObject stubs
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
