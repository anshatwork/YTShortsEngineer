"""
agents/ingestion/state.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~
State schema for the knowledge-graph ingestion sub-graph.

Mirrors the conventions of ``agents/state.py`` / ``LongToShortsState``: a
``TypedDict(total=False)`` whose keys are written by exactly one owning node and
read downstream. Perception nodes accumulate intermediate structures (scenes,
chunks, entities…); the final ``graph_upsert`` node turns them into
``core.kg`` NodeSpec/EdgeSpec writes.

Ownership (only-owner-writes, like the clip pipeline):
    decode_probe          → content_hash, media_type, duration_s, media_asset
    scene_detect          → scenes
    keyframe_extract      → scenes[*].keyframe_path
    transcribe            → transcript, timed_transcript
    chunk_transcript      → transcript_chunks
    ocr                   → text_blocks
    embed                 → *_embedding fields on the above
    extract_entities      → entities
    extract_relationships → relationships
    resolve_entities      → entities (normalized/deduped)
    graph_upsert          → stats
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict


class IngestionState(TypedDict, total=False):
    # --- Inputs (built by the runner) ---
    asset_id: str                       # Supabase assets.asset_id (uuid)
    owner_id: str                       # tenant scope; stamped on every KG node
    source_path: str                    # local path to the media bytes
    media_type: str                     # video|image|screenshot|document|slide|audio
    uri: str                            # original source (url / path / upload id)
    title: Optional[str]
    filename: Optional[str]
    transcript: Optional[str]           # pre-supplied transcript (skips Whisper)
    timed_transcript: Optional[List[Dict[str, Any]]]  # [{"text","start","duration"}]

    # --- Job tracking (populated by the runner) ---
    job_id: str                         # ingestion_job_id for logs + progress
    current_node: str

    # --- Intermediate (owned per the table above) ---
    content_hash: str
    duration_s: float
    width: int
    height: int
    media_asset: Dict[str, Any]         # base props + optional embedding
    scenes: List[Dict[str, Any]]        # {scene_index,start_s,end_s,keyframe_path?,embedding?}
    transcript_chunks: List[Dict[str, Any]]  # {chunk_index,start_s,end_s,text,embedding?}
    text_blocks: List[Dict[str, Any]]   # {block_key,text,bbox,t_s,scene_index,embedding?}
    entities: List[Dict[str, Any]]      # {label,name,norm_name,chunk_index?,embedding?}
    relationships: List[Dict[str, Any]] # {type,from,to,props}

    # --- Output ---
    stats: Dict[str, int]               # {"nodes","edges","entities",...}
    error: Optional[str]


__all__ = ["IngestionState"]
