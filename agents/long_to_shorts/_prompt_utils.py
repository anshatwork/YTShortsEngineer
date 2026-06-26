"""
agents/long_to_shorts/_prompt_utils.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Shared prompt helpers for the Long-to-Shorts LLM nodes.

The pipeline's prompts are otherwise fully static. ``guidance_block`` lets every
LLM node fold in optional creator-supplied context (e.g. "deep dive on AI
agents") so segment selection, titles, summaries, hooks, and thumbnails are
steered toward what the creator actually wants.

It is folded into the *user* prompt rather than the system prompt on purpose: the
LLM cache keys on ``hash(prompt_text)`` (see ``_llm_cache.cached_llm_text``), so
distinct guidance yields distinct cache entries automatically, and empty guidance
leaves the prompt byte-identical to before — existing cached completions stay
valid with no version bump.

The block frames the context as the *overall video's* angle that every clip
belongs to, and explicitly bans echoing it back as a title/summary/hook, so a
catchy guidance line steers all clips' copy instead of being parroted verbatim
onto whichever clip happens to mention the subject.
"""

from __future__ import annotations

from typing import Optional


def guidance_block(context: Optional[str]) -> str:
    """Return a creator-guidance block to fold into an LLM user prompt.

    Lead the user turn with this block (place it *before* the transcript excerpt)
    so the angle is weighted as standing context rather than read as source text
    to quote.

    Returns "" when no usable context is given, keeping the prompt byte-identical
    so the LLM cache stays valid.
    """
    if not context or not context.strip():
        return ""
    return (
        "The creator describes this whole video as:\n"
        f'"""\n{context.strip()}\n"""\n'
        "This is the overall angle/subject every clip belongs to. Make this "
        "clip's title, summary, and hook consistent with that angle while staying "
        "grounded in the specific transcript excerpt below. The description above "
        "is framing, NOT copy: never output it (or a close paraphrase of it) as "
        "the title, summary, or hook — write fresh lines for this clip.\n\n"
    )


__all__ = ["guidance_block"]
