"""
core/kg/repository.py
~~~~~~~~~~~~~~~~~~~~~~
Parameterized Cypher for reading and writing the graph — the ONLY module that
builds Cypher strings for node/edge CRUD.

Safety contract (Neo4j has no RLS, so this is load-bearing):

* Labels, relationship types and property *keys* are validated as safe
  identifiers (:func:`core.kg.models.safe_identifier`) before being interpolated
  into a query — everything else is passed as a **parameter**, never concatenated.
* Every node write folds in ``owner_id`` (from ``NodeSpec``) and every read that
  is user-facing is expected to include an ``owner_id`` filter (the query engine
  in :mod:`core.kg.query` enforces this).

Idempotency: writes use ``MERGE`` on the node's stable key props, so replaying an
ingestion converges instead of duplicating (design §6).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from core.kg import driver
from core.kg.models import EdgeSpec, NodeSpec, safe_identifier
from core.kg.schema import fulltext_index_name, vector_index_name

logger = logging.getLogger(__name__)


def _key_pattern(key: Dict[str, Any], param: str = "key") -> str:
    """Return an inline Cypher map like ``{k1: $key.k1, k2: $key.k2}``.

    Property keys are validated (identifier-safe); values are read from the map
    parameter *param* so they are never interpolated.
    """
    parts = [f"{safe_identifier(k)}: ${param}.{safe_identifier(k)}" for k in key]
    return "{" + ", ".join(parts) + "}"


def _node_merge_query(spec: NodeSpec) -> str:
    label = safe_identifier(spec.label)
    key_map = _key_pattern(spec.key_props, "key")
    lines = [
        f"MERGE (n:{label} {key_map})",
        "ON CREATE SET n.id = coalesce($props.id, randomUUID()), n.created_at = timestamp()",
        "SET n += $props, n.updated_at = timestamp()",
    ]
    if spec.embedding is not None:
        field = safe_identifier(spec.embedding_field)
        lines.append(f"SET n.{field} = $embedding")
    lines.append("RETURN n.id AS id")
    return "\n".join(lines)


def _node_params(spec: NodeSpec) -> Dict[str, Any]:
    params: Dict[str, Any] = {"key": spec.key_props, "props": spec.merged_props()}
    if spec.embedding is not None:
        params["embedding"] = list(spec.embedding)
    return params


def upsert_node(spec: NodeSpec) -> Optional[str]:
    """MERGE a single node; return its id."""
    rows = driver.run_write(_node_merge_query(spec), _node_params(spec))
    return rows[0]["id"] if rows else None


def upsert_nodes(specs: List[NodeSpec]) -> int:
    """MERGE many nodes in ONE write transaction (atomic per asset). Returns count."""
    if not specs:
        return 0
    with driver.session() as sess:
        def _work(tx):
            n = 0
            for spec in specs:
                tx.run(_node_merge_query(spec), **_node_params(spec))
                n += 1
            return n
        return sess.execute_write(_work)


def _edge_merge_query(spec: EdgeSpec) -> str:
    a, b = safe_identifier(spec.from_label), safe_identifier(spec.to_label)
    rel = safe_identifier(spec.type)
    from_map = _key_pattern(spec.from_key, "from_key")
    to_map = _key_pattern(spec.to_key, "to_key")
    return "\n".join([
        f"MATCH (a:{a} {from_map})",
        f"MATCH (b:{b} {to_map})",
        f"MERGE (a)-[r:{rel}]->(b)",
        "SET r += $props, r.updated_at = timestamp()",
    ])


def upsert_edge(spec: EdgeSpec) -> None:
    """MERGE a single relationship between two existing nodes."""
    driver.run_write(
        _edge_merge_query(spec),
        {"from_key": spec.from_key, "to_key": spec.to_key, "props": spec.props},
    )


def upsert_edges(specs: List[EdgeSpec]) -> int:
    """MERGE many edges in one write transaction. Returns count attempted."""
    if not specs:
        return 0
    with driver.session() as sess:
        def _work(tx):
            n = 0
            for spec in specs:
                tx.run(
                    _edge_merge_query(spec),
                    from_key=spec.from_key, to_key=spec.to_key, props=spec.props,
                )
                n += 1
            return n
        return sess.execute_write(_work)


def get_node(label: str, key: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Fetch a node's properties by label + stable key, or None."""
    label = safe_identifier(label)
    q = f"MATCH (n:{label} {_key_pattern(key)}) RETURN properties(n) AS props LIMIT 1"
    rows = driver.run_read(q, {"key": key})
    return rows[0]["props"] if rows else None


