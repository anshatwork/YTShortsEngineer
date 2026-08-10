"""
core/kg/migrations
~~~~~~~~~~~~~~~~~~~
Idempotent schema/version runner for the knowledge graph.

Because Neo4j is schema-flexible, a "migration" is (a) the constraint/index DDL
from :mod:`core.kg.schema` — all ``IF NOT EXISTS`` so re-applying is a no-op —
plus (b) optional numbered data backfills registered in :data:`DATA_MIGRATIONS`.
Applied backfills are recorded on a ``(:_KGMigration {version})`` marker node so
each runs at most once.

Run it explicitly::

    python -m core.kg.migrations        # applies schema + pending backfills

or programmatically via :func:`run_migrations` (e.g. from a deploy script or a
test fixture). It is safe to call on every startup.
"""

from __future__ import annotations

import logging
from typing import Callable, Dict, List, Tuple

from core.kg import driver
from core.kg.schema import schema_statements

logger = logging.getLogger(__name__)

# Numbered data backfills: (version, description, fn). fn takes no args and uses
# core.kg.driver.run_write. Keep them idempotent anyway (belt and suspenders).
DATA_MIGRATIONS: List[Tuple[int, str, Callable[[], None]]] = []

SCHEMA_VERSION = 1  # bump when schema_statements() changes meaningfully


def _applied_versions() -> set:
    rows = driver.run_read(
        "MATCH (m:_KGMigration) RETURN m.version AS version"
    )
    return {r["version"] for r in rows}


def _record_version(version: int, description: str) -> None:
    driver.run_write(
        "MERGE (m:_KGMigration {version: $version}) "
        "SET m.description = $description, m.applied_at = timestamp()",
        {"version": version, "description": description},
    )


def apply_schema() -> int:
    """Apply every constraint/index statement. Returns the count applied."""
    stmts = schema_statements()
    for stmt in stmts:
        try:
            driver.run_write(stmt)
        except Exception as exc:  # noqa: BLE001
            # A concurrent/duplicate create can race; log and continue so one bad
            # statement never blocks the rest of the schema.
            logger.warning("schema statement failed (continuing): %s | %s", exc, stmt)
    _record_version(SCHEMA_VERSION, "schema constraints + indexes")
    logger.info("KG schema applied (%d statements, version=%d)", len(stmts), SCHEMA_VERSION)
    return len(stmts)


def run_migrations() -> Dict[str, int]:
    """Apply schema + any pending data backfills. Returns a small summary dict."""
    if not driver.kg_enabled():
        logger.info("KG disabled (KG_ENABLED not set); skipping migrations.")
        return {"schema_statements": 0, "data_migrations": 0}

    n_schema = apply_schema()

    applied = _applied_versions()
    n_data = 0
    for version, description, fn in sorted(DATA_MIGRATIONS):
        if version in applied:
            continue
        logger.info("running KG data migration v%d: %s", version, description)
        fn()
        _record_version(version, description)
        n_data += 1

    return {"schema_statements": n_schema, "data_migrations": n_data}


if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(level=logging.INFO)
    print(run_migrations())


__all__ = ["run_migrations", "apply_schema", "DATA_MIGRATIONS", "SCHEMA_VERSION"]
