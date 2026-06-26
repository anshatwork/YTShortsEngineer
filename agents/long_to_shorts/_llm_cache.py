"""
agents/long_to_shorts/_llm_cache.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Thin memoization wrapper for LLM calls in the pipeline.

Hook-scoring (per transcript chunk) and content-generation (per clip) are pure
functions of (model, prompt) — the prompt already embeds the transcript excerpt
and every tunable — so the raw completion can be cached. Re-processing the same
video, or resuming a failed job, then reuses the completions instead of paying
for the model again.

The cache stores the *raw* completion text; parsing (``_parse_llm_json`` /
``_parse_content_response``) stays outside the cache so prompt-independent parser
fixes take effect without a version bump.
"""

from __future__ import annotations

import os
from typing import Callable

from core.cache import get_cache, hash_text


def _model_id() -> str:
    """Best-effort model identifier for the cache key (chat backend agnostic).

    Keyed on the active provider's model so Claude and local completions never
    collide in the cache.
    """
    provider = os.getenv("LLM_PROVIDER", "claude").lower()
    if provider == "claude":
        return os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
    return (
        os.getenv("OLLAMA_MODEL")
        or os.getenv("LLM_MODEL_ID")
        or os.getenv("HF_MODEL_ID")
        or "default"
    )


def cached_llm_text(
    prompt_text: str,
    *,
    operation: str,
    version: int,
    invoke: Callable[[], str],
) -> str:
    """Return the (cached) raw completion for *prompt_text*.

    Args:
        operation: stable cache namespace, e.g. "analyze_llm" / "content_llm".
        version:   bump to invalidate when the prompt template / parsing contract
                   changes in a way that should discard old completions.
        invoke:    zero-arg callable that performs the real LLM call and returns
                   the completion string (may include retry logic).
    """
    inputs = {"model": _model_id(), "prompt": hash_text(prompt_text)}
    return get_cache().get_or_compute_json(
        operation, version, inputs, lambda: {"text": invoke()}
    )["text"]


__all__ = ["cached_llm_text"]
