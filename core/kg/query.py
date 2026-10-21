"""
core/kg/query.py
~~~~~~~~~~~~~~~~~
The KG query engine — the read surface every application consumes.

Three layers (design §9):

1. :func:`build_cypher` — compile a validated :class:`~core.kg.models.QuerySpec`
   into parameterized Cypher with an ``owner_id`` filter ALWAYS injected. This is
   the tenant-isolation guarantee (Neo4j has no RLS).
2. :func:`semantic_search` — hybrid retrieval: embed the query, run vector ANN +
   lexical full-text over the target label, fuse and de-dup. Vector finds
   *semantically similar*; graph/lexical supplies *exact + structured* matches.
3. :func:`interpret_query` — natural language → ``QuerySpec`` via
   ``get_llm().parse`` (constrained/validated, never raw Cypher generation).

Nothing here trusts a client-supplied ``owner_id``; callers pass the authenticated
user id and it is bound as a parameter.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from core.kg import repository
from core.kg.models import GraphNodeResult, QuerySpec, safe_identifier

logger = logging.getLogger(__name__)


def build_cypher(spec: QuerySpec, owner_id: str) -> Tuple[str, Dict[str, Any]]:
    """Compile *spec* to (cypher, params) with owner isolation always applied."""
    label = safe_identifier(spec.label)
    params: Dict[str, Any] = {"owner_id": owner_id, "top_k": int(spec.top_k)}
    where = ["n.owner_id = $owner_id"]

    for i, (k, v) in enumerate(spec.filters.items()):
        pk = f"f_{i}"
        where.append(f"n.{safe_identifier(k)} = ${pk}")
        params[pk] = v

    if spec.time_window and len(spec.time_window) == 2:
        params["tw0"], params["tw1"] = spec.time_window[0], spec.time_window[1]
        # interval overlap: node.start_s < tw1 AND node.end_s > tw0
        where.append("coalesce(n.start_s, n.t_s) < $tw1")
        where.append("coalesce(n.end_s, n.t_s) > $tw0")

    lines = [f"MATCH (n:{label})", "WHERE " + " AND ".join(where)]

    return_targets = []
    for i, step in enumerate(spec.traversals):
        edge = safe_identifier(step.edge)
        tgt = f"t{i}"
        tgt_label = f":{safe_identifier(step.target_label)}" if step.target_label else ""
        if step.direction == "out":
            lines.append(f"MATCH (n)-[:{edge}]->({tgt}{tgt_label})")
        elif step.direction == "in":
            lines.append(f"MATCH (n)<-[:{edge}]-({tgt}{tgt_label})")
        else:
            lines.append(f"MATCH (n)-[:{edge}]-({tgt}{tgt_label})")
        return_targets.append(tgt)

    ret = "RETURN labels(n) AS labels, properties(n) AS props"
    if return_targets:
        collected = ", ".join(
            f"collect(distinct properties({t})) AS {t}" for t in return_targets
        )
        ret += ", " + collected
    lines.append(ret)
    lines.append("LIMIT $top_k")
    return "\n".join(lines), params


def query(spec: QuerySpec, owner_id: str) -> List[Dict[str, Any]]:
    """Run a structured QuerySpec traversal; return raw rows (embeddings stripped)."""
    cypher, params = build_cypher(spec, owner_id)
    rows = driver_run_read(cypher, params)
    for r in rows:
        r.get("props", {}).pop("embedding", None)
    return rows


def driver_run_read(cypher: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
    from core.kg import driver
    return driver.run_read(cypher, params)


def _fuse(
    vector_hits: List[Dict[str, Any]],
    lexical_hits: List[Dict[str, Any]],
    *,
    top_k: int,
    w_vec: float = 0.6,
    w_lex: float = 0.4,
) -> List[GraphNodeResult]:
    """Reciprocal-style blend of vector + lexical hits, de-duped by node id."""
    scored: Dict[str, Dict[str, Any]] = {}

    def _fold(hits: List[Dict[str, Any]], weight: float) -> None:
        # normalize scores within each list so the two are comparable
        vals = [h.get("score") or 0.0 for h in hits]
        hi = max(vals) if vals else 1.0
        hi = hi or 1.0
        for h in hits:
            props = h.get("props", {})
            nid = props.get("id") or repr(sorted(props.items()))
            norm = (h.get("score") or 0.0) / hi
            entry = scored.setdefault(nid, {"labels": h.get("labels", []), "props": props, "score": 0.0})
            entry["score"] += weight * norm

    _fold(vector_hits, w_vec)
    _fold(lexical_hits, w_lex)
    results = [
        GraphNodeResult(labels=e["labels"], properties=e["props"], score=round(e["score"], 4))
        for e in scored.values()
    ]
    results.sort(key=lambda r: r.score or 0.0, reverse=True)
    return results[:top_k]


def semantic_search(
    label: str,
    text: str,
    owner_id: str,
    *,
    top_k: int = 20,
    modality: str = "text",
) -> List[GraphNodeResult]:
    """Hybrid vector + lexical search over one label, owner-scoped.

    *modality* selects which embedder to use for the query vector ("text" for
    text labels, "image" is reserved for cross-modal text→image where the query
    is still text but compared against image vectors in a shared CLIP space).
    Degrades gracefully: if embeddings are unavailable it falls back to lexical.
    """
    vector_hits: List[Dict[str, Any]] = []
    try:
        from tools.embeddings import get_embedder

        vec = get_embedder().embed_text([text])[0]
        vector_hits = repository.vector_search(label, vec, top_k=top_k, owner_id=owner_id)
    except Exception as exc:  # noqa: BLE001 — degrade to lexical-only
        logger.info("semantic_search vector path unavailable (%s); lexical only.", exc)

    lexical_hits: List[Dict[str, Any]] = []
    try:
        lexical_hits = repository.fulltext_search(label, text, top_k=top_k, owner_id=owner_id)
    except Exception as exc:  # noqa: BLE001 — label may have no fulltext index
        logger.debug("fulltext path unavailable for %s (%s).", label, exc)

    return _fuse(vector_hits, lexical_hits, top_k=top_k)


def neighborhood(
    label: str,
    key: Dict[str, Any],
    owner_id: str,
    *,
    edge: Optional[str] = None,
    direction: str = "both",
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """Owner-checked 1-hop neighborhood of an anchor node."""
    node = repository.get_node(label, key)
    if node is None or node.get("owner_id") not in (None, owner_id):
        return []
    return repository.neighbors(label, key, edge=edge, direction=direction, limit=limit)


_QUERY_SYSTEM = (
    "You translate a user's natural-language request about their media library "
    "into a structured graph query. Choose the single best anchor node label from "
    "the allowed set, exact-match filters, an optional free-text query for "
    "semantic search, and optional relationship traversals. Never invent labels or "
    "edge types outside the provided vocabulary."
)


def interpret_query(question: str) -> QuerySpec:
    """Parse a natural-language question into a validated QuerySpec via the LLM."""
    from tools.llm import get_llm

    prompt = (
        f"User request: {question}\n\n"
        "Produce a QuerySpec. Prefer text_query for 'find/show me' semantic asks; "
        "use filters for concrete attributes (e.g. media_type='screenshot')."
    )
    return get_llm().parse(prompt, QuerySpec, system=_QUERY_SYSTEM)


__all__ = [
    "build_cypher",
    "query",
    "semantic_search",
    "neighborhood",
    "interpret_query",
]
