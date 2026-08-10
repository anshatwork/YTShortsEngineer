"""
agents/ingestion/graph_upsert_node.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Stage 11 — persist everything into the knowledge graph.

Turns the accumulated state (asset, scenes, frames, chunks, text blocks, entities,
relationships) into ``core.kg`` NodeSpec / EdgeSpec writes and MERGEs them in one
transaction each (atomic per asset). All MERGEs are on stable keys, so a re-ingest
converges rather than duplicating (idempotent — design §6).

Gated by ``core.kg.driver.kg_enabled``: when the graph is off this node is a
no-op, keeping the whole layer additive. Degrade-not-fail: a write error is logged
and reported in ``stats`` but never crashes ingestion.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from agents.ingestion._logging_utils import node_stage
from core.kg import driver, repository
from core.kg.models import EdgeSpec, NodeSpec

logger = logging.getLogger(__name__)


def _graph_upsert_impl(state: Dict[str, Any]) -> Dict[str, Any]:
    if not driver.kg_enabled():
        logger.info("KG disabled; graph_upsert skipped.")
        return {"stats": {"nodes": 0, "edges": 0, "skipped": 1}}

    content_hash = state.get("content_hash")
    if not content_hash:
        return {"stats": {"nodes": 0, "edges": 0, "error": 1}}

    owner_id = state.get("owner_id")
    asset_id = state.get("asset_id") or content_hash
    media_asset: Dict[str, Any] = state.get("media_asset") or {}
    scenes: List[Dict[str, Any]] = state.get("scenes") or []
    chunks: List[Dict[str, Any]] = state.get("transcript_chunks") or []
    blocks: List[Dict[str, Any]] = state.get("text_blocks") or []
    entities: List[Dict[str, Any]] = state.get("entities") or []
    relationships: List[Dict[str, Any]] = state.get("relationships") or []

    nodes: List[NodeSpec] = []
    edges: List[EdgeSpec] = []

    asset_key = {"content_hash": content_hash}

    # --- MediaAsset ---
    nodes.append(NodeSpec(
        label="MediaAsset",
        key_props=asset_key,
        owner_id=owner_id,
        props={
            "asset_id": asset_id,
            "media_type": media_asset.get("media_type"),
            "uri": media_asset.get("uri"),
            "title": media_asset.get("title"),
            "summary": media_asset.get("summary"),
            "duration_s": media_asset.get("duration_s"),
        },
        embedding=media_asset.get("embedding"),
    ))

    # --- Scenes + Frames ---
    prev_scene_key: Optional[Dict[str, Any]] = None
    for sc in scenes:
        scene_key = {"asset_id": asset_id, "scene_index": sc["scene_index"]}
        nodes.append(NodeSpec(
            label="Scene", key_props=scene_key, owner_id=owner_id,
            props={
                "start_s": sc.get("start_s"), "end_s": sc.get("end_s"),
                "t_s": sc.get("t_s"),
                "keyframe_cas_ref": sc.get("keyframe_path"),
            },
            embedding=sc.get("embedding"),
        ))
        edges.append(EdgeSpec(type="PART_OF", from_label="Scene", from_key=scene_key,
                              to_label="MediaAsset", to_key=asset_key))
        if prev_scene_key is not None:
            edges.append(EdgeSpec(type="FOLLOWS", from_label="Scene", from_key=scene_key,
                                  to_label="Scene", to_key=prev_scene_key))
        prev_scene_key = scene_key

        # Frame (temporal + OCR anchor) when a keyframe exists
        if sc.get("keyframe_path") and sc.get("t_s") is not None:
            frame_key = {"asset_id": asset_id, "t_s": sc["t_s"]}
            nodes.append(NodeSpec(
                label="Frame", key_props=frame_key, owner_id=owner_id,
                props={"cas_ref": sc.get("keyframe_path"), "scene_index": sc["scene_index"]},
                embedding=sc.get("embedding"),  # shared CLIP vector
            ))
            edges.append(EdgeSpec(type="HAS_FRAME", from_label="Scene", from_key=scene_key,
                                  to_label="Frame", to_key=frame_key))
            edges.append(EdgeSpec(type="PART_OF", from_label="Frame", from_key=frame_key,
                                  to_label="MediaAsset", to_key=asset_key))

    # --- TranscriptChunks ---
    chunk_key_by_index: Dict[int, Dict[str, Any]] = {}
    prev_chunk_key: Optional[Dict[str, Any]] = None
    for c in chunks:
        chunk_key = {"asset_id": asset_id, "start_s": c["start_s"], "end_s": c["end_s"]}
        chunk_key_by_index[c["chunk_index"]] = chunk_key
        nodes.append(NodeSpec(
            label="TranscriptChunk", key_props=chunk_key, owner_id=owner_id,
            props={"text": c.get("text"), "chunk_index": c.get("chunk_index")},
            embedding=c.get("embedding"),
        ))
        edges.append(EdgeSpec(type="PART_OF", from_label="TranscriptChunk", from_key=chunk_key,
                              to_label="MediaAsset", to_key=asset_key))
        if prev_chunk_key is not None:
            edges.append(EdgeSpec(type="FOLLOWS", from_label="TranscriptChunk", from_key=chunk_key,
                                  to_label="TranscriptChunk", to_key=prev_chunk_key))
        prev_chunk_key = chunk_key

    # --- TextBlocks (OCR) ---
    for b in blocks:
        tb_key = {"asset_id": asset_id, "block_key": b["block_key"]}
        nodes.append(NodeSpec(
            label="TextBlock", key_props=tb_key, owner_id=owner_id,
            props={"text": b.get("text"), "bbox": b.get("bbox"), "t_s": b.get("t_s"),
                   "confidence": b.get("confidence")},
            embedding=b.get("embedding"),
        ))
        # Anchor OCR text to its frame when one exists at that timestamp.
        if b.get("t_s") is not None:
            frame_key = {"asset_id": asset_id, "t_s": b["t_s"]}
            edges.append(EdgeSpec(type="CONTAINS_TEXT", from_label="Frame", from_key=frame_key,
                                  to_label="TextBlock", to_key=tb_key))

    # --- Entities ---
    for ent in entities:
        ent_key = {"owner_id": owner_id, "norm_name": ent["norm_name"]}
        nodes.append(NodeSpec(
            label=ent["label"], key_props=ent_key, owner_id=owner_id,
            props={"name": ent.get("name"), "norm_name": ent["norm_name"]},
            embedding=ent.get("embedding"),
        ))

    # --- Relationships (ref-resolved) ---
    def _resolve(ref: Dict[str, Any]) -> Optional[Tuple[str, Dict[str, Any]]]:
        kind = ref.get("node")
        if kind == "asset":
            return "MediaAsset", asset_key
        if kind == "chunk":
            key = chunk_key_by_index.get(ref.get("index"))
            return ("TranscriptChunk", key) if key else None
        if kind == "entity":
            return ref["label"], {"owner_id": owner_id, "norm_name": ref["norm_name"]}
        return None

    for rel in relationships:
        src = _resolve(rel["from_ref"])
        dst = _resolve(rel["to_ref"])
        if not src or not dst:
            continue
        edges.append(EdgeSpec(
            type=rel["type"],
            from_label=src[0], from_key=src[1],
            to_label=dst[0], to_key=dst[1],
            props={"source": "ingestion"},
        ))

    # --- Persist ---
    n_nodes = n_edges = 0
    try:
        n_nodes = repository.upsert_nodes(nodes)
        n_edges = repository.upsert_edges(edges)
    except Exception as exc:  # noqa: BLE001 — report, don't crash ingestion
        logger.exception("graph_upsert write failed: %s", exc)
        return {"stats": {"nodes": n_nodes, "edges": n_edges, "error": 1}}

    stats = {
        "nodes": n_nodes, "edges": n_edges,
        "scenes": len(scenes), "chunks": len(chunks),
        "text_blocks": len(blocks), "entities": len(entities),
    }
    logger.info("graph_upsert done: %s", stats)
    return {"stats": stats}


def graph_upsert_node(state: Dict[str, Any]) -> Dict[str, Any]:
    with node_stage(state, "graph_upsert"):
        return _graph_upsert_impl(state)


__all__ = ["graph_upsert_node"]
