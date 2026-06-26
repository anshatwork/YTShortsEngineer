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
import traceback
from contextlib import contextmanager
from typing import Any, Dict, Iterator


@contextmanager
def node_stage(state: Dict[str, Any], name: str) -> Iterator[None]:
    """Context manager that logs node entry/exit, updates job_store.current_node,
    and records a per-stage checkpoint in the execution journal (job_stages).

    The journal (see api/stage_store.py) gives a durable, cross-process record of
    which stages started / completed / failed. Skipping recompute on a resume is
    handled separately by the content-addressable cache (core/cache), so re-running
    a node after a crash is cheap and idempotent — this just records the fact.
    All store interactions are best-effort and never break the pipeline.

    Also binds the ``current_node`` logging contextvar for the duration of the
    body so every log line emitted by the node (including third-party libs like
    ffmpeg-python / httpx) is stamped ``[job:<id>|<node>]``.
    """
    from core.logging_config import current_node as _node_ctx

    logger = logging.getLogger(f"agents.long_to_shorts.{name}")
    job_id = state.get("job_id", "?") if isinstance(state, dict) else "?"
    t0 = time.perf_counter()
    node_token = _node_ctx.set(name)

    if job_id != "?":
        try:
            from agents.long_to_shorts.api.job_store import job_store
            job_store.update(job_id, current_node=name)
        except Exception:
            pass
        try:
            from agents.long_to_shorts.api.stage_store import stage_store
            stage_store.start(job_id, name)
        except Exception:
            pass

    logger.info("[job:%s] %s START", job_id, name)
    try:
        yield
    except Exception as exc:
        logger.exception(
            "[job:%s] %s FAILED after %.2fs", job_id, name,
            time.perf_counter() - t0,
        )
        if job_id != "?":
            try:
                from agents.long_to_shorts.api.stage_store import stage_store
                # Persist a traceback tail (stage_store truncates to 2000 chars)
                # so the stored / SSE-streamed error is actionable, not just a
                # one-line message.
                tb = "".join(
                    traceback.format_exception(type(exc), exc, exc.__traceback__)
                )
                stage_store.fail(job_id, name, error=f"{exc}\n\n{tb}")
            except Exception:
                pass
        raise
    else:
        logger.info(
            "[job:%s] %s END (%.2fs)", job_id, name,
            time.perf_counter() - t0,
        )
        if job_id != "?":
            try:
                from agents.long_to_shorts.api.stage_store import stage_store
                stage_store.complete(job_id, name)
            except Exception:
                pass
    finally:
        _node_ctx.reset(node_token)


__all__ = ["node_stage"]
