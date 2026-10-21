"""
agents/publishing/graph.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The publishing *review* sub-graph — Stage 3 (scoring) → Stage 4 (evaluation)
with a bounded generator→eval→revise loop:

    START → scoring → eval ─(pass OR budget spent)─→ END
                       ▲                              │
                       └────────── revise ◄───────────┘ (fail & revisions < max)

Mirrors the ingestion/long_to_shorts sub-graphs: module-level ``StateGraph``,
compiled once, no checkpointer (durability = the CAS-cached scores/evals). It is
invoked synchronously inside the orchestrator's GENERATING/EVALUATING step.

The revision loop is ALWAYS bounded — ``revise_node`` increments the counter even
on failure and the router stops at ``max_revisions`` — so it can never spin.
"""

from __future__ import annotations

import logging
import os

from langgraph.graph import END, START, StateGraph

from agents.publishing.eval_agent_node import eval_agent_node
from agents.publishing.revise_node import revise_node
from agents.publishing.scoring_node import scoring_node
from agents.publishing.state import PublishingClipState

logger = logging.getLogger(__name__)


def _max_revisions(state: PublishingClipState) -> int:
    v = state.get("max_revisions")
    if v is None:
        v = int(os.getenv("PUBLISH_MAX_REVISIONS", "2"))
    return int(v)


def _route_after_eval(state: PublishingClipState) -> str:
    """Revise only if the selected clip failed AND we still have budget."""
    selected = state.get("selected_eval") or {}
    if selected.get("passed"):
        return "done"
    if int(state.get("revision_count", 0)) >= _max_revisions(state):
        return "done"
    return "revise"


_workflow: StateGraph = StateGraph(PublishingClipState)

_workflow.add_node("scoring", scoring_node)
_workflow.add_node("eval", eval_agent_node)
_workflow.add_node("revise", revise_node)

_workflow.add_edge(START, "scoring")
_workflow.add_edge("scoring", "eval")
_workflow.add_conditional_edges(
    "eval", _route_after_eval, {"revise": "revise", "done": END}
)
_workflow.add_edge("revise", "eval")

publishing_review_app = _workflow.compile()

__all__ = ["publishing_review_app"]
