"""
tools/llm/credentials.py
~~~~~~~~~~~~~~~~~~~~~~~~~~
Per-job LLM credential resolution (BYOK — bring your own key).

The pipeline's default inference path is our GPU Ollama box. When a user has
supplied their own provider API key, that job should use *their* key/provider and
bypass our GPU entirely — without threading an ``llm`` argument through every
node. We propagate it the same way job/node logging context is propagated (see
``core.logging_config``): a contextvar bound for the duration of one job's worker
thread.

    from tools.llm.credentials import LLMCredential, llm_credential_context

    with llm_credential_context(LLMCredential(provider="claude", api_key=key)):
        long_to_shorts_app.invoke(state)   # get_llm() inside picks up the cred

``tools.llm.get_llm()`` reads ``current_llm_credential`` and, when set, builds the
user's provider with their key and does **not** fall back to our Ollama GPU.
"""

from __future__ import annotations

import contextvars
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator, Optional

# Providers a user may bring their own key for. Only providers with a
# BaseLLMProvider implementation that accepts an api_key belong here. Extend as
# more providers gain BYOK support (see tools.llm._construct).
BYOK_PROVIDERS = ("claude",)


def redact_key(value: Optional[str]) -> str:
    """Mask a secret for safe logging: keep only a short fingerprint."""
    if not value:
        return "<none>"
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}…{value[-2:]}"


@dataclass(frozen=True)
class LLMCredential:
    """A user-supplied LLM provider + key for one job. Never logged raw."""

    provider: str
    api_key: str
    model: Optional[str] = None

    def __post_init__(self) -> None:
        if self.provider not in BYOK_PROVIDERS:
            raise ValueError(
                f"Unsupported BYOK provider '{self.provider}' "
                f"(supported: {', '.join(BYOK_PROVIDERS)})"
            )
        if not self.api_key:
            raise ValueError("LLMCredential.api_key must not be empty")

    def __repr__(self) -> str:  # never leak the key in logs / tracebacks
        return (
            f"LLMCredential(provider={self.provider!r}, model={self.model!r}, "
            f"api_key={redact_key(self.api_key)})"
        )


current_llm_credential: contextvars.ContextVar[Optional[LLMCredential]] = (
    contextvars.ContextVar("current_llm_credential", default=None)
)


@contextmanager
def llm_credential_context(cred: Optional[LLMCredential]) -> Iterator[None]:
    """Bind *cred* (or None) to the current thread for the duration of a job."""
    token = current_llm_credential.set(cred)
    try:
        yield
    finally:
        current_llm_credential.reset(token)


__all__ = [
    "LLMCredential",
    "BYOK_PROVIDERS",
    "current_llm_credential",
    "llm_credential_context",
    "redact_key",
]
