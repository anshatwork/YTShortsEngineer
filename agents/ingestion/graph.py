"""
agents/ingestion/graph.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~
Standalone LangGraph StateGraph for knowledge-graph ingestion.

A linear perception→knowledge pipeline mirroring the long_to_shorts sub-graph
(no checkpointer; durability comes from the CAS + the content-hash keys):

    START → decode_probe → scene_detect → keyframe_extract → transcribe
          → chunk_transcript → ocr → embed → extract_entities
          → extract_relationships → resolve_entities → graph_upsert → END

Every node degrades rather than fails, so ingestion always persists whatever it
could extract.
"""

from langgraph.graph import END, START, StateGraph

from agents.ingestion.chunk_transcript_node import chunk_transcript_node
from agents.ingestion.decode_probe_node import decode_probe_node
from agents.ingestion.embed_node import embed_node
from agents.ingestion.extract_entities_node import extract_entities_node
from agents.ingestion.extract_relationships_node import extract_relationships_node
from agents.ingestion.graph_upsert_node import graph_upsert_node
from agents.ingestion.keyframe_extract_node import keyframe_extract_node
from agents.ingestion.ocr_node import ocr_node
from agents.ingestion.resolve_entities_node import resolve_entities_node
from agents.ingestion.scene_detect_node import scene_detect_node
from agents.ingestion.state import IngestionState
from agents.ingestion.transcribe_node import transcribe_node

_workflow: StateGraph = StateGraph(IngestionState)

_workflow.add_node("decode_probe", decode_probe_node)
_workflow.add_node("scene_detect", scene_detect_node)
_workflow.add_node("keyframe_extract", keyframe_extract_node)
_workflow.add_node("transcribe", transcribe_node)
_workflow.add_node("chunk_transcript", chunk_transcript_node)
_workflow.add_node("ocr", ocr_node)
_workflow.add_node("embed", embed_node)
_workflow.add_node("extract_entities", extract_entities_node)
_workflow.add_node("extract_relationships", extract_relationships_node)
_workflow.add_node("resolve_entities", resolve_entities_node)
_workflow.add_node("graph_upsert", graph_upsert_node)

_workflow.add_edge(START, "decode_probe")
_workflow.add_edge("decode_probe", "scene_detect")
_workflow.add_edge("scene_detect", "keyframe_extract")
_workflow.add_edge("keyframe_extract", "transcribe")
_workflow.add_edge("transcribe", "chunk_transcript")
_workflow.add_edge("chunk_transcript", "ocr")
_workflow.add_edge("ocr", "embed")
_workflow.add_edge("embed", "extract_entities")
_workflow.add_edge("extract_entities", "extract_relationships")
_workflow.add_edge("extract_relationships", "resolve_entities")
_workflow.add_edge("resolve_entities", "graph_upsert")
_workflow.add_edge("graph_upsert", END)

ingestion_app = _workflow.compile()

__all__ = ["ingestion_app"]
