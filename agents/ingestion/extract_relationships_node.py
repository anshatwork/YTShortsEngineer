"""
agents/ingestion/extract_relationships_node.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Stage 9 — turn extracted entities into typed relationships. Phase-1 builds the
reliable, deterministic structural edges:

  * ``MENTIONS``     TranscriptChunk → entity  (who/what a span talks about)
  * ``ABOUT_TOPIC``  MediaAsset      → Topic/Concept
  * ``APPEARS_IN``   Person/Org/Product → MediaAsset

This is also the seam where a future LLM relationship pass (EXPLAINS, RELATED_TO,
USES_PRODUCT with reasoning) plugs in without changing the graph_upsert contract.
Edges are emitted as ref-based dicts that ``graph_upsert`` resolves to node keys.
"""

from __future__ import annotations

from typing import Any, Dict, List

from agents.ingestion._logging_utils import node_stage

_TOPICAL = {"Topic", "Concept"}
_PRESENCE = {"Person", "Organization", "Product"}


def _extract_relationships_impl(state: Dict[str, Any]) -> Dict[str, Any]:
    entities: List[Dict[str, Any]] = state.get("entities") or []
    rels: List[Dict[str, Any]] = []
    seen: set = set()

    for ent in entities:
        ref = {"node": "entity", "label": ent["label"], "norm_name": ent["norm_name"]}

        # MENTIONS from the chunk that surfaced this entity
        if ent.get("chunk_index") is not None:
            key = ("MENTIONS", ent["chunk_index"], ent["label"], ent["norm_name"])
            if key not in seen:
                rels.append({
                    "type": "MENTIONS",
                    "from_ref": {"node": "chunk", "index": ent["chunk_index"]},
                    "to_ref": ref,
                })
                seen.add(key)

        # ABOUT_TOPIC asset → topic/concept
        if ent["label"] in _TOPICAL:
            key = ("ABOUT_TOPIC", ent["norm_name"])
            if key not in seen:
                rels.append({
                    "type": "ABOUT_TOPIC",
                    "from_ref": {"node": "asset"},
                    "to_ref": ref,
                })
                seen.add(key)

        # APPEARS_IN person/org/product → asset
        if ent["label"] in _PRESENCE:
            key = ("APPEARS_IN", ent["label"], ent["norm_name"])
            if key not in seen:
                rels.append({
                    "type": "APPEARS_IN",
                    "from_ref": ref,
                    "to_ref": {"node": "asset"},
                })
                seen.add(key)

    return {"relationships": rels}


def extract_relationships_node(state: Dict[str, Any]) -> Dict[str, Any]:
    with node_stage(state, "extract_relationships"):
        return _extract_relationships_impl(state)


__all__ = ["extract_relationships_node"]
