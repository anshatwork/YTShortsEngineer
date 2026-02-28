"""
agents/long_to_shorts/content_gen_node.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
ContentGenNode – viral title and description generation (Reduce phase).

For each successfully extracted clip in generated_clips:
  1.  Extracts the relevant transcript excerpt based on timestamp_range.
  2.  Prompts the LLM for a viral Title (≤50 chars) and a
      1-sentence YouTube Shorts description.
  3.  Enforces the 50-char title limit via hard truncation as a safety net.
  4.  Returns the updated generated_clips list with title and summary filled in.
"""

import logging
import re
from typing import Any, Dict, List

from agents.state import ClipObject, LongToShortsState
from tools.llm.ollama import get_chat_model

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_TITLE_MAX_CHARS: int = 50

_CONTENT_PROMPT = """\
You are a viral YouTube Shorts copywriter.

Write a compelling title and a one-sentence description for a short video clip.

Rules:
- Title: maximum {max_chars} characters, punchy, no clickbait emojis
- Summary: exactly ONE sentence, optimised for YouTube Shorts descriptions

Transcript excerpt:
\"\"\"
{transcript_excerpt}
\"\"\"

Respond with ONLY these two lines (no extra text or labels):
TITLE: <your title here>
SUMMARY: <your one-sentence description here>
"""


# ---------------------------------------------------------------------------
# Helper: get relevant transcript excerpt for a timestamp range
# ---------------------------------------------------------------------------

def _get_excerpt(
    transcript: str, start: float, end: float, chars_per_second: float = 10.5
) -> str:
    """Return the substring of *transcript* that corresponds to [start, end] seconds."""
    total_chars = len(transcript)
    # Estimate character positions from timing
    start_char = max(0, int(start * chars_per_second))
    end_char = min(total_chars, int(end * chars_per_second))
    excerpt = transcript[start_char:end_char].strip()
    # Fallback: return up to 600 chars if estimation produces nothing
    return excerpt or transcript[:600]


# ---------------------------------------------------------------------------
# Helper: parse LLM title/summary response
# ---------------------------------------------------------------------------

def _parse_content_response(raw: str) -> Dict[str, str]:
    """
    Extract TITLE and SUMMARY from the LLM response.
    Returns {"title": str, "summary": str}.
    Falls back to truncated raw text if parsing fails.
    """
    title = ""
    summary = ""

    for line in raw.splitlines():
        line = line.strip()
        if line.upper().startswith("TITLE:"):
            title = line[6:].strip()
        elif line.upper().startswith("SUMMARY:"):
            summary = line[8:].strip()

    # Hard fallback: if parsing failed, use first 50 chars as title
    if not title:
        title = raw.strip()[:_TITLE_MAX_CHARS]
    if not summary:
        # Use the whole raw text as summary (it will be a single LLM sentence)
        summary = raw.strip()

    # Enforce title length limit
    if len(title) > _TITLE_MAX_CHARS:
        title = title[:_TITLE_MAX_CHARS].rstrip()

    # Strip trailing whitespace from summary
    summary = re.sub(r"\s+", " ", summary).strip()

    return {"title": title, "summary": summary}


# ---------------------------------------------------------------------------
# Node function
# ---------------------------------------------------------------------------

def content_gen_node(state: LongToShortsState) -> Dict[str, Any]:
    """
    LangGraph node: generate viral title + 1-sentence summary for each clip.

    Input state keys used:
        generated_clips – List[ClipObject] from ClippingLogicNode
        transcript      – full transcript for excerpt extraction

    Output state keys:
        generated_clips – same list with title and summary filled in
        current_step
    """
    clips: List[ClipObject] = state.get("generated_clips", [])
    transcript: str = state.get("transcript", "")

    if not clips:
        logger.warning("ContentGenNode: no clips to generate content for.")
        return {
            "generated_clips": [],
            "current_step": "content_gen_skipped",
        }

    logger.info(f"ContentGenNode: generating titles + summaries for {len(clips)} clip(s).")

    # Try to initialize LLM (Ollama); fall back to placeholder text if unavailable
    llm_available = True
    llm = None
    try:
        llm = get_chat_model()
    except Exception as exc:
        logger.warning(f"ContentGenNode: LLM unavailable ({exc}). Using placeholder metadata.")
        llm_available = False

    enriched_clips: List[ClipObject] = []

    for clip in clips:
        clip_id = clip["clip_id"]
        start, end = clip["timestamp_range"]

        updated: ClipObject = dict(clip)  # type: ignore[assignment]

        if llm_available and llm is not None:
            excerpt = _get_excerpt(transcript, start, end)
            prompt_text = _CONTENT_PROMPT.format(
                max_chars=_TITLE_MAX_CHARS,
                transcript_excerpt=excerpt,
            )
            try:
                from langchain_core.messages import HumanMessage
                response = llm.invoke([HumanMessage(content=prompt_text)])
                raw = response.content if hasattr(response, "content") else str(response)
                content = _parse_content_response(raw)
                updated["title"] = content["title"]
                updated["summary"] = content["summary"]
                logger.info(
                    f"  ✓ {clip_id}: title='{updated['title']}' "
                    f"({len(updated['title'])} chars)"
                )
            except Exception as exc:
                logger.error(f"  ✗ {clip_id}: LLM call failed – {exc}. Using placeholder.")
                updated["title"] = f"Clip {clip_id} ({start:.0f}s–{end:.0f}s)"[:_TITLE_MAX_CHARS]
                updated["summary"] = (
                    f"Highlight segment extracted from {start:.1f}s to {end:.1f}s."
                )
        else:
            # Placeholder metadata when LLM is not available
            updated["title"] = f"Clip {clip_id} ({start:.0f}s–{end:.0f}s)"[:_TITLE_MAX_CHARS]
            updated["summary"] = (
                f"Highlight segment extracted from {start:.1f}s to {end:.1f}s."
            )

        enriched_clips.append(updated)

    logger.info(f"ContentGenNode: enriched {len(enriched_clips)} clip(s).")
    return {
        "generated_clips": enriched_clips,
        "current_step": "content_generated",
    }
