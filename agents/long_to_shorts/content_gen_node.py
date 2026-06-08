"""
agents/long_to_shorts/content_gen_node.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
ContentGenNode – viral title, description, hook overlay, and hashtag generation
(Reduce phase).

For each successfully extracted clip in generated_clips:
  1.  Extracts the relevant transcript excerpt based on timestamp_range.
  2.  Prompts the LLM for a viral Title (≤50 chars), a 1-sentence description,
      a short hook overlay text (≤35 chars), and 5 SEO hashtags.
  3.  Enforces length limits via hard truncation as a safety net.
  4.  Returns the updated generated_clips list with title, summary, hook_text,
      and hashtags filled in.
"""

import logging
import re
import time
from typing import Any, Dict, List, Optional

from agents.long_to_shorts._logging_utils import node_stage
from agents.state import ClipObject, LongToShortsState
from tools.llm.ollama import check_available, get_chat_model

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_TITLE_MAX_CHARS: int    = 50
_HOOK_TEXT_MAX_CHARS: int = 55

_CONTENT_PROMPT = """\
You are an expert YouTube Shorts copywriter who creates content that stops the scroll.

Analyse the transcript excerpt and produce ALL FOUR of the following:

1. TITLE  — Maximum {max_title_chars} characters. Punchy, curiosity-driven, no filler.
   Use power openers like: "Why I...", "The truth about...", "How to...", "You're doing X wrong",
   "Nobody tells you this about...", "This changed everything".
   NO emojis. NO ALL-CAPS shouting.

2. SUMMARY — Exactly ONE sentence optimised for a YouTube Shorts description.
   Must tease the value without giving everything away. End with a soft CTA if natural.

3. HOOK — Maximum {max_hook_chars} characters. A punchy overlay line that appears ON SCREEN
   at the top of the video. Think of it as the first thing a viewer reads before they decide
   to watch. Different from the title — more like a bold statement or question.
   Examples: "Wait until the end", "This blew my mind", "Most people get this wrong",
   "The truth they don't want you to know".

4. TAGS — Exactly 5 hashtag keywords (no # symbol, lowercase, no spaces in each tag).
   Choose tags that balance search volume and specificity for this clip's topic.

Transcript excerpt:
\"\"\"
{transcript_excerpt}
\"\"\"

Respond with EXACTLY these four lines and nothing else:
TITLE: <your title here>
SUMMARY: <your one-sentence description here>
HOOK: <your overlay hook text here>
TAGS: tag1, tag2, tag3, tag4, tag5
"""


# ---------------------------------------------------------------------------
# Helper: get relevant transcript excerpt for a timestamp range
# ---------------------------------------------------------------------------

def _get_excerpt(
    transcript: str, start: float, end: float, chars_per_second: float = 10.5
) -> str:
    """Return the substring of *transcript* that corresponds to [start, end] seconds."""
    total_chars = len(transcript)
    start_char = max(0, int(start * chars_per_second))
    end_char = min(total_chars, int(end * chars_per_second))
    excerpt = transcript[start_char:end_char].strip()
    return excerpt or transcript[:600]


def _get_excerpt_timed(
    timed_transcript: List[Dict[str, Any]], start: float, end: float
) -> str:
    """Extract transcript text from timed caption segments overlapping [start, end].

    Prefers this over the character-heuristic approach when YouTube captions are
    available, because segment timestamps are exact.
    """
    words = []
    for seg in timed_transcript:
        seg_start = float(seg.get("start", 0))
        seg_end = seg_start + float(seg.get("duration", 0))
        if seg_end >= start and seg_start <= end:
            words.append(seg.get("text", "").strip())
    return " ".join(words).strip()


def _invoke_with_retry(llm: Any, messages: List[Any], max_attempts: int = 3) -> str:
    """Invoke the LLM with exponential backoff on transient failures."""
    last_exc: Optional[Exception] = None
    for attempt in range(max_attempts):
        try:
            response = llm.invoke(messages)
            return response.content if hasattr(response, "content") else str(response)
        except Exception as exc:
            last_exc = exc
            if attempt < max_attempts - 1:
                wait = 2 ** attempt  # 1s, 2s
                logger.warning(
                    f"LLM attempt {attempt + 1}/{max_attempts} failed ({exc}), "
                    f"retrying in {wait}s…"
                )
                time.sleep(wait)
    raise RuntimeError(f"LLM failed after {max_attempts} attempts") from last_exc


# ---------------------------------------------------------------------------
# Helper: parse LLM title/summary response
# ---------------------------------------------------------------------------

