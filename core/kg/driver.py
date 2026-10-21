"""
core/kg/driver.py
~~~~~~~~~~~~~~~~~~
Process-wide Neo4j driver singleton + thin session helpers.

This is the low-level seam between the KG and the graph database. It mirrors the
conventions of the rest of the repo:

* config is read from the environment at first use (``os.getenv``) so the module
  is import-safe even when the graph is not configured — exactly like
  ``supabase_client.get_worker_client`` and ``core.cache.get_cache``;
* the ``neo4j`` package is imported **lazily** so it is only a hard dependency
  when the KG is actually enabled (mirrors ``tools/llm`` lazy provider imports);
* ``kg_enabled()`` is the master switch (``KG_ENABLED``, default **off**) so the
  new layer is purely additive — nothing in the existing pipeline changes until
  it is turned on.

``NEO4J_URI`` / ``NEO4J_USER`` / ``NEO4J_PASSWORD`` are read here (also declared
in ``core/config.py`` for documentation). Memgraph is a drop-in: point
``NEO4J_URI`` at the ``bolt://`` endpoint of a Memgraph instance.
"""

from __future__ import annotations

import logging
import os
import threading
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Optional

from core.exceptions import KnowledgeGraphError

logger = logging.getLogger(__name__)

_driver: Any = None
_driver_lock = threading.Lock()


def kg_enabled() -> bool:
    """Master switch for the knowledge-graph layer (default off — additive)."""
    return os.getenv("KG_ENABLED", "false").lower() in ("1", "true", "yes")


def _neo4j_config() -> Dict[str, str]:
    uri = os.getenv("NEO4J_URI")
    if not uri:
        raise KnowledgeGraphError(
            "NEO4J_URI is not set; the knowledge graph cannot connect. "
            "Set NEO4J_URI/NEO4J_USER/NEO4J_PASSWORD (or KG_ENABLED=false)."
        )
    return {
        "uri": uri,
        "user": os.getenv("NEO4J_USER", "neo4j"),
        "password": os.getenv("NEO4J_PASSWORD", "neo4j"),
    }


def get_driver() -> Any:
    """Return the process-wide Neo4j driver, creating it on first use.

    Raises :class:`KnowledgeGraphError` if the ``neo4j`` package is missing or the
    connection cannot be established — callers that must degrade gracefully should
    guard with :func:`kg_enabled` and catch this.
    """
    global _driver
    if _driver is not None:
        return _driver
    with _driver_lock:
        if _driver is not None:
            return _driver
        try:
            from neo4j import GraphDatabase  # lazy: only needed when KG is on
        except ImportError as exc:  # pragma: no cover - env-dependent
            raise KnowledgeGraphError(
                "the 'neo4j' package is not installed; run `pip install neo4j` "
                "to enable the knowledge graph."
            ) from exc
        cfg = _neo4j_config()
        try:
            _driver = GraphDatabase.driver(
                cfg["uri"], auth=(cfg["user"], cfg["password"])
            )
        except Exception as exc:  # noqa: BLE001
            raise KnowledgeGraphError(f"could not create Neo4j driver: {exc}") from exc
    return _driver


def close_driver() -> None:
    """Close and drop the singleton driver (used at shutdown / in tests)."""
    global _driver
    with _driver_lock:
        if _driver is not None:
            try:
                _driver.close()
            except Exception:  # noqa: BLE001
                pass
            _driver = None


@contextmanager
def session(*, database: Optional[str] = None) -> Iterator[Any]:
    """Yield a Neo4j session bound to the singleton driver."""
    driver = get_driver()
    db = database or os.getenv("NEO4J_DATABASE") or None
    sess = driver.session(database=db) if db else driver.session()
    try:
        yield sess
    finally:
        sess.close()


def run_write(cypher: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Execute a write query in a managed transaction; return rows as dicts."""
    with session() as sess:
        return sess.execute_write(lambda tx: [r.data() for r in tx.run(cypher, **(params or {}))])


def run_read(cypher: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Execute a read query in a managed transaction; return rows as dicts."""
    with session() as sess:
        return sess.execute_read(lambda tx: [r.data() for r in tx.run(cypher, **(params or {}))])


def health() -> Dict[str, Any]:
    """Return a small health dict for the ``/kg/health`` probe.

    Never raises — reports ``ok: False`` with the reason so a health endpoint can
    surface KG status without taking the whole API down.
    """
    if not kg_enabled():
        return {"ok": False, "enabled": False, "detail": "KG_ENABLED is not set"}
    try:
        get_driver().verify_connectivity()
        return {"ok": True, "enabled": True}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "enabled": True, "detail": str(exc)}


__all__ = [
    "kg_enabled",
    "get_driver",
    "close_driver",
    "session",
    "run_write",
    "run_read",
    "health",
]
