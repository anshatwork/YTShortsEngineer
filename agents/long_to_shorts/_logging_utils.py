"""
agents/long_to_shorts/_logging_utils.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Shared instrumentation helper for the Long-to-Shorts LangGraph nodes.

Each node wraps its body with `node_stage(state, "<name>")` to get:
  • [job:<id>] <name> START
  • [job:<id>] <name> END (<seconds>s)
  • [job:<id>] <name> FAILED after <seconds>s   (on exception, then re-raise)
  • job_store.update(job_id, current_node="<name>") so the API exposes real
    per-stage progress to the frontend.

Works whether or not `job_id` is present in state — CLI runs without the API
just emit `[job:?]` lines and skip the job_store update.
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Any, Dict, Iterator


@contextmanager
def node_stage(state: Dict[str, Any], name: str) -> Iterator[None]:
    """Context manager that logs node entry/exit and updates job_store.current_node."""
    logger = logging.getLogger(f"agents.long_to_shorts.{name}")
    job_id = state.get("job_id", "?") if isinstance(state, dict) else "?"
    t0 = time.perf_counter()

    if job_id != "?":
        try:
            from agents.long_to_shorts.api.job_store import job_store
            job_store.update(job_id, current_node=name)
        except Exception:
            pass

    logger.info("[job:%s] %s START", job_id, name)
    try:
        yield
    except Exception:
        logger.exception(
            "[job:%s] %s FAILED after %.2fs", job_id, name,
            time.perf_counter() - t0,
        )
        raise
    else:
        logger.info(
            "[job:%s] %s END (%.2fs)", job_id, name,
            time.perf_counter() - t0,
        )


__all__ = ["node_stage"]
