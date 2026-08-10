"""
agents/ingestion/resolve_entities_node.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Stage 10 — entity resolution (design §6). Two parts:

1. **Exact, in-run dedup:** collapse entities that share ``(label, norm_name)`` so
   one asset contributes one node per entity (and MERGE-on-``(owner_id, norm_name)``
   in ``graph_upsert`` then collapses across assets — 500 mentions → 1 node).
2. **Embed entity names** so entities are semantically searchable AND so the
   background fuzzy-merge pass (``core.kg.resolution.resolve_label``, e.g. "K8s" →
   "Kubernetes") has vectors to compare. The cross-asset fuzzy merge itself runs
   out-of-band, not on the ingestion hot path.

The unique ``entities`` list is preserved (with per-entity ``chunk_index`` info
kept via the relationships built in stage 9).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from agents.ingestion._logging_utils import node_stage

logger = logging.getLogger(__name__)


def _resolve_entities_impl(state: Dict[str, Any]) -> Dict[str, Any]:
    entities: List[Dict[str, Any]] = state.get("entities") or []

    # Exact in-run dedup by (label, norm_name); keep the first surface form.
    unique: Dict[tuple, Dict[str, Any]] = {}
    for ent in entities:
        k = (ent["label"], ent["norm_name"])
        unique.setdefault(k, {
            "label": ent["label"], "name": ent["name"], "norm_name": ent["norm_name"],
        })

    unique_list = list(unique.values())

    # Embed the canonical names (text) so entity nodes are searchable + resolvable.
    if unique_list:
        try:
            from tools.embeddings import embed_text_cached

            vecs = embed_text_cached([e["name"] for e in unique_list])
            for e, v in zip(unique_list, vecs):
                e["embedding"] = v
        except Exception as exc:  # noqa: BLE001 — entities still upserted un-vectored
            logger.info("entity embedding degraded (%s).", exc)

    return {"entities": unique_list}


def resolve_entities_node(state: Dict[str, Any]) -> Dict[str, Any]:
    with node_stage(state, "resolve_entities"):
        return _resolve_entities_impl(state)


__all__ = ["resolve_entities_node"]
