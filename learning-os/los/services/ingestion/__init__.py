"""Content Ingestion service — the one explicit user action ("Remember this") enters here.

Responsibility: dedup on a normalized-URL content hash, persist the immutable ``Content`` aggregate,
and append a ``ContentSaved`` event (via the transactional outbox). Downstream services react to the
event; the user's request returns as soon as the content is saved.
"""
