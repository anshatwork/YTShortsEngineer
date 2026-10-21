"""
core/execution/lifecycle.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The job / stage lifecycle state machines, kept in one place.

Job status (already used by the stores): queued → running → done | failed.
Stage status (the per-node execution journal, see job_stages table):
    pending → running → complete | failed   (failed may retry → running)

Centralizing the allowed transitions lets callers validate before writing,
and gives every reader one definition of "terminal". This replaces ad-hoc
``status="..."`` string-passing scattered across the runners.
"""

from __future__ import annotations

from typing import Dict, Set

# ── Job-level ──────────────────────────────────────────────────────────────

JOB_QUEUED = "queued"
JOB_RUNNING = "running"
JOB_DONE = "done"
JOB_FAILED = "failed"

JOB_TERMINAL: Set[str] = {JOB_DONE, JOB_FAILED}

_JOB_TRANSITIONS: Dict[str, Set[str]] = {
    JOB_QUEUED: {JOB_RUNNING, JOB_FAILED},
    JOB_RUNNING: {JOB_DONE, JOB_FAILED, JOB_RUNNING},  # running→running = progress
    JOB_DONE: {JOB_RUNNING},     # allow explicit re-run of a finished job
    JOB_FAILED: {JOB_RUNNING},   # allow retry of a failed job
}

# ── Stage-level ────────────────────────────────────────────────────────────

STAGE_PENDING = "pending"
STAGE_RUNNING = "running"
STAGE_COMPLETE = "complete"
STAGE_FAILED = "failed"

STAGE_TERMINAL: Set[str] = {STAGE_COMPLETE}


# ── Publishing workflow (agents/publishing autonomous state machine) ────────
# A durable, human-gated macro workflow that wraps the clip pipeline. Two states
# are human gates (WAITING_FOR_*) — the only non-terminal states with no pending
# queue work; they idle until an approval endpoint fires. Everything else is an
# autonomous transition enqueued on the task queue.

PUB_DISCOVERING = "discovering"
PUB_WAITING_SOURCE = "waiting_for_source_approval"
PUB_WAITING_REVIEW = "waiting_for_context_review"
PUB_GENERATING = "generating"
PUB_SCORING = "scoring"
PUB_EVALUATING = "evaluating"
PUB_REVISING = "revising"
PUB_WAITING_UPLOAD = "waiting_for_upload_approval"
PUB_UPLOADING = "uploading"
PUB_COMPLETE = "complete"
PUB_FAILED = "failed"
PUB_CANCELLED = "cancelled"

PUBLISHING_TERMINAL: Set[str] = {PUB_COMPLETE, PUB_FAILED, PUB_CANCELLED}

# States the worker actively drives (has queued work). The two WAITING_* states
# and terminals are intentionally absent — a crash-recovery sweep re-enqueues
# only these.
PUBLISHING_RESUMABLE: Set[str] = {
    PUB_DISCOVERING, PUB_GENERATING, PUB_SCORING, PUB_EVALUATING,
    PUB_REVISING, PUB_UPLOADING,
}

_PUBLISHING_TRANSITIONS: Dict[str, Set[str]] = {
    PUB_DISCOVERING: {PUB_WAITING_SOURCE, PUB_FAILED, PUB_CANCELLED},
    # refresh loops back to DISCOVERING; approve advances to GENERATING.
    PUB_WAITING_SOURCE: {PUB_DISCOVERING, PUB_GENERATING, PUB_WAITING_REVIEW, PUB_FAILED, PUB_CANCELLED},
    PUB_WAITING_REVIEW: {PUB_GENERATING, PUB_DISCOVERING, PUB_FAILED, PUB_CANCELLED},
    PUB_GENERATING: {PUB_SCORING, PUB_FAILED, PUB_CANCELLED},
    # WAITING_UPLOAD is the no-eval edge (e.g. zero clips shortlisted).
    PUB_SCORING: {PUB_EVALUATING, PUB_WAITING_UPLOAD, PUB_FAILED, PUB_CANCELLED},
    PUB_EVALUATING: {PUB_REVISING, PUB_WAITING_UPLOAD, PUB_FAILED, PUB_CANCELLED},
    PUB_REVISING: {PUB_EVALUATING, PUB_FAILED, PUB_CANCELLED},
    # approve→UPLOADING, regenerate→GENERATING, reject→CANCELLED, edit→(self).
    PUB_WAITING_UPLOAD: {
        PUB_UPLOADING, PUB_GENERATING, PUB_WAITING_UPLOAD, PUB_FAILED, PUB_CANCELLED,
    },
    PUB_UPLOADING: {PUB_COMPLETE, PUB_FAILED, PUB_CANCELLED},
}


def can_transition_job(current: str, target: str) -> bool:
    """True if a job may move from *current* to *target* status."""
    if current == target:
        return True
    return target in _JOB_TRANSITIONS.get(current, set())


def can_transition_publishing(current: str, target: str) -> bool:
    """True if a publishing job may move from *current* to *target* status."""
    if current == target:
        return True
    return target in _PUBLISHING_TRANSITIONS.get(current, set())


def is_publishing_terminal(status: str) -> bool:
    return status in PUBLISHING_TERMINAL


def is_job_terminal(status: str) -> bool:
    return status in JOB_TERMINAL


def is_stage_complete(status: str) -> bool:
    return status == STAGE_COMPLETE


__all__ = [
    "JOB_QUEUED", "JOB_RUNNING", "JOB_DONE", "JOB_FAILED", "JOB_TERMINAL",
    "STAGE_PENDING", "STAGE_RUNNING", "STAGE_COMPLETE", "STAGE_FAILED", "STAGE_TERMINAL",
    "can_transition_job", "is_job_terminal", "is_stage_complete",
    "PUB_DISCOVERING", "PUB_WAITING_SOURCE", "PUB_WAITING_REVIEW", "PUB_GENERATING", "PUB_SCORING",
    "PUB_EVALUATING", "PUB_REVISING", "PUB_WAITING_UPLOAD", "PUB_UPLOADING",
    "PUB_COMPLETE", "PUB_FAILED", "PUB_CANCELLED",
    "PUBLISHING_TERMINAL", "PUBLISHING_RESUMABLE",
    "can_transition_publishing", "is_publishing_terminal",
]