def neighbors(
    label: str,
    key: Dict[str, Any],
    *,
    edge: Optional[str] = None,
    direction: str = "both",
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """Return neighboring nodes of an anchor node, optionally along one edge type."""
    label = safe_identifier(label)
    rel = f":{safe_identifier(edge)}" if edge else ""
    if direction == "out":
        pattern = f"(n)-[r{rel}]->(m)"
    elif direction == "in":
        pattern = f"(n)<-[r{rel}]-(m)"
    else:
        pattern = f"(n)-[r{rel}]-(m)"
    q = (
        f"MATCH (n:{label} {_key_pattern(key)}) "
        f"MATCH {pattern} "
        "RETURN labels(m) AS labels, properties(m) AS props, type(r) AS edge "
        "LIMIT $limit"
    )
    rows = driver.run_read(q, {"key": key, "limit": int(limit)})
    return rows


def vector_search(
    label: str,
    query_vector: List[float],
    *,
    top_k: int = 20,
    owner_id: Optional[str] = None,
    over_fetch: int = 5,
) -> List[Dict[str, Any]]:
    """ANN search over *label*'s vector index, filtered by owner.

    Over-fetches (``top_k * over_fetch``) then applies the ``owner_id`` filter in
    Cypher, because Neo4j's vector index cannot pre-filter by property.
    """
    idx = vector_index_name(label)
    fetch = int(top_k) * max(1, int(over_fetch))
    where = "WHERE node.owner_id = $owner_id" if owner_id is not None else ""
    q = (
        f"CALL db.index.vector.queryNodes('{idx}', $fetch, $vec) "
        "YIELD node, score "
        f"{where} "
        "RETURN labels(node) AS labels, properties(node) AS props, score "
        "ORDER BY score DESC LIMIT $top_k"
    )
    params = {"fetch": fetch, "vec": list(query_vector), "top_k": int(top_k)}
    if owner_id is not None:
        params["owner_id"] = owner_id
    rows = driver.run_read(q, params)
    for r in rows:
        r.get("props", {}).pop("embedding", None)  # never ship vectors to callers
    return rows


def fulltext_search(
    label: str,
    text: str,
    *,
    top_k: int = 20,
    owner_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Lexical search over *label*'s full-text index, filtered by owner."""
    idx = fulltext_index_name(label)
    where = "WHERE node.owner_id = $owner_id" if owner_id is not None else ""
    q = (
        f"CALL db.index.fulltext.queryNodes('{idx}', $text) YIELD node, score "
        f"{where} "
        "RETURN labels(node) AS labels, properties(node) AS props, score "
        "ORDER BY score DESC LIMIT $top_k"
    )
    params: Dict[str, Any] = {"text": text, "top_k": int(top_k)}
    if owner_id is not None:
        params["owner_id"] = owner_id
    rows = driver.run_read(q, params)
    for r in rows:
        r.get("props", {}).pop("embedding", None)
    return rows


def redirect_edges(
    dup_label: str,
    dup_key: Dict[str, Any],
    canon_label: str,
    canon_key: Dict[str, Any],
) -> Dict[str, int]:
    """Move all relationships off a duplicate node onto the canonical node and
    record a ``MERGED_INTO`` provenance edge (entity resolution, design §6).

    Returns counts of redirected in/out edges. The duplicate node is retained
    (not deleted) so the merge is auditable and reversible.
    """
    dup_label = safe_identifier(dup_label)
    canon_label = safe_identifier(canon_label)
    dup_map = _key_pattern(dup_key, "dup")
    canon_map = _key_pattern(canon_key, "canon")

    # Outgoing edges of the duplicate → recreate from canonical.
    out_q = (
        f"MATCH (d:{dup_label} {dup_map})-[r]->(x) "
        f"MATCH (c:{canon_label} {canon_map}) "
        "WHERE x <> c "
        "CALL apoc.create.relationship(c, type(r), properties(r), x) YIELD rel "
        "DELETE r RETURN count(rel) AS n"
    )
    in_q = (
        f"MATCH (x)-[r]->(d:{dup_label} {dup_map}) "
        f"MATCH (c:{canon_label} {canon_map}) "
        "WHERE x <> c "
        "CALL apoc.create.relationship(x, type(r), properties(r), c) YIELD rel "
        "DELETE r RETURN count(rel) AS n"
    )
    # apoc may be unavailable; fall back to a type-preserving-less redirect that
    # still connects the graph via RELATED_TO so nothing is orphaned.
    out_fallback = (
        f"MATCH (d:{dup_label} {dup_map})-[r]->(x) "
        f"MATCH (c:{canon_label} {canon_map}) WHERE x <> c "
        "MERGE (c)-[:RELATED_TO]->(x) DELETE r RETURN count(*) AS n"
    )
    in_fallback = (
        f"MATCH (x)-[r]->(d:{dup_label} {dup_map}) "
        f"MATCH (c:{canon_label} {canon_map}) WHERE x <> c "
        "MERGE (x)-[:RELATED_TO]->(c) DELETE r RETURN count(*) AS n"
    )
    params = {"dup": dup_key, "canon": canon_key}

    def _try(primary: str, fallback: str) -> int:
        try:
            rows = driver.run_write(primary, params)
        except Exception:  # noqa: BLE001 — apoc missing / other; use fallback
            rows = driver.run_write(fallback, params)
        return rows[0]["n"] if rows else 0

    n_out = _try(out_q, out_fallback)
    n_in = _try(in_q, in_fallback)

    driver.run_write(
        f"MATCH (d:{dup_label} {dup_map}) "
        f"MATCH (c:{canon_label} {canon_map}) "
        "MERGE (d)-[m:MERGED_INTO]->(c) "
        "SET d.resolved = true, d.merged_into = c.id, m.merged_at = timestamp()",
        params,
    )
    return {"out": n_out, "in": n_in}


__all__ = [
    "upsert_node",
    "upsert_nodes",
    "upsert_edge",
    "upsert_edges",
    "get_node",
    "neighbors",
    "vector_search",
    "fulltext_search",
    "redirect_edges",
]
