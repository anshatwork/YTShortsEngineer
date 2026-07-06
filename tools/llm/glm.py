"""
tools/llm/glm.py
~~~~~~~~~~~~~~~~~
GLM provider — Z.ai's GLM models via their OpenAI-compatible REST API.

Z.ai exposes free models (``glm-4.5-flash``, ``glm-4.7-flash``) behind an
OpenAI-compatible chat-completions endpoint, so a free account key is enough to
run the whole pipeline at $0 per token. Implemented with ``requests`` (already a
dependency) — no OpenAI/zhipuai SDK required.

Public surface
--------------
    GLMLLM               – BaseLLMProvider implementation (generate/complete/parse)
    check_available()    – pre-flight: is a key configured?

Configuration (environment variables, all optional except the key)
------------------------------------------------------------------
    GLM_API_KEY          – Z.ai API key  (aliases: ZAI_API_KEY, ZHIPUAI_API_KEY)
    GLM_MODEL            – model id        (default: "glm-4.5-flash")
    GLM_BASE_URL         – API base url    (default: "https://api.z.ai/api/paas/v4")
    GLM_TEMPERATURE      – sampling temp   (default: 0.3)
    GLM_MAX_TOKENS       – max output toks (default: 1024)
    GLM_TIMEOUT          – HTTP timeout s  (default: 60)

Usage
-----
    LLM_PROVIDER=glm GLM_API_KEY=<key> ENABLE_LLM_FALLBACK=false
    # then any get_llm() in the pipeline routes through GLM.
"""

from __future__ import annotations

import logging
import os
from typing import Optional, Tuple

import requests

from tools.llm.base import BaseLLMProvider

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Defaults (overridable via env)
# ---------------------------------------------------------------------------

_DEFAULT_MODEL: str = "glm-4.5-flash"
_DEFAULT_BASE_URL: str = "https://api.z.ai/api/paas/v4"
_DEFAULT_TEMPERATURE: float = 0.3
_DEFAULT_MAX_TOKENS: int = 1024
_DEFAULT_TIMEOUT: float = 60.0


def _api_key() -> Optional[str]:
    # Accept a few common env names so an existing Z.ai/Zhipu key just works.
    return (
        os.getenv("GLM_API_KEY")
        or os.getenv("ZAI_API_KEY")
        or os.getenv("ZHIPUAI_API_KEY")
    )


def _model() -> str:
    return os.getenv("GLM_MODEL", _DEFAULT_MODEL)


def _base_url() -> str:
    return os.getenv("GLM_BASE_URL", _DEFAULT_BASE_URL)


def _temperature() -> float:
    return float(os.getenv("GLM_TEMPERATURE", str(_DEFAULT_TEMPERATURE)))


def _max_tokens() -> int:
    return int(os.getenv("GLM_MAX_TOKENS", str(_DEFAULT_MAX_TOKENS)))


def _timeout() -> float:
    return float(os.getenv("GLM_TIMEOUT", str(_DEFAULT_TIMEOUT)))


def check_available() -> Tuple[bool, str]:
    """Pre-flight check: is a GLM key configured?

    Mirrors ``ollama.check_available`` so callers can fail fast with one clear
    message instead of a per-clip API error. We only verify configuration (not a
    live request) to avoid spending a call just to probe.
    """
    if not _api_key():
        return False, "GLM_API_KEY not set (get a free key at https://z.ai)."
    return True, "ok"


class GLMLLM(BaseLLMProvider):
    """GLM provider over Z.ai's OpenAI-compatible chat-completions endpoint."""

    def __init__(
        self,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        api_key: Optional[str] = None,
    ):
        # api_key arg (BYOK) wins; otherwise fall back to env. Same shape as
        # AnthropicLLM so credential wiring works identically.
        self._api_key = api_key or _api_key()
        if not self._api_key:
            raise ValueError(
                "GLM_API_KEY is not set — cannot construct GLMLLM. "
                "Get a free key at https://z.ai and set GLM_API_KEY."
            )
        self._model = model or _model()
        self._max_tokens = max_tokens or _max_tokens()
        self._base_url = _base_url().rstrip("/")
        self._temperature = _temperature()
        self._timeout = _timeout()

    # -- HTTP ------------------------------------------------------------------

    def _chat(self, messages: list, **kwargs) -> str:
        url = f"{self._base_url}/chat/completions"
        payload = {
            "model": self._model,
            "messages": messages,
            "temperature": kwargs.get("temperature", self._temperature),
            "max_tokens": kwargs.get("max_tokens", self._max_tokens),
            "stream": False,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        resp = requests.post(url, json=payload, headers=headers, timeout=self._timeout)
        if resp.status_code != 200:
            # Never include the key; cap the body so a verbose error can't dump secrets.
            raise RuntimeError(
                f"GLM API error {resp.status_code}: {resp.text[:300]}"
            )
        data = resp.json()
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"Unexpected GLM response shape: {str(data)[:300]}") from exc

    # -- BaseLLMProvider interface --------------------------------------------

    def complete(self, prompt: str, *, system: Optional[str] = None) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return self._chat(messages)

    def generate(self, prompt: str, **kwargs) -> str:
        return self.complete(prompt, system=kwargs.get("system"))

    # parse() inherits the prompt-engineered JSON implementation from
    # BaseLLMProvider (same path Ollama uses) — robust and SDK-free.


__all__ = ["GLMLLM", "check_available"]
