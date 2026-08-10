"""
agents/ingestion/_logging_utils.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``node_stage`` for the ingestion sub-graph — the analogue of
``agents/long_to_shorts/_logging_utils.node_stage``, but it updates the
*ingestion* job store (not the clip job store).

Each ingestion node wraps its body with ``node_stage(state, "<name>")`` to get
consistent ``[ingest:<id>] <name> START/END/FAILED`` logging, the
``current_node`` logging contextvar, and a best-effort
``ingestion_job_store.update(current_node=...)`` for live SSE progress. All store
interactions are best-effort and never break ingestion.
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Any, Dict, Iterator

logger = logging.getLogger(__name__)


@contextmanager
def node_stage(state: Dict[str, Any], name: str) -> Iterator[None]:
    from core.logging_config import current_node as _node_ctx

    job_id = state.get("job_id", "?") if isinstance(state, dict) else "?"
    t0 = time.perf_counter()
    node_token = _node_ctx.set(name)

    if job_id != "?":
        try:
            from agents.long_to_shorts.api.ingestion_job_store import ingestion_job_store
            ingestion_job_store.update(job_id, current_node=name)
        except Exception:
            pass

    logger.info("[ingest:%s] %s START", job_id, name)
    try:
        yield
    except Exception:
        logger.exception(
            "[ingest:%s] %s FAILED after %.2fs", job_id, name, time.perf_counter() - t0
        )
        raise
    else:
        logger.info("[ingest:%s] %s END (%.2fs)", job_id, name, time.perf_counter() - t0)
    finally:
        _node_ctx.reset(node_token)


__all__ = ["node_stage"]
