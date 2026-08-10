"""
agents/ingestion/extract_entities_node.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Stage 8 — pull salient entities/concepts out of each transcript chunk (and OCR
text) with the LLM, via ``get_llm().parse`` into a constrained schema. Each
extraction is memoized in the CAS keyed on (model, text hash, version) so
re-ingesting is free and prompt changes are handled by bumping the version
(``KG_ENTITY_CACHE_VERSION``). Degrade-not-fail: a chunk whose extraction errors
is skipped.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List

from agents.ingestion._kg_prompts import (
    KG_ENTITY_CACHE_VERSION,
    EntityExtraction,
    _KG_ENTITY_SYSTEM,
    entity_prompt,
)
from agents.ingestion._logging_utils import node_stage
from core.cache import get_cache, hash_text
from core.kg.resolution import normalize_name

logger = logging.getLogger(__name__)


def _model_id() -> str:
    provider = os.getenv("LLM_PROVIDER", "claude").lower()
    if provider == "claude":
        return os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
    return os.getenv("OLLAMA_MODEL") or os.getenv("GLM_MODEL") or "default"


def _max_chunks() -> int:
    try:
        return int(os.getenv("KG_MAX_ENTITY_CHUNKS", "40"))
    except ValueError:
        return 40


def _extract_one(text: str) -> EntityExtraction:
    """Cached per-excerpt entity extraction."""
    from tools.llm import get_llm

    inputs = {"model": _model_id(), "text": hash_text(text)}
    data = get_cache().get_or_compute_json(
        "kg_entities", KG_ENTITY_CACHE_VERSION, inputs,
        lambda: get_llm().parse(
            entity_prompt(text), EntityExtraction, system=_KG_ENTITY_SYSTEM
        ).model_dump(),
    )
    return EntityExtraction(**data)


def _extract_entities_impl(state: Dict[str, Any]) -> Dict[str, Any]:
    chunks: List[Dict[str, Any]] = state.get("transcript_chunks") or []
    # Include OCR text as pseudo-chunks (no chunk_index → asset-level mentions).
    ocr_texts = [b["text"] for b in (state.get("text_blocks") or []) if b.get("text")]

    entities: List[Dict[str, Any]] = []
    seen: set = set()

    for chunk in chunks[: _max_chunks()]:
        text = (chunk.get("text") or "").strip()
        if len(text) < 8:
            continue
        try:
            result = _extract_one(text)
        except Exception as exc:  # noqa: BLE001 — skip this chunk
            logger.info("entity extraction skipped for a chunk (%s).", exc)
            continue
        for ent in result.entities:
            norm = normalize_name(ent.name)
            if not norm:
                continue
            entities.append({
                "label": ent.label, "name": ent.name, "norm_name": norm,
                "chunk_index": chunk["chunk_index"],
            })
            seen.add((ent.label, norm))

    # A light OCR pass (aggregate, asset-level) so on-screen brands/terms surface.
    if ocr_texts:
        joined = " \n ".join(ocr_texts)[:4000]
        try:
            for ent in _extract_one(joined).entities:
                norm = normalize_name(ent.name)
                if norm and (ent.label, norm) not in seen:
                    entities.append({
                        "label": ent.label, "name": ent.name, "norm_name": norm,
                        "chunk_index": None,
                    })
                    seen.add((ent.label, norm))
        except Exception as exc:  # noqa: BLE001
            logger.debug("OCR entity pass skipped (%s).", exc)

    return {"entities": entities}


def extract_entities_node(state: Dict[str, Any]) -> Dict[str, Any]:
    with node_stage(state, "extract_entities"):
        return _extract_entities_impl(state)


__all__ = ["extract_entities_node"]
