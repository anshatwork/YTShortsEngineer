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
import os
import re
import time
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from agents.long_to_shorts._logging_utils import node_stage
from agents.state import ClipObject, LongToShortsState
from core.audio_themes import AudioTheme
from tools.llm import get_llm

logger = logging.getLogger(__name__)


class ClipMeta(BaseModel):
    """Structured-output schema for per-clip metadata."""

    title: str
    summary: str
    hook_text: str
    hashtags: list[str]
    mood: AudioTheme

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_TITLE_MAX_CHARS: int    = 50
_HOOK_TEXT_MAX_CHARS: int = 55

# Bump to invalidate cached content-gen completions when the prompt changes.
# v2: migrated to Claude structured outputs (ClipMeta schema) + cached system prompt.
# v3: creator guidance now leads the user turn with a stronger no-verbatim frame.
_CONTENT_LLM_CACHE_VERSION: int = 3

# Background-music recommendation. Enabled by default; set RECOMMEND_MUSIC=0 to
# skip the asset-layer lookup entirely (e.g. when no music API keys/cache exist).
_RECOMMEND_MUSIC: bool = os.getenv("RECOMMEND_MUSIC", "1").lower() not in ("0", "false", "no")
_MOOD_OPTIONS: str = ", ".join(AudioTheme.list_values())

# Static instructions — passed as a cached system prompt. Only the transcript
# excerpt (the user turn) varies per clip.
_CONTENT_SYSTEM = """\
You are an expert YouTube Shorts copywriter who creates content that stops the scroll.
From the transcript excerpt the user provides, produce metadata for the clip:

- title: up to {max_title_chars} characters. Punchy, curiosity-driven, no filler.
  Power openers work well: "Why I...", "The truth about...", "How to...",
  "You're doing X wrong", "Nobody tells you this about...", "This changed everything".
  No emojis, no all-caps.
- summary: one sentence for the YouTube description that teases the value without
  giving everything away. A soft CTA is fine if it reads naturally.
- hook_text: up to {max_hook_chars} characters — a punchy on-screen overlay line, the
  first thing a viewer reads. Distinct from the title; a bold statement or question.
  e.g. "Wait until the end", "This blew my mind", "Most people get this wrong".
- hashtags: 5 keywords, no # symbol, lowercase, no spaces within a tag; balance search
  volume and specificity for this clip's topic.
- mood: the background-music mood that best fits the clip's emotional tone, one of
  {mood_options}. Guide: eerie=dark/suspenseful, mysterious=intriguing, peaceful=calm,
  energetic=upbeat/fast, professional=corporate/serious, contemplative=thoughtful,
  inspiring=motivational, neutral=generic."""

_CONTENT_USER = """\
Transcript excerpt:
\"\"\"
{transcript_excerpt}
\"\"\""""

