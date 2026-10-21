"""
agents/publishing
~~~~~~~~~~~~~~~~~~
The Autonomous Publishing Agent's intelligence layer: the discovery agent
(Stage 1) and the review sub-graph (Stage 3 scoring → Stage 4 evaluation →
bounded revision loop). The durable, human-gated orchestration around this lives
in ``agents/long_to_shorts/api`` (publishing_store / _orchestrator / _runner /
_routes); the clip generation (Stage 2) and upload reuse the existing pipeline.
"""

from agents.publishing.graph import publishing_review_app

__all__ = ["publishing_review_app"]