def _parse_content_response(raw: str) -> Dict[str, Any]:
    """
    Extract TITLE, SUMMARY, HOOK, and TAGS from the LLM response.

    Returns:
        {
            "title":     str,
            "summary":   str,
            "hook_text": str,
            "hashtags":  List[str],
        }

    Falls back gracefully if any field is missing.
    """
    title     = ""
    summary   = ""
    hook_text = ""
    tags_raw  = ""

    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        
        # More flexible parsing - handle variations in formatting
        if re.match(r'^title\s*:\s*', stripped, re.IGNORECASE):
            title = re.sub(r'^title\s*:\s*', '', stripped, flags=re.IGNORECASE).strip()
        elif re.match(r'^summary\s*:\s*', stripped, re.IGNORECASE):
            summary = re.sub(r'^summary\s*:\s*', '', stripped, flags=re.IGNORECASE).strip()
        elif re.match(r'^hook\s*:\s*', stripped, re.IGNORECASE):
            hook_text = re.sub(r'^hook\s*:\s*', '', stripped, flags=re.IGNORECASE).strip()
        elif re.match(r'^tags?\s*:\s*', stripped, re.IGNORECASE):
            tags_raw = re.sub(r'^tags?\s*:\s*', '', stripped, flags=re.IGNORECASE).strip()

    # Hard fallbacks
    if not title:
        title = raw.strip()[:_TITLE_MAX_CHARS]
    if not summary:
        summary = raw.strip()

    # Enforce length limits
    if len(title) > _TITLE_MAX_CHARS:
        title = title[:_TITLE_MAX_CHARS].rstrip()
    if len(hook_text) > _HOOK_TEXT_MAX_CHARS:
        hook_text = hook_text[:_HOOK_TEXT_MAX_CHARS].rstrip()

    # Normalise whitespace
    summary   = re.sub(r"\s+", " ", summary).strip()
    hook_text = re.sub(r"\s+", " ", hook_text).strip()

    # Parse hashtags: comma-separated, strip leading # if LLM added them
    hashtags: List[str] = []
    if tags_raw:
        for tag in tags_raw.split(","):
            tag = tag.strip().lstrip("#").lower().replace(" ", "")
            if tag:
                hashtags.append(tag)
    hashtags = hashtags[:5]  # cap at 5

    return {
        "title":     title,
        "summary":   summary,
        "hook_text": hook_text,
        "hashtags":  hashtags,
    }


# ---------------------------------------------------------------------------
# Node function
# ---------------------------------------------------------------------------

def content_gen_node(state: LongToShortsState) -> Dict[str, Any]:
    """
    LangGraph node: generate viral title, summary, hook overlay text, and
    hashtags for each clip.

    Input state keys used:
        generated_clips – List[ClipObject] from ClippingLogicNode
        transcript      – full transcript for excerpt extraction

    Output state keys:
        generated_clips – same list with title, summary, hook_text, hashtags filled in
        current_step
    """
    with node_stage(state, "content_gen"):
        return _content_gen_impl(state)


def _content_gen_impl(state: LongToShortsState) -> Dict[str, Any]:
    clips: List[ClipObject] = state.get("generated_clips", [])
    transcript: str = state.get("transcript", "")
    timed_transcript: Optional[List[Dict[str, Any]]] = state.get("timed_transcript")

    if not clips:
        logger.warning("ContentGenNode: no clips to generate content for.")
        return {
            "generated_clips": [],
            "current_step": "content_gen_skipped",
        }

    logger.info(f"ContentGenNode: generating metadata for {len(clips)} clip(s).")
    if timed_transcript:
        logger.info("ContentGenNode: using timed transcript for precise excerpt extraction.")

    llm_available = True
    llm = None
    try:
        llm = get_chat_model()
        ok, detail = check_available()
        if not ok:
            raise RuntimeError(detail)
    except Exception as exc:
        logger.warning(f"ContentGenNode: LLM unavailable ({exc}). Using placeholder metadata.")
        llm_available = False

    enriched_clips: List[ClipObject] = []

    for clip in clips:
        clip_id = clip["clip_id"]
        start, end = clip["timestamp_range"]

        updated: ClipObject = dict(clip)  # type: ignore[assignment]

        if llm_available and llm is not None:
            if timed_transcript:
                excerpt = _get_excerpt_timed(timed_transcript, start, end)
                if not excerpt:
                    excerpt = _get_excerpt(transcript, start, end)
            else:
                excerpt = _get_excerpt(transcript, start, end)

            prompt_text = _CONTENT_PROMPT.format(
                max_title_chars=_TITLE_MAX_CHARS,
                max_hook_chars=_HOOK_TEXT_MAX_CHARS,
                transcript_excerpt=excerpt,
            )
            try:
                from langchain_core.messages import HumanMessage
                raw = _invoke_with_retry(llm, [HumanMessage(content=prompt_text)])
                content = _parse_content_response(raw)

                # Post-parse guards: ensure required fields are never empty
                if not content["title"]:
                    content["title"] = f"Clip {clip_id}"[:_TITLE_MAX_CHARS]
                if not content["hook_text"]:
                    content["hook_text"] = content["title"][:_HOOK_TEXT_MAX_CHARS]

                updated["title"]     = content["title"]
                updated["summary"]   = content["summary"]
                updated["hook_text"] = content["hook_text"]
                updated["hashtags"]  = content["hashtags"]
                logger.info(
                    f"  ✓ {clip_id}: title='{updated['title']}' "
                    f"({len(updated['title'])} chars)  "
                    f"hook='{updated['hook_text']}'  "
                    f"tags={updated['hashtags']}"
                )
            except Exception as exc:
                logger.error(f"  ✗ {clip_id}: LLM call failed – {exc}. Using placeholder.")
                fallback_title = f"Clip {clip_id} ({start:.0f}s–{end:.0f}s)"[:_TITLE_MAX_CHARS]
                updated["title"]     = fallback_title
                updated["summary"]   = f"Highlight segment extracted from {start:.1f}s to {end:.1f}s."
                updated["hook_text"] = fallback_title[:_HOOK_TEXT_MAX_CHARS]
                updated["hashtags"]  = []
        else:
            fallback_title = f"Clip {clip_id} ({start:.0f}s–{end:.0f}s)"[:_TITLE_MAX_CHARS]
            updated["title"]     = fallback_title
            updated["summary"]   = f"Highlight segment extracted from {start:.1f}s to {end:.1f}s."
            updated["hook_text"] = fallback_title[:_HOOK_TEXT_MAX_CHARS]
            updated["hashtags"]  = []

        enriched_clips.append(updated)

    logger.info(f"ContentGenNode: enriched {len(enriched_clips)} clip(s).")
    return {
        "generated_clips": enriched_clips,
        "current_step": "content_generated",
    }
