"""
tools/llm/anthropic_provider.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Claude provider built on the official ``anthropic`` SDK.

Public surface
--------------
    AnthropicLLM         – BaseLLMProvider with native structured outputs

Configuration (environment variables)
--------------------------------------
    ANTHROPIC_API_KEY    – required (read by the SDK directly)
    CLAUDE_MODEL         – model id (default: "claude-sonnet-4-6")
    CLAUDE_MAX_TOKENS    – max output tokens (default: 4096)

Notes
-----
* Static instruction text is passed as a cached ``system`` block
  (``cache_control: ephemeral``) so the per-chunk / per-clip transcript — the only
  part that varies — is the sole uncached portion. Across the chunks of one video
  this serves the instruction prefix from cache (~0.1x cost).
* ``parse()`` uses ``client.messages.parse(output_format=...)`` for guaranteed
  schema-valid output, falling back to the prompt-engineered base implementation
  if the installed SDK predates ``messages.parse``.
"""

import os
from typing import Optional, Type, TypeVar

from pydantic import BaseModel

from tools.llm.base import BaseLLMProvider

T = TypeVar("T", bound=BaseModel)

_DEFAULT_MODEL = "claude-sonnet-4-6"
_DEFAULT_MAX_TOKENS = 4096


class AnthropicLLM(BaseLLMProvider):
    def __init__(self, model: Optional[str] = None, max_tokens: Optional[int] = None):
        import anthropic  # imported lazily so the package is only required when used

        self._anthropic = anthropic
        self._client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env
        self._model = model or os.getenv("CLAUDE_MODEL", _DEFAULT_MODEL)
        self._max_tokens = max_tokens or int(
            os.getenv("CLAUDE_MAX_TOKENS", str(_DEFAULT_MAX_TOKENS))
        )

    def _system_blocks(self, system: Optional[str]):
        if not system:
            return None
        return [
            {"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}
        ]

    def complete(self, prompt: str, *, system: Optional[str] = None) -> str:
        resp = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=self._system_blocks(system),
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(
            b.text for b in resp.content if getattr(b, "type", None) == "text"
        )

    def generate(self, prompt: str, **kwargs) -> str:
        return self.complete(prompt, system=kwargs.get("system"))

    def parse(self, prompt: str, schema: Type[T], *, system: Optional[str] = None) -> T:
        try:
            resp = self._client.messages.parse(
                model=self._model,
                max_tokens=self._max_tokens,
                system=self._system_blocks(system),
                messages=[{"role": "user", "content": prompt}],
                output_format=schema,
            )
        except AttributeError:
            # SDK too old for messages.parse — use the prompt-engineered fallback.
            return super().parse(prompt, schema, system=system)
        parsed = getattr(resp, "parsed_output", None)
        if parsed is None:
            return super().parse(prompt, schema, system=system)
        return parsed
