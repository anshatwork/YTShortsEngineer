"""
agents/ingestion/_kg_prompts.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Static, versioned prompts + structured-output schemas for KG extraction.

Follows the repo's prompt conventions (see docs/claude/prompts.md):
* system prompts are static module constants (sent as an ephemeral cache block);
* extraction uses ``get_llm().parse(prompt, Schema, system=...)``;
* completions are memoized via ``cached_llm_text``-style caching keyed on a
  version — **bump the version constant when a prompt's meaning changes** or stale
  extractions will be served.
"""

from __future__ import annotations

from typing import List, Literal

from pydantic import BaseModel, Field

# Bump when _KG_ENTITY_SYSTEM or the extraction contract changes meaningfully.
KG_ENTITY_CACHE_VERSION = 1

EntityLabel = Literal[
    "Person", "Organization", "Location", "Product",
    "Topic", "Concept", "Event", "Activity",
]


class ExtractedEntity(BaseModel):
    """One entity mentioned in a transcript/OCR span."""

    name: str = Field(..., description="Canonical surface form, e.g. 'Kubernetes'.")
    label: EntityLabel = Field(..., description="Entity type from the allowed set.")


class EntityExtraction(BaseModel):
    """Structured output for the entity-extraction call."""

    entities: List[ExtractedEntity] = Field(default_factory=list)


_KG_ENTITY_SYSTEM = (
    "You extract named entities and key concepts from a transcript or on-screen "
    "text excerpt, to populate a knowledge graph. Return only entities that are "
    "genuinely present and salient. Use the most canonical name (e.g. 'Kubernetes' "
    "not 'k8s'; a person's full name if stated). Choose the single best label from: "
    "Person, Organization, Location, Product, Topic, Concept, Event, Activity. "
    "Do NOT include generic filler words. Prefer 5-12 high-signal entities over an "
    "exhaustive list. Never infer sensitive attributes about people."
)


def entity_prompt(text: str) -> str:
    """User prompt for entity extraction over one excerpt."""
    return (
        "Extract the salient entities and concepts from this excerpt:\n\n"
        f"\"\"\"\n{text.strip()}\n\"\"\""
    )


__all__ = [
    "KG_ENTITY_CACHE_VERSION",
    "EntityLabel",
    "ExtractedEntity",
    "EntityExtraction",
    "_KG_ENTITY_SYSTEM",
    "entity_prompt",
]
