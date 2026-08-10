"""
agents.ingestion
~~~~~~~~~~~~~~~~~
The knowledge-graph ingestion sub-graph: converts any uploaded asset into
persistent graph entities + relationships + embeddings, exactly once.

    from agents.ingestion import ingestion_app
    final = ingestion_app.invoke({"asset_id": ..., "owner_id": ..., "source_path": ...})

Driven by ``agents/long_to_shorts/api/ingestion_runner.py`` on a worker thread,
or invoked directly for CLI/testing. See ``agents/ingestion/graph.py`` for the
node order and ``docs/claude/knowledge-graph.md`` for the design.
"""

from agents.ingestion.graph import ingestion_app

__all__ = ["ingestion_app"]
