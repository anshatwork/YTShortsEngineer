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


def can_transition_job(current: str, target: str) -> bool:
    """True if a job may move from *current* to *target* status."""
    if current == target:
        return True
    return target in _JOB_TRANSITIONS.get(current, set())


def is_job_terminal(status: str) -> bool:
    return status in JOB_TERMINAL


def is_stage_complete(status: str) -> bool:
    return status == STAGE_COMPLETE


__all__ = [
    "JOB_QUEUED", "JOB_RUNNING", "JOB_DONE", "JOB_FAILED", "JOB_TERMINAL",
    "STAGE_PENDING", "STAGE_RUNNING", "STAGE_COMPLETE", "STAGE_FAILED", "STAGE_TERMINAL",
    "can_transition_job", "is_job_terminal", "is_stage_complete",
]