# Pre-fill the static fields once so the cached system prefix stays byte-identical
# across every clip (only the transcript, in the user turn, varies).
_CONTENT_SYSTEM_FILLED = _CONTENT_SYSTEM.format(
    max_title_chars=_TITLE_MAX_CHARS,
    max_hook_chars=_HOOK_TEXT_MAX_CHARS,
    mood_options=_MOOD_OPTIONS,
)


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
    Extract TITLE, SUMMARY, HOOK, TAGS, and MOOD from the LLM response.

    Returns:
        {
            "title":     str,
            "summary":   str,
            "hook_text": str,
            "hashtags":  List[str],
            "mood":      str,   # validated AudioTheme value (defaults to "neutral")
        }

    Falls back gracefully if any field is missing.
    """
    title     = ""
    summary   = ""
    hook_text = ""
    tags_raw  = ""
    mood_raw  = ""

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
        elif re.match(r'^mood\s*:\s*', stripped, re.IGNORECASE):
            mood_raw = re.sub(r'^mood\s*:\s*', '', stripped, flags=re.IGNORECASE).strip()

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

    # Validate mood against the AudioTheme vocabulary; default to neutral.
    # Tolerate the LLM wrapping it in quotes/punctuation by taking the first word.
    mood_token = mood_raw.split()[0].strip(" .'\"") if mood_raw else ""
    mood_enum = AudioTheme.validate(mood_token)
    mood = mood_enum.value if mood_enum else AudioTheme.NEUTRAL.value

    return {
        "title":     title,
        "summary":   summary,
        "hook_text": hook_text,
        "hashtags":  hashtags,
        "mood":      mood,
    }


def _clipmeta_to_fields(meta: ClipMeta, clip_id: str) -> Dict[str, Any]:
    """Normalize a validated :class:`ClipMeta` into clip fields.

    Structured outputs guarantee the shape, so this only enforces the soft length
    caps, whitespace/hashtag normalization, and non-empty fallbacks that the regex
    parser used to do.
    """
    title = re.sub(r"\s+", " ", meta.title).strip()[:_TITLE_MAX_CHARS] or f"Clip {clip_id}"[:_TITLE_MAX_CHARS]
    hook_text = re.sub(r"\s+", " ", meta.hook_text).strip()[:_HOOK_TEXT_MAX_CHARS] or title[:_HOOK_TEXT_MAX_CHARS]
    summary = re.sub(r"\s+", " ", meta.summary).strip()

    hashtags: List[str] = []
    for tag in meta.hashtags:
        t = tag.strip().lstrip("#").lower().replace(" ", "")
        if t:
            hashtags.append(t)
    hashtags = hashtags[:5]

    mood = meta.mood.value if isinstance(meta.mood, AudioTheme) else str(meta.mood)
    return {
        "title":     title,
        "summary":   summary,
        "hook_text": hook_text,
        "hashtags":  hashtags,
        "mood":      mood,
    }


# ---------------------------------------------------------------------------
# Helper: recommend background music via the generalized asset layer
# ---------------------------------------------------------------------------

def _recommend_music(
    mood: str,
    title: str,
    hashtags: List[str],
    user_id: Optional[str],
) -> Dict[str, Any]:
    """Look up the latest background track matching *mood* and return clip fields.

    Uses the cache-first asset layer (:func:`tools.assets.retrieve`), so the
    first clip of a given mood may hit Pixabay/Freesound while same-mood clips
    reuse the warm cache. Never raises — on any failure (no API keys, network,
    empty pool) it returns empty fields and the clip simply gets no music.
    """
    try:
        from tools.assets import AssetQuery, AssetType, retrieve

        keywords = [w for w in re.split(r"\W+", title) if len(w) > 3][:3] + hashtags[:2]
        results = retrieve(
            AssetQuery(
                asset_type=AssetType.MUSIC,
                theme=mood,
                keywords=keywords,
                order="latest",
                user_id=user_id,
            ),
            k=1,
        )
        if not results or not results[0].local_path:
            logger.info("  ♪ no track found for mood '%s'", mood)
            return {}

        track = results[0]
        logger.info("  ♪ mood='%s' track='%s' (%s)", mood, track.title, track.source)
        return {
            "music_theme":       mood,
            "music_path":        track.local_path,
            "music_title":       track.title,
            "music_source":      track.source,
            "music_attribution": track.attribution,
        }
    except Exception as exc:  # noqa: BLE001 — music is best-effort, never fatal
        logger.warning("  ♪ music recommendation failed for mood '%s': %s", mood, exc)
        return {}


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
        llm = get_llm()
    except Exception as exc:
        logger.warning(f"ContentGenNode: LLM unavailable ({exc}). Using placeholder metadata.")
        llm_available = False

    from agents.long_to_shorts._prompt_utils import guidance_block
    guidance = guidance_block(state.get("user_context"))

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

            user_prompt = guidance + _CONTENT_USER.format(transcript_excerpt=excerpt)
            try:
                from agents.long_to_shorts._llm_cache import cached_llm_text

                def _invoke() -> str:
                    meta = llm.parse(user_prompt, ClipMeta, system=_CONTENT_SYSTEM_FILLED)
                    return meta.model_dump_json()

                raw = cached_llm_text(
                    user_prompt,
                    operation="content_llm",
                    version=_CONTENT_LLM_CACHE_VERSION,
                    invoke=_invoke,
                )
                content = _clipmeta_to_fields(ClipMeta.model_validate_json(raw), clip_id)

                updated["title"]     = content["title"]
                updated["summary"]   = content["summary"]
                updated["hook_text"] = content["hook_text"]
                updated["hashtags"]  = content["hashtags"]
                updated["music_theme"] = content["mood"]
                logger.info(
                    f"  ✓ {clip_id}: title='{updated['title']}' "
                    f"({len(updated['title'])} chars)  "
                    f"hook='{updated['hook_text']}'  "
                    f"tags={updated['hashtags']}  "
                    f"mood='{content['mood']}'"
                )

                # Recommend the latest background music for this clip's mood.
                if _RECOMMEND_MUSIC:
                    updated.update(
                        _recommend_music(
                            content["mood"],
                            content["title"],
                            content["hashtags"],
                            state.get("job_id"),
                        )
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
