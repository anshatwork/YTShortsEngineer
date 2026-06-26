"""
tools/llm/ollama.py
~~~~~~~~~~~~~~~~~~~~
Ollama LLM provider — runs models locally via the Ollama daemon.

Public surface
--------------
    OllamaLLM            – BaseLLMProvider implementation (plain generate())
    get_chat_model()     – returns a LangChain ChatOllama instance, ready for
                           use with .invoke([HumanMessage(...)]) in agent nodes

Configuration (environment variables, all optional)
----------------------------------------------------
    OLLAMA_MODEL         – model tag to pull/run  (default: "mistral")
    OLLAMA_BASE_URL      – Ollama server base URL  (default: "http://localhost:11434")
    OLLAMA_TEMPERATURE   – sampling temperature    (default: 0.3)
    OLLAMA_MAX_TOKENS    – max tokens to generate  (default: 512)

Usage in agent nodes
--------------------
    from tools.llm.ollama import get_chat_model

    llm = get_chat_model()
    response = llm.invoke([HumanMessage(content="...")])
    text = response.content
"""

import json
import logging
import os
import urllib.request
from typing import Optional, Tuple

from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage

from tools.llm.base import BaseLLMProvider

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Defaults (overridable via env)
# ---------------------------------------------------------------------------

_DEFAULT_MODEL: str       = "llama3.1:8b"
_DEFAULT_BASE_URL: str    = "http://127.0.0.1:11434"
_DEFAULT_TEMPERATURE: float = 0.3
_DEFAULT_MAX_TOKENS: int  = 512


def _model() -> str:
    return os.getenv("OLLAMA_MODEL", _DEFAULT_MODEL)

def _base_url() -> str:
    return os.getenv("OLLAMA_BASE_URL", _DEFAULT_BASE_URL)

def _temperature() -> float:
    return float(os.getenv("OLLAMA_TEMPERATURE", str(_DEFAULT_TEMPERATURE)))

def _max_tokens() -> int:
    return int(os.getenv("OLLAMA_MAX_TOKENS", str(_DEFAULT_MAX_TOKENS)))


# ---------------------------------------------------------------------------
# LangChain factory — used by agent nodes
# ---------------------------------------------------------------------------

def get_chat_model(
    model: Optional[str] = None,
    base_url: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
) -> ChatOllama:
    """
    Return a LangChain ChatOllama instance configured from env / kwargs.

    The returned object is fully compatible with `.invoke([HumanMessage(...)])`.

    Args:
        model:       Ollama model tag (e.g. "mistral", "llama3", "gemma2").
                     Overrides OLLAMA_MODEL env var.
        base_url:    Ollama server URL.  Overrides OLLAMA_BASE_URL env var.
        temperature: Sampling temperature (0–1).
        max_tokens:  Maximum tokens to generate.

    Raises:
        RuntimeError: If Ollama is unreachable (surfaces on first .invoke()).
    """
    resolved_model = model or _model()
    resolved_url   = base_url or _base_url()
    resolved_temp  = temperature if temperature is not None else _temperature()
    resolved_maxt  = max_tokens if max_tokens is not None else _max_tokens()

    logger.info(
        f"[OllamaLLM] model={resolved_model}  base_url={resolved_url}  "
        f"temperature={resolved_temp}  max_tokens={resolved_maxt}"
    )

    return ChatOllama(
        model=resolved_model,
        base_url=resolved_url,
        temperature=resolved_temp,
        num_predict=resolved_maxt,
    )


def check_available(
    base_url: Optional[str] = None, timeout: float = 3.0
) -> Tuple[bool, str]:
    """
    Probe the Ollama server before relying on it.

    `get_chat_model()` only *constructs* a ChatOllama; it never connects, so a
    dead daemon or an un-pulled model is only discovered on the first
    `.invoke()` — which then surfaces as a per-clip failure. This pre-flight
    check lets callers fail fast with a single clear message.

    Returns:
        (ok, detail). ok=False means the server is unreachable OR the configured
        model is not pulled; *detail* is a human-readable reason.
    """
    url = (base_url or _base_url()).rstrip("/") + "/api/tags"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            if resp.status != 200:
                return False, f"Ollama returned HTTP {resp.status}"
            tags = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        return False, f"Ollama unreachable at {url} ({exc})"

    names = {m.get("name", "") for m in tags.get("models", [])}
    want = _model()
    base_names = {n.split(":")[0] for n in names}
    if want not in names and want.split(":")[0] not in base_names:
        return False, f"model '{want}' not pulled (run: ollama pull {want})"
    return True, "ok"


# ---------------------------------------------------------------------------
# BaseLLMProvider implementation — plain text generate()
# ---------------------------------------------------------------------------

class OllamaLLM(BaseLLMProvider):
    """
    Ollama LLM provider implementing the BaseLLMProvider interface.

    Suitable when you want a simple `generate(prompt) → str` call
    rather than a full LangChain chain.
    """

    def __init__(
        self,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ):
        self._chat = get_chat_model(
            model=model,
            base_url=base_url,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    def generate(self, prompt: str, **kwargs) -> str:
        """
        Send *prompt* to Ollama and return the response text.

        Args:
            prompt: The full prompt string.
            **kwargs: Ignored (for interface compatibility).

        Returns:
            Generated text string.
        """
        response = self._chat.invoke([HumanMessage(content=prompt)])
        return response.content if hasattr(response, "content") else str(response)

    def complete(self, prompt: str) -> str:
        """Single-turn completion (alias of :meth:`generate`) for the parse() path."""
        return self.generate(prompt)
