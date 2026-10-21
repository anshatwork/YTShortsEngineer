"""
agents/publishing/_logging_utils.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``node_stage`` for the publishing review sub-graph — the analogue of
``agents/long_to_shorts/_logging_utils.node_stage``. Stamps ``[publish:<id>]``
logs, binds the ``current_node`` logging contextvar, and best-effort updates the
publishing job's ``phase_detail`` for live SSE. All store interaction is
best-effort and never breaks the graph (degrade-not-fail).
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Any, Dict, Iterator

logger = logging.getLogger(__name__)

# Review-node → durable publishing status. node_stage advances the publishing
# job's status as the sub-graph walks (SCORING → EVALUATING → REVISING → …), so
# the DB row (and SSE) reflects the real stage without the runner interleaving
# writes into a synchronous graph invoke. Guarded by can_transition_publishing.
_NODE_STATUS = {
    "scoring": "scoring",
    "eval": "evaluating",
    "revise": "revising",
}


def _sync_status(job_id: str, name: str) -> None:
    """Best-effort: advance the publishing job's status + phase_detail. Never raises."""
    try:
        from agents.long_to_shorts.api.publishing_store import publishing_store
        from core.execution.lifecycle import can_transition_publishing

        fields: Dict[str, Any] = {"phase_detail": f"review:{name}"}
        target = _NODE_STATUS.get(name)
        if target is not None:
            job = publishing_store.get(job_id)
            current = getattr(job, "status", None)
            if current and current != target and can_transition_publishing(current, target):
                fields["status"] = target
        publishing_store.update(job_id, **fields)
    except Exception:  # noqa: BLE001 — instrumentation must never break the graph
        pass


@contextmanager
def node_stage(state: Dict[str, Any], name: str) -> Iterator[None]:
    from core.logging_config import current_node as _node_ctx

    job_id = state.get("job_id", "?") if isinstance(state, dict) else "?"
    t0 = time.perf_counter()
    node_token = _node_ctx.set(name)

    if job_id != "?":
        _sync_status(job_id, name)

    logger.info("[publish:%s] %s START", job_id, name)
    try:
        yield
    except Exception:
        logger.exception(
            "[publish:%s] %s FAILED after %.2fs", job_id, name, time.perf_counter() - t0
        )
        raise
    else:
        logger.info("[publish:%s] %s END (%.2fs)", job_id, name, time.perf_counter() - t0)
    finally:
        _node_ctx.reset(node_token)


__all__ = ["node_stage"]
