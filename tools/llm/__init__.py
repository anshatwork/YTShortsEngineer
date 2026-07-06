"""
tools/llm
~~~~~~~~~
Provider-agnostic LLM factory.

    from tools.llm import get_llm

    llm = get_llm()
    text = llm.generate("...")                       # free text
    obj  = llm.parse("...", MySchema, system="...")   # structured output

Provider selection (env ``LLM_PROVIDER``): ``claude`` (default) | ``ollama`` | ``hf``.
When the primary is Claude and ``ENABLE_LLM_FALLBACK`` is truthy, calls that fail
(API error, missing key, network) transparently fall back to the local Ollama model
— preserving the existing offline path. Provider classes are imported lazily so the
``anthropic`` package is only required when Claude is actually selected.
"""

import logging
import os
from typing import Optional, Type, TypeVar

from pydantic import BaseModel

from tools.llm.base import BaseLLMProvider

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

__all__ = ["get_llm", "FallbackLLM"]


def _truthy(name: str, default: str = "true") -> bool:
    return os.getenv(name, default).lower() not in ("0", "false", "no", "")


def _construct(provider: str, credential=None) -> BaseLLMProvider:
    """Build a provider. When *credential* (an LLMCredential) is given, construct
    the user's provider with their own API key (BYOK) instead of our env key."""
    if provider == "claude":
        from tools.llm.anthropic_provider import AnthropicLLM

        if credential is not None:
            return AnthropicLLM(model=credential.model, api_key=credential.api_key)
        return AnthropicLLM()
    if provider == "ollama":
        from tools.llm.ollama import OllamaLLM

        return OllamaLLM()
    if provider == "glm":
        from tools.llm.glm import GLMLLM

        if credential is not None:
            return GLMLLM(model=credential.model, api_key=credential.api_key)
        return GLMLLM()
    if provider == "hf":
        from tools.llm.huggingface import HuggingFaceLLM

        return HuggingFaceLLM()
    raise ValueError(
        f"Unknown LLM_PROVIDER '{provider}' (use claude | ollama | glm | hf)"
    )


class FallbackLLM(BaseLLMProvider):
    """Wraps a primary provider and lazily delegates to Ollama on any failure."""

    def __init__(self, primary: BaseLLMProvider):
        self._primary = primary
        self._fallback: Optional[BaseLLMProvider] = None

    def _fb(self) -> BaseLLMProvider:
        if self._fallback is None:
            self._fallback = _construct("ollama")
        return self._fallback

    def _with_fallback(self, op: str, primary_call, fallback_call):
        """Run *primary_call*; on any failure log the full traceback and try the
        Ollama *fallback_call*. If the fallback ALSO fails, log that distinctly
        (otherwise it would be invisible) and re-raise so the caller sees a real
        error instead of a silent wrong result."""
        primary_name = type(self._primary).__name__
        try:
            return primary_call()
        except Exception as exc:  # noqa: BLE001 — fall back to local model
            logger.warning(
                "Primary LLM (%s) failed during %s (%s); falling back to Ollama.",
                primary_name, op, exc, exc_info=True,
            )
            try:
                return fallback_call()
            except Exception:
                logger.error(
                    "Ollama fallback ALSO failed during %s (after primary %s failed).",
                    op, primary_name, exc_info=True,
                )
                raise

    def generate(self, prompt: str, **kwargs) -> str:
        return self._with_fallback(
            "generate",
            lambda: self._primary.generate(prompt, **kwargs),
            lambda: self._fb().generate(prompt),
        )

    def complete(self, prompt: str) -> str:
        return self._with_fallback(
            "complete",
            lambda: self._primary.complete(prompt),
            lambda: self._fb().complete(prompt),
        )

    def parse(self, prompt: str, schema: Type[T], *, system: Optional[str] = None) -> T:
        return self._with_fallback(
            "parse",
            lambda: self._primary.parse(prompt, schema, system=system),
            lambda: self._fb().parse(prompt, schema, system=system),
        )


def get_llm() -> BaseLLMProvider:
    """Return the LLM provider for the current job.

    If a BYOK credential is bound to this thread (see
    ``tools.llm.credentials.llm_credential_context``), build the user's provider
    with their key and do **not** fall back to our Ollama GPU — a user's bad key
    must never silently spend our compute. Otherwise use the env-configured
    provider (the GPU Ollama default in production), with the usual fallback chain.
    """
    from tools.llm.credentials import current_llm_credential, redact_key

    cred = current_llm_credential.get()
    if cred is not None:
        logger.info(
            "BYOK LLM in use — provider=%s key=%s (our GPU bypassed)",
            cred.provider, redact_key(cred.api_key),
        )
        return _construct(cred.provider, credential=cred)

    provider = os.getenv("LLM_PROVIDER", "claude").lower()
    fallback_enabled = _truthy("ENABLE_LLM_FALLBACK")

    try:
        primary = _construct(provider)
    except Exception as exc:  # construction failed (e.g. missing ANTHROPIC_API_KEY)
        if fallback_enabled and provider != "ollama":
            logger.warning(
                "Could not construct '%s' provider (%s); using Ollama.", provider, exc
            )
            return _construct("ollama")
        raise

    if provider == "claude" and fallback_enabled:
        return FallbackLLM(primary)
    return primary
