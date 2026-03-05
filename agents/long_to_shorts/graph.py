"""
agents/long_to_shorts/graph.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Standalone LangGraph StateGraph for the Long-to-Shorts clipping pipeline.

Graph topology (linear):

    START
      │
      ▼
  analyze_video       ← AnalyzeVideoNode:  LLM hook-scores transcript segments
      │
      ▼
  clipping_logic      ← ClippingLogicNode: parallel ffmpeg 9:16 extraction (Map)
      │
      ▼
  content_gen         ← ContentGenNode:    viral title + summary + hook_text + hashtags
      │
      ▼
  top_text            ← TopTextNode:       burn hook-text overlay at top of clip (optional)
      │
      ▼
  subtitles           ← SubtitlesNode:     Whisper transcription + burn subtitles (optional)
      │
      ▼
  intro_attach        ← IntroAttachNode:   prepend title-card intro + crossfade (optional)
      │
      ▼
    END

Optional nodes are controlled independently:
    TopTextNode    — env ADD_TOP_TEXT=1   or state["add_top_text"]  = True
    SubtitlesNode  — env ADD_SUBTITLES=1  or state["add_subtitles"] = True
    IntroAttachNode — env ADD_INTRO=0 disables it   (default: enabled)
"""

from langgraph.graph import StateGraph, START, END

from agents.state import LongToShortsState
from agents.long_to_shorts.analyze_video_node import analyze_video_node
from agents.long_to_shorts.clipping_logic_node import clipping_logic_node
from agents.long_to_shorts.content_gen_node import content_gen_node
from agents.long_to_shorts.top_text_node import top_text_node
from agents.long_to_shorts.subtitles_node import subtitles_node
from agents.long_to_shorts.intro_attach_node import intro_attach_node

# ---------------------------------------------------------------------------
# Build the graph
# ---------------------------------------------------------------------------

_workflow: StateGraph = StateGraph(LongToShortsState)

# Register nodes
_workflow.add_node("analyze_video",  analyze_video_node)
_workflow.add_node("clipping_logic", clipping_logic_node)
_workflow.add_node("content_gen",    content_gen_node)
_workflow.add_node("top_text",       top_text_node)
_workflow.add_node("subtitles",      subtitles_node)
_workflow.add_node("intro_attach",   intro_attach_node)

# Linear edges
_workflow.add_edge(START,            "analyze_video")
_workflow.add_edge("analyze_video",  "clipping_logic")
_workflow.add_edge("clipping_logic", "content_gen")
_workflow.add_edge("content_gen",    "top_text")
_workflow.add_edge("top_text",       "subtitles")
_workflow.add_edge("subtitles",      "intro_attach")
_workflow.add_edge("intro_attach",   END)

# ---------------------------------------------------------------------------
# Compile (no checkpointer; no HITL interrupts needed for this sub-graph)
# ---------------------------------------------------------------------------

long_to_shorts_app = _workflow.compile()

__all__ = ["long_to_shorts_app"]
