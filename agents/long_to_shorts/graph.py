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
  thumbnail           ← ThumbnailNode:     AI-directed thumbnail image per clip (optional)
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
  music_attach        ← MusicAttachNode:   mix recommended background music (optional)
      │
      ▼
    END

Optional nodes are controlled independently:
    ThumbnailNode  — env ADD_THUMBNAIL=1  or state["add_thumbnail"]  = True
    TopTextNode    — env ADD_TOP_TEXT=1   or state["add_top_text"]  = True
    SubtitlesNode  — env ADD_SUBTITLES=1  or state["add_subtitles"] = True
    IntroAttachNode — env ADD_INTRO=0 disables it   (default: enabled)
    MusicAttachNode — env ADD_MUSIC=1     or state["add_music"]     = True (default: disabled)
"""

from langgraph.graph import StateGraph, START, END

from agents.state import LongToShortsState
from agents.long_to_shorts.analyze_video_node import analyze_video_node
from agents.long_to_shorts.clipping_logic_node import clipping_logic_node
from agents.long_to_shorts.content_gen_node import content_gen_node
from agents.long_to_shorts.thumbnail_node import thumbnail_node
from agents.long_to_shorts.top_text_node import top_text_node
from agents.long_to_shorts.subtitles_node import subtitles_node
from agents.long_to_shorts.intro_attach_node import intro_attach_node
from agents.long_to_shorts.music_attach_node import music_attach_node

# ---------------------------------------------------------------------------
# Build the graph
# ---------------------------------------------------------------------------

_workflow: StateGraph = StateGraph(LongToShortsState)

# Register nodes
_workflow.add_node("analyze_video",  analyze_video_node)
_workflow.add_node("clipping_logic", clipping_logic_node)
_workflow.add_node("content_gen",    content_gen_node)
_workflow.add_node("thumbnail",      thumbnail_node)
_workflow.add_node("top_text",       top_text_node)
_workflow.add_node("subtitles",      subtitles_node)
_workflow.add_node("intro_attach",   intro_attach_node)
_workflow.add_node("music_attach",   music_attach_node)

# Linear edges
_workflow.add_edge(START,            "analyze_video")
_workflow.add_edge("analyze_video",  "clipping_logic")
_workflow.add_edge("clipping_logic", "content_gen")
_workflow.add_edge("content_gen",    "thumbnail")
_workflow.add_edge("thumbnail",      "top_text")
_workflow.add_edge("top_text",       "subtitles")
_workflow.add_edge("subtitles",      "intro_attach")
_workflow.add_edge("intro_attach",   "music_attach")
_workflow.add_edge("music_attach",   END)

# ---------------------------------------------------------------------------
# Compile (no checkpointer; no HITL interrupts needed for this sub-graph)
# ---------------------------------------------------------------------------

long_to_shorts_app = _workflow.compile()

__all__ = ["long_to_shorts_app"]
