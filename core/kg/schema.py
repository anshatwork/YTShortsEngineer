"""
core/kg/schema.py
~~~~~~~~~~~~~~~~~~
Declarative graph schema: the stable-key uniqueness constraints, owner_id range
indexes, vector indexes and full-text indexes that back the KG.

Neo4j is schema-flexible, so "schema" here means *constraints + indexes* rather
than table DDL. Every statement is written ``IF NOT EXISTS`` so applying it is
idempotent — that is what makes :func:`core.kg.migrations.run_migrations` safe to
run on every startup.

Embedding dimensions are read from the environment so they track whatever model
``tools/embeddings`` is configured with (bump the model → bump the dim → the
vector index is recreated by a migration). Defaults match the recommended
local-default stack (bge-small text = 384, OpenCLIP ViT-B/32 image = 512).
"""

from __future__ import annotations

import os
from typing import Dict, List, Tuple

from core.kg.models import safe_identifier

# label -> the property (or properties) forming its stable identity (MERGE key)
KEY_PROPS: Dict[str, Tuple[str, ...]] = {
    "MediaAsset": ("content_hash",),
    "Scene": ("asset_id", "scene_index"),
    "Frame": ("asset_id", "t_s"),
    "Clip": ("clip_id",),
    "TranscriptChunk": ("asset_id", "start_s", "end_s"),
    "TextBlock": ("asset_id", "block_key"),
    "Document": ("content_hash",),
    "Slide": ("content_hash", "page_no"),
    "Page": ("content_hash", "page_no"),
    "AudioTrack": ("asset_id",),
    "Speaker": ("asset_id", "speaker_label"),
    "Creator": ("user_id",),
    # Resolvable semantic entities MERGE on (owner_id, norm_name) — see §6.
    "Person": ("owner_id", "norm_name"),
    "Organization": ("owner_id", "norm_name"),
    "Location": ("owner_id", "norm_name"),
    "Product": ("owner_id", "norm_name"),
    "Topic": ("owner_id", "norm_name"),
    "Concept": ("owner_id", "norm_name"),
    "Event": ("owner_id", "norm_name"),
    "Activity": ("owner_id", "norm_name"),
    "Object": ("owner_id", "label_name"),
    # App-assigned uuid keys
    "Story": ("id",),
    "Quiz": ("id",),
    "Question": ("id",),
    "Course": ("id",),
    "Collection": ("id",),
    "Summary": ("id",),
    "CodeSnippet": ("id",),
    "Chart": ("id",),
}

# Searchable labels grouped by embedding modality (drives vector-index dims).
TEXT_EMBED_LABELS = (
    "MediaAsset", "Clip", "TranscriptChunk", "TextBlock", "Topic", "Concept",
    "Person", "Organization", "Product", "Location", "Event", "Activity",
    "Document", "Slide", "Summary",
)
IMAGE_EMBED_LABELS = ("Frame", "Scene")

# Labels that get an owner_id range index (hot path for tenant-scoped queries).
OWNER_INDEXED_LABELS = (
    "MediaAsset", "Scene", "Frame", "Clip", "TranscriptChunk", "TextBlock",
    "Document", "Slide", "Person", "Organization", "Location", "Product",
    "Topic", "Concept", "Event", "Activity", "Collection", "Story",
)

# Full-text indexes: label -> the text properties to index for lexical search.
FULLTEXT_INDEXES: Dict[str, Tuple[str, ...]] = {
    "TranscriptChunk": ("text",),
    "TextBlock": ("text",),
    "MediaAsset": ("title", "summary"),
    "Document": ("title", "text"),
}


def _text_dim() -> int:
    return int(os.getenv("EMBEDDING_DIM_TEXT", "384"))


def _image_dim() -> int:
    return int(os.getenv("EMBEDDING_DIM_IMAGE", "512"))


def _sim() -> str:
    return os.getenv("KG_VECTOR_SIMILARITY", "cosine")


def _constraint_stmt(label: str, props: Tuple[str, ...]) -> str:
    safe_identifier(label)
    cols = ", ".join(f"n.{safe_identifier(p)}" for p in props)
    name = f"uniq_{label.lower()}_" + "_".join(props)
    return (
        f"CREATE CONSTRAINT {name} IF NOT EXISTS "
        f"FOR (n:{label}) REQUIRE ({cols}) IS UNIQUE"
    )


def _owner_index_stmt(label: str) -> str:
    safe_identifier(label)
    return (
        f"CREATE INDEX idx_{label.lower()}_owner IF NOT EXISTS "
        f"FOR (n:{label}) ON (n.owner_id)"
    )


def _vector_index_stmt(label: str, dim: int) -> str:
    safe_identifier(label)
    name = f"vec_{label.lower()}_embedding"
    return (
        f"CREATE VECTOR INDEX {name} IF NOT EXISTS "
        f"FOR (n:{label}) ON (n.embedding) "
        f"OPTIONS {{indexConfig: {{"
        f"`vector.dimensions`: {int(dim)}, "
        f"`vector.similarity_function`: '{_sim()}'}}}}"
    )


def _fulltext_index_stmt(label: str, props: Tuple[str, ...]) -> str:
    safe_identifier(label)
    name = f"ft_{label.lower()}"
    each = ", ".join(f"n.{safe_identifier(p)}" for p in props)
    return (
        f"CREATE FULLTEXT INDEX {name} IF NOT EXISTS "
        f"FOR (n:{label}) ON EACH [{each}]"
    )


def schema_statements() -> List[str]:
    """Return every idempotent DDL statement that defines the graph schema."""
    stmts: List[str] = []
    for label, props in KEY_PROPS.items():
        stmts.append(_constraint_stmt(label, props))
    for label in OWNER_INDEXED_LABELS:
        stmts.append(_owner_index_stmt(label))
    for label in TEXT_EMBED_LABELS:
        stmts.append(_vector_index_stmt(label, _text_dim()))
    for label in IMAGE_EMBED_LABELS:
        stmts.append(_vector_index_stmt(label, _image_dim()))
    for label, props in FULLTEXT_INDEXES.items():
        stmts.append(_fulltext_index_stmt(label, props))
    return stmts


def vector_index_name(label: str) -> str:
    """Name of the vector index for *label* (used by repository.vector_search)."""
    return f"vec_{safe_identifier(label).lower()}_embedding"


def fulltext_index_name(label: str) -> str:
    return f"ft_{safe_identifier(label).lower()}"


__all__ = [
    "KEY_PROPS",
    "TEXT_EMBED_LABELS",
    "IMAGE_EMBED_LABELS",
    "OWNER_INDEXED_LABELS",
    "FULLTEXT_INDEXES",
    "schema_statements",
    "vector_index_name",
    "fulltext_index_name",
]
