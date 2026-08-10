"""
agents/long_to_shorts/api/publishing_orchestrator.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Pure state-machine transition logic for the Autonomous Publishing Agent. No I/O,
no store, no side effects — just "given the current status and an event/action,
what is the next status?". Kept pure so the whole state machine is unit-testable
without a database, and so the runner (autonomous events) and the approval routes
(human actions) share one definition of what's legal.

The durable status lives in ``publishing_jobs`` (publishing_store); the runner and
routes call these helpers and then persist the returned target status.
"""

from __future__ import annotations

from typing import Optional

from core.execution.lifecycle import (
    PUB_CANCELLED,
    PUB_COMPLETE,
    PUB_DISCOVERING,
    PUB_FAILED,
    PUB_GENERATING,
    PUB_UPLOADING,
    PUB_WAITING_SOURCE,
    PUB_WAITING_REVIEW,
    PUB_WAITING_UPLOAD,
    can_transition_publishing,
    is_publishing_terminal,
)


class InvalidTransition(Exception):
    """Raised when an event/action is not legal for the current status.

    Routes map this to HTTP 409 (wrong state), the runner to a failed job.
    """


# ---------------------------------------------------------------------------
# Autonomous events (emitted by the runner as each stage completes)
# ---------------------------------------------------------------------------

# event -> the status the runner moves to when the event fires. The *source*
# status is validated separately via can_transition_publishing.
_AUTONOMOUS_TARGET = {
    "discovered": PUB_WAITING_SOURCE,
    "generated": None,        # generation flows straight into review; no status hop
    "reviewed": PUB_WAITING_UPLOAD,
    "uploaded": PUB_COMPLETE,
    "error": PUB_FAILED,
}


def next_autonomous_status(current: str, event: str) -> str:
    """Return the target status for an autonomous *event*, validating the hop."""
    if event not in _AUTONOMOUS_TARGET:
        raise InvalidTransition(f"unknown event '{event}'")
    target = _AUTONOMOUS_TARGET[event]
    if target is None:
        return current
    if event == "error":
        return PUB_FAILED  # always allowed from any non-terminal state
    if not can_transition_publishing(current, target):
        raise InvalidTransition(f"cannot go {current} -> {target} on '{event}'")
    return target


# ---------------------------------------------------------------------------
# Human actions (from the two approval endpoints)
# ---------------------------------------------------------------------------

def resolve_source_action(current: str, action: str, video_url: Optional[str]) -> str:
    """Human decision #1 — approve / reject / refresh the source video."""
    if current != PUB_WAITING_SOURCE:
        raise InvalidTransition(
            f"source approval only valid at '{PUB_WAITING_SOURCE}' (now '{current}')"
        )
    if action == "approve":
        if not video_url:
            raise InvalidTransition("approve requires a video_url")
        return PUB_GENERATING
    if action == "refresh":
        return PUB_DISCOVERING
    if action == "reject":
        return PUB_CANCELLED
    raise InvalidTransition(f"unknown source action '{action}'")


def resolve_upload_action(current: str, action: str) -> str:
    """Human decision #2 — approve / reject / regenerate / edit metadata."""
    if current != PUB_WAITING_UPLOAD:
        raise InvalidTransition(
            f"upload approval only valid at '{PUB_WAITING_UPLOAD}' (now '{current}')"
        )
    if action in ("approve", "select_clip"):
        return PUB_UPLOADING
    if action == "regenerate":
        return PUB_GENERATING
    if action == "reject":
        return PUB_CANCELLED
    if action == "edit_metadata":
        return PUB_WAITING_UPLOAD  # stays at the gate after patching
    raise InvalidTransition(f"unknown upload action '{action}'")


def is_gate(status: str) -> bool:
    """True for the two human-gate states (idle; no queued work)."""
    return status in (PUB_WAITING_SOURCE, PUB_WAITING_REVIEW, PUB_WAITING_UPLOAD)


def is_terminal(status: str) -> bool:
    return is_publishing_terminal(status)


__all__ = [
    "InvalidTransition",
    "next_autonomous_status",
    "resolve_source_action",
    "resolve_upload_action",
    "is_gate",
    "is_terminal",
]
