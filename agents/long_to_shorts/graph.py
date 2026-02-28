"""
agents/long_to_shorts/graph.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Standalone LangGraph StateGraph for the Long-to-Shorts clipping pipeline.

Graph topology (linear, no ReviewNode):

    START
      │
      ▼
  analyze_video       ← AnalyzeVideoNode:  LLM hook-scores transcript segments
      │
      ▼
  clipping_logic      ← ClippingLogicNode: parallel ffmpeg 9:16 extraction (Map)
      │
      ▼
  content_gen         ← ContentGenNode:    viral title + summary per clip (Reduce)
      │
      ▼
  intro_attach        ← IntroAttachNode:   prepend title-card intro + crossfade
      │
      ▼
    END

No manual review step — the LLM's Hook Score in AnalyzeVideoNode is the
automatic filter (top-N selection replaces human review).

IntroAttachNode can be disabled at runtime by setting ADD_INTRO=0 in the
environment; it will pass generated_clips through unchanged in that case.
"""

from langgraph.graph import StateGraph, START, END

from agents.state import LongToShortsState
from agents.long_to_shorts.analyze_video_node import analyze_video_node
from agents.long_to_shorts.clipping_logic_node import clipping_logic_node
from agents.long_to_shorts.content_gen_node import content_gen_node
from agents.long_to_shorts.intro_attach_node import intro_attach_node

# ---------------------------------------------------------------------------
# Build the graph
# ---------------------------------------------------------------------------

_workflow: StateGraph = StateGraph(LongToShortsState)

# Register nodes
_workflow.add_node("analyze_video", analyze_video_node)
_workflow.add_node("clipping_logic", clipping_logic_node)
_workflow.add_node("content_gen", content_gen_node)
_workflow.add_node("intro_attach", intro_attach_node)

# Linear edges: analysis → clipping (Map) → content_gen (Reduce) → intro_attach
_workflow.add_edge(START, "analyze_video")
_workflow.add_edge("analyze_video", "clipping_logic")
_workflow.add_edge("clipping_logic", "content_gen")
_workflow.add_edge("content_gen", "intro_attach")
_workflow.add_edge("intro_attach", END)

# ---------------------------------------------------------------------------
# Compile (no checkpointer; no HITL interrupts needed for this sub-graph)
# ---------------------------------------------------------------------------

long_to_shorts_app = _workflow.compile()

__all__ = ["long_to_shorts_app"]
