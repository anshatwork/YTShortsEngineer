"""
core.kg
~~~~~~~
Multimodal Knowledge Graph — the persistent semantic layer ("the brain").

This is a ``core/`` leaf primitive (a peer of :mod:`core.cache`): it imports only
from ``core/`` and knows nothing about graph state, nodes or the API. Everything
above it (the ingestion sub-graph, the API, future applications) reaches the graph
through this package.

Public surface::

    from core.kg import driver, repository, query, resolution
    from core.kg.models import NodeSpec, EdgeSpec, QuerySpec

    if driver.kg_enabled():
        repository.upsert_node(NodeSpec(label="MediaAsset",
                                        key_props={"content_hash": h},
                                        owner_id=uid, props={...}))
        hits = query.semantic_search("TranscriptChunk", "explain RAG", uid)

The graph is behind ``KG_ENABLED`` (default off) so the layer is purely additive;
callers guard writes/reads with :func:`core.kg.driver.kg_enabled`.
"""

from core.kg import driver, query, repository, resolution
from core.kg.models import EdgeSpec, NodeSpec, QuerySpec

__all__ = [
    "driver",
    "repository",
    "query",
    "resolution",
    "NodeSpec",
    "EdgeSpec",
    "QuerySpec",
]
