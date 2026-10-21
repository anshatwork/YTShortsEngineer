"""OpenRouter provider using its OpenAI-compatible chat-completions API."""

from __future__ import annotations

import os
from typing import Optional, Tuple

import requests

from tools.llm.base import BaseLLMProvider

_DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
_DEFAULT_MODEL = "openrouter/free"


def _api_key() -> Optional[str]:
    return os.getenv("OPENROUTER_API_KEY") or os.getenv("GLM_API_KEY")


def check_available() -> Tuple[bool, str]:
    if not _api_key():
        return False, "OPENROUTER_API_KEY not set."
    return True, "ok"


class OpenRouterLLM(BaseLLMProvider):
    """Small, dependency-light OpenRouter adapter with safe error handling."""

    def __init__(self, model: Optional[str] = None, max_tokens: Optional[int] = None, api_key: Optional[str] = None) -> None:
        self._api_key = api_key or _api_key()
        if not self._api_key:
            raise ValueError("OPENROUTER_API_KEY is not set.")
        self._base_url = os.getenv("OPENROUTER_BASE_URL", _DEFAULT_BASE_URL).rstrip("/")
        self._model = model or os.getenv("OPENROUTER_MODEL", _DEFAULT_MODEL)
        self._max_tokens = max_tokens or int(os.getenv("OPENROUTER_MAX_TOKENS", "1024"))
        self._temperature = float(os.getenv("OPENROUTER_TEMPERATURE", "0.3"))
        self._timeout = float(os.getenv("OPENROUTER_TIMEOUT", "60"))

    def _chat(self, messages: list, **kwargs) -> str:
        payload = {
            "model": self._model,
            "messages": messages,
            "temperature": kwargs.get("temperature", self._temperature),
            "max_tokens": kwargs.get("max_tokens", self._max_tokens),
            "stream": False,
        }
        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}
        if os.getenv("OPENROUTER_APP_URL"):
            headers["HTTP-Referer"] = os.environ["OPENROUTER_APP_URL"]
        if os.getenv("OPENROUTER_APP_NAME"):
            headers["X-Title"] = os.environ["OPENROUTER_APP_NAME"]
        response = requests.post(f"{self._base_url}/chat/completions", json=payload, headers=headers, timeout=self._timeout)
        if response.status_code != 200:
            raise RuntimeError(f"OpenRouter API error {response.status_code}: {response.text[:300]}")
        try:
            return response.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("Unexpected OpenRouter response shape") from exc

    def complete(self, prompt: str, *, system: Optional[str] = None) -> str:
        messages = ([{"role": "system", "content": system}] if system else [])
        messages.append({"role": "user", "content": prompt})
        return self._chat(messages)

    def generate(self, prompt: str, **kwargs) -> str:
        return self.complete(prompt, system=kwargs.get("system"))


__all__ = ["OpenRouterLLM", "check_available"]
