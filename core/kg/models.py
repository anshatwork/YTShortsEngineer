"""
core/kg/models.py
~~~~~~~~~~~~~~~~~~
Pydantic schemas for the multimodal Knowledge Graph write/read surface.

These are transport/spec objects — deliberately generic so one repository can
upsert *any* node/edge — plus the canonical label/edge vocabulary and the
:class:`QuerySpec` the query engine compiles to parameterized Cypher.

Design notes
------------
* A node is identified by its **stable key** (``key_props``): the properties that
  uniquely identify the real-world thing (e.g. ``{"content_hash": ...}`` for a
  ``MediaAsset``, ``{"owner_id": ..., "norm_name": ...}`` for a ``Concept``).
  The repository ``MERGE``s on exactly those, which is what makes ingestion
  idempotent (§6 of the design).
* All nodes carry ``owner_id`` for tenant isolation — Neo4j has no RLS, so the
  query builder always filters by it. This is enforced in :mod:`core.kg.query`.
* Labels, edge types and property *keys* cannot be parameterized in Cypher, so
  they are validated as safe identifiers before interpolation (see
  :func:`safe_identifier`). Property *values* are always passed as parameters.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

# ---------------------------------------------------------------------------
# Canonical vocabulary (kept in sync with docs/claude/knowledge-graph.md §2/§4)
# ---------------------------------------------------------------------------

# Media / structural
MEDIA_LABELS = (
    "MediaAsset", "Scene", "Frame", "Clip", "TranscriptChunk",
    "Document", "Slide", "Page", "AudioTrack", "TextBlock",
)
# Semantic entities (Person is text/NER-derived only — no biometrics)
ENTITY_LABELS = (
    "Person", "Organization", "Location", "Product",
    "Topic", "Concept", "Event", "Activity", "Object",
    "CodeSnippet", "Chart",
)
# Knowledge / derived + identity
DERIVED_LABELS = (
    "Question", "Quiz", "Story", "Course", "Collection", "Summary",
    "Creator", "Speaker",
)
NODE_LABELS = MEDIA_LABELS + ENTITY_LABELS + DERIVED_LABELS

# Entity labels that participate in dedup / entity resolution (§6). These MERGE
# on (owner_id, norm_name); everything else MERGEs on content/structural keys.
RESOLVABLE_LABELS = (
    "Person", "Organization", "Location", "Product",
    "Topic", "Concept", "Event", "Activity",
)

EDGE_TYPES = (
    "PART_OF", "HAS_FRAME", "DERIVED_FROM", "GENERATED_FROM", "MENTIONS",
    "ABOUT_TOPIC", "EXPLAINS", "CONTAINS_TEXT", "SHOWS_OBJECT", "USES_PRODUCT",
    "TAKEN_AT", "FOLLOWS", "RELATED_TO", "REFERENCES", "BELONGS_TO", "CONTAINS",
    "SUMMARIZES", "MERGED_INTO", "APPEARS_IN",
)

MediaType = Literal["video", "image", "screenshot", "document", "slide", "audio"]

# A Cypher identifier we are willing to interpolate into a query string. Values
# never go through here — only labels, relationship types and property keys.
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def safe_identifier(name: str) -> str:
    """Return *name* if it is a safe Cypher identifier, else raise ``ValueError``.

    Labels / relationship types / property keys cannot be query parameters, so
    they must be interpolated — this is the guard that keeps that injection-safe.
    """
    if not isinstance(name, str) or not _IDENT_RE.match(name):
        raise ValueError(f"unsafe cypher identifier: {name!r}")
    return name


# ---------------------------------------------------------------------------
# Write specs
# ---------------------------------------------------------------------------

class NodeSpec(BaseModel):
    """A node to upsert (MERGE on ``key_props``, then SET the rest)."""

    label: str = Field(..., description="Node label, e.g. 'MediaAsset'.")
    key_props: Dict[str, Any] = Field(
        ..., description="Properties forming the stable identity (MERGE key)."
    )
    props: Dict[str, Any] = Field(
        default_factory=dict, description="Remaining properties to SET on the node."
    )
    owner_id: Optional[str] = Field(
        default=None, description="Tenant scope; folded into props on write."
    )
    embedding: Optional[List[float]] = Field(
        default=None, description="Vector for the node's embedding index (if searchable)."
    )
    embedding_field: str = Field(
        default="embedding", description="Property name the vector is stored under."
    )
    embedding_model: Optional[str] = Field(
        default=None, description="Identifier of the model that produced the embedding."
    )

    @field_validator("label")
    @classmethod
    def _valid_label(cls, v: str) -> str:
        return safe_identifier(v)

    def merged_props(self) -> Dict[str, Any]:
        """All non-key properties to SET (owner_id + embedding metadata folded in)."""
        out = dict(self.props)
        if self.owner_id is not None:
            out.setdefault("owner_id", self.owner_id)
        if self.embedding_model is not None:
            out["embedding_model"] = self.embedding_model
        return out


class EdgeSpec(BaseModel):
    """A relationship to upsert between two nodes identified by their key props."""

    type: str = Field(..., description="Relationship type, e.g. 'MENTIONS'.")
    from_label: str
    from_key: Dict[str, Any]
    to_label: str
    to_key: Dict[str, Any]
    props: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("type")
    @classmethod
    def _valid_type(cls, v: str) -> str:
        return safe_identifier(v)

    @field_validator("from_label", "to_label")
    @classmethod
    def _valid_label(cls, v: str) -> str:
        return safe_identifier(v)


# ---------------------------------------------------------------------------
# Query spec (compiled to Cypher by core/kg/query.py)
# ---------------------------------------------------------------------------

class TraversalStep(BaseModel):
    """One hop away from the anchor node, e.g. up ``PART_OF`` to a ``MediaAsset``."""

    edge: str = Field(..., description="Relationship type to traverse.")
    direction: Literal["out", "in", "both"] = "out"
    target_label: Optional[str] = Field(
        default=None, description="Restrict the far node to this label."
    )

    @field_validator("edge")
    @classmethod
    def _valid_edge(cls, v: str) -> str:
        return safe_identifier(v)


class QuerySpec(BaseModel):
    """A structured, validated query over the graph.

    Compiled to parameterized Cypher with an ``owner_id`` filter always applied
    (see :func:`core.kg.query.build_cypher`). Doubles as the ``output_format``
    schema for natural-language → query interpretation via ``get_llm().parse``.
    """

    label: str = Field(..., description="Anchor node label to match.")
    filters: Dict[str, Any] = Field(
        default_factory=dict,
        description="Exact-match property filters on the anchor node.",
    )
    text_query: Optional[str] = Field(
        default=None,
        description="Free-text query for hybrid vector/lexical search.",
    )
    traversals: List[TraversalStep] = Field(
        default_factory=list,
        description="Ordered hops to expand from the anchor before returning.",
    )
    time_window: Optional[List[float]] = Field(
        default=None,
        description="Optional [start_s, end_s] interval filter on the anchor.",
    )
    top_k: int = Field(default=20, ge=1, le=200)

    @field_validator("label")
    @classmethod
    def _valid_label(cls, v: str) -> str:
        return safe_identifier(v)


class GraphNodeResult(BaseModel):
    """A node returned from a read — label(s) + properties (embedding stripped)."""

    labels: List[str] = Field(default_factory=list)
    properties: Dict[str, Any] = Field(default_factory=dict)
    score: Optional[float] = Field(
        default=None, description="Similarity/relevance score when from a search."
    )


__all__ = [
    "MediaType",
    "NODE_LABELS",
    "MEDIA_LABELS",
    "ENTITY_LABELS",
    "DERIVED_LABELS",
    "RESOLVABLE_LABELS",
    "EDGE_TYPES",
    "safe_identifier",
    "NodeSpec",
    "EdgeSpec",
    "TraversalStep",
    "QuerySpec",
    "GraphNodeResult",
]
