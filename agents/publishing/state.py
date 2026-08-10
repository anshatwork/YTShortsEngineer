"""
agents/publishing/state.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
State for the publishing *review* sub-graph (Stage 3 scoring → Stage 4 eval →
revision loop). This is the short-lived, in-memory state for one GENERATING/
EVALUATING worker step — the durable macro state lives in ``publishing_jobs``
(see agents/long_to_shorts/api/publishing_store.py). Durability of expensive work
inside this graph comes from the CAS (cached scores/evals), not a checkpointer.

Single-owner-writes (mirrors agents/ingestion/state.py):
    scoring_node    → scored_clips, shortlist_ids
    eval_agent_node → eval_reports, selected_clip_id, selected_eval
    revise_node     → clips (rewritten metadata), revision_count
Everything is read-only to the nodes that don't own it.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict


class PublishingClipState(TypedDict, total=False):
    # -- inputs (set by the runner before invoke) --
    job_id: str                       # the publishing_job_id, for [publish:<id>] logs
    clips: List[Dict[str, Any]]       # ClipResult dicts from the reused clip pipeline
    transcript: Optional[str]
    timed_transcript: Optional[List[Dict[str, Any]]]
    user_context: Optional[str]
    max_revisions: int

    # -- scoring_node owns --
    scored_clips: List[Dict[str, Any]]   # ScoreCard dumps
    shortlist_ids: List[str]

    # -- eval_agent_node owns --
    eval_reports: List[Dict[str, Any]]   # EvalReport dumps (one per shortlisted clip)
    selected_clip_id: Optional[str]
    selected_eval: Optional[Dict[str, Any]]

    # -- revise_node owns --
    revision_count: int

    # -- status --
    current_node: Optional[str]
    error: Optional[str]


__all__ = ["PublishingClipState"]
