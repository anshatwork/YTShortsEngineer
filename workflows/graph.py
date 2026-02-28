from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from workflows.state import ShortsState
from agents.trend_discovery import TrendDiscoveryAgent
from agents.content_sourcing import ContentSourcingAgent
from agents.script_generation import ScriptGenerationAgent
from agents.voice_synthesis import VoiceSynthesisAgent
from agents.video_assembly import VideoAssemblyAgent
from agents.quality_control import QualityControlAgent
from agents.publisher import PublisherAgent

# Node Wrappers
def trend_discovery_node(state: ShortsState):
    return TrendDiscoveryAgent().run(state)

def content_sourcing_node(state: ShortsState):
    return ContentSourcingAgent().run(state)

def script_generation_node(state: ShortsState):
    return ScriptGenerationAgent().run(state)

def voice_synthesis_node(state: ShortsState):
    return VoiceSynthesisAgent().run(state)

def video_assembly_node(state: ShortsState):
    return VideoAssemblyAgent().run(state)

def quality_control_node(state: ShortsState):
    return QualityControlAgent().run(state)

def publisher_node(state: ShortsState):
    return PublisherAgent().run(state)

# Initialize Graph
workflow = StateGraph(ShortsState)

# Add Nodes
workflow.add_node("trend_discovery", trend_discovery_node)
workflow.add_node("content_sourcing", content_sourcing_node)
workflow.add_node("script_generation", script_generation_node)
workflow.add_node("voice_synthesis", voice_synthesis_node)
workflow.add_node("video_assembly", video_assembly_node)
workflow.add_node("quality_control", quality_control_node)
workflow.add_node("publisher", publisher_node)

# Define Edges
workflow.add_edge(START, "trend_discovery")
workflow.add_edge("trend_discovery", "content_sourcing")
# Interrupt here for video selection
workflow.add_edge("content_sourcing", "script_generation")
workflow.add_edge("script_generation", "voice_synthesis")
workflow.add_edge("voice_synthesis", "video_assembly")
# Interrupt here for final review
workflow.add_edge("video_assembly", "quality_control")

# Conditional Routing
def route_after_qc(state: ShortsState) -> str:
    if state.get("review_status") == "approved":
        return "publisher"
    return END

workflow.add_conditional_edges(
    "quality_control",
    route_after_qc,
    {
        "publisher": "publisher",
        END: END
    }
)

workflow.add_edge("publisher", END)

# Persistence
memory = MemorySaver()

# Compile
app = workflow.compile(
    checkpointer=memory,
    interrupt_before=["script_generation", "quality_control"]
)
