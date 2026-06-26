import json
import re
from abc import ABC, abstractmethod
from typing import Type, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


def _extract_json(text: str) -> str:
    """Best-effort: pull the first JSON object out of a model completion.

    Tolerates markdown fences and leading/trailing prose so the prompt-engineered
    fallback path (Ollama / HuggingFace, which lack native structured outputs)
    still validates cleanly against a Pydantic schema.
    """
    t = text.strip()
    if t.startswith("```"):
        t = t.split("```", 2)[1]
        if t.startswith("json"):
            t = t[4:]
        t = t.strip("`").strip()
    start, end = t.find("{"), t.rfind("}")
    if start != -1 and end != -1 and end > start:
        return t[start : end + 1]
    return t


class BaseLLMProvider(ABC):
    """
    Abstract Base Class for LLM Providers.

    Providers implement :meth:`generate` (and ideally :meth:`complete`). Structured
    output is available on every provider via :meth:`parse`: providers with native
    structured-output support override it, the rest get a prompt-engineered default
    that asks for JSON and validates it against the supplied Pydantic schema.
    """

    @abstractmethod
    def generate(self, prompt: str, **kwargs) -> str:
        """Generate text from a prompt."""
        ...

    def complete(self, prompt: str) -> str:
        """Single-turn raw completion. Used by the default :meth:`parse`.

        Defaults to :meth:`generate` for providers that don't override it.
        """
        return self.generate(prompt)

    def parse(self, prompt: str, schema: Type[T], *, system: str | None = None) -> T:
        """Return an instance of *schema* parsed from the model's response.

        Default (prompt-engineered) implementation: append the JSON schema to the
        prompt, complete, extract the JSON object, and validate. Providers with
        native structured outputs (e.g. Anthropic) override this.
        """
        schema_json = json.dumps(schema.model_json_schema())
        full = (
            (f"{system}\n\n" if system else "")
            + prompt
            + "\n\nReturn ONLY a JSON object matching this schema. "
            "No markdown fences, no commentary.\nSchema:\n"
            + schema_json
        )
        raw = self.complete(full)
        return schema.model_validate_json(_extract_json(raw))
