"""
LangGraph workflow for YouTube Shorts Creator
Defines the complete workflow graph with HITL interrupts and batch processing support
"""

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from agents.state import ShortsState
from agents.node import (
    parse_scripts_node,
    generate_queries_node,
    generate_script_node,
    select_video_node,
    select_audio_node,
    render_video_node,
    review_node,
    upload_to_yt_node
)
from tools.youtube_api import fetch_yt_assets_node

# Initialize Graph
workflow = StateGraph(ShortsState)

# Add Nodes
workflow.add_node("parse_scripts", parse_scripts_node)  # NEW: Parse long-form content
workflow.add_node("generate_queries", generate_queries_node)
workflow.add_node("fetch_assets", fetch_yt_assets_node)
workflow.add_node("generate_script", generate_script_node)
workflow.add_node("select_video", select_video_node)
workflow.add_node("select_audio", select_audio_node)  # NEW: Select background audio
workflow.add_node("render_video", render_video_node)
workflow.add_node("review", review_node)
workflow.add_node("upload_to_yt", upload_to_yt_node)

# Define Edges
# Conditional start: parse_scripts if source_content exists, otherwise generate_script
def route_start(state: ShortsState) -> str:
    """Route to parser if source_content exists, otherwise to script generation."""
    if state.get("source_content"):
        return "parse_scripts"
    return "generate_script"

workflow.add_conditional_edges(
    START,
    route_start,
    {
        "parse_scripts": "parse_scripts",
        "generate_script": "generate_script"
    }
)

# After parsing, go to script generation (which will use extract mode)
workflow.add_edge("parse_scripts", "generate_script")

# New Flow: Script (Intent) -> Video Selection (Search) -> Audio Selection -> Render
workflow.add_edge("generate_script", "select_video")
workflow.add_edge("select_video", "select_audio")  # NEW: Add audio selection
workflow.add_edge("select_audio", "render_video")

# Interrupt before review for user to review the video
workflow.add_edge("render_video", "review")

# Conditional edge after review
def route_after_review(state: ShortsState) -> str:
    """Route to upload if approved, otherwise end."""
    if state.get("review_status") == "approved":
        return "upload_to_yt"
    return END

workflow.add_conditional_edges(
    "review",
    route_after_review,
    {
        "upload_to_yt": "upload_to_yt",
        END: END
    }
)

workflow.add_edge("upload_to_yt", END)

# Persistence for HITL
memory = MemorySaver()

# Compile with interrupts
app = workflow.compile(
    checkpointer=memory,
    interrupt_before=["select_video", "render_video", "review"] 
)