"""Ingestion application service — orchestration only (no business rules, no transport).

Ties the ``Content`` aggregate to persistence + the event log. This is the single place that turns
"remember this URL" into a saved aggregate plus a ``ContentSaved`` event on the outbox.
"""

from __future__ import annotations

import logging
from typing import Optional

from los.events.event_store import EventStore
from los.services.ingestion.adapters.repository import ContentRepository
from los.services.ingestion.domain.content import Content, SourceType

logger = logging.getLogger(__name__)


class IngestionService:
    def __init__(self, repo: ContentRepository, store: EventStore) -> None:
        self._repo = repo
        self._store = store

    async def save_content(
        self,
        *,
        owner_id: str,
        url: str,
        source_type: SourceType,
        title: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> tuple[Content, bool]:
        """Idempotently save content. Returns ``(content, created)`` — ``created`` is False when the
        same URL was already remembered by this owner (no duplicate row, no second event).

        NOTE (Phase 1 follow-up): the content insert and the event append are two writes; for the
        postgres backend they should share one transaction. The memory backend is atomic; the
        outbox already guarantees atomicity between the event append and the broker publish.
        """
        content = Content.create(owner_id=owner_id, url=url, source_type=source_type, title=title)

        existing = await self._repo.get_by_hash(owner_id, content.content_hash)
        if existing is not None:
            logger.info("idempotent capture: %s already saved for owner", existing.content_id)
            return existing, False

        await self._repo.insert(content)
        event = content.saved_event(correlation_id=correlation_id)
        stored = await self._store.append(event)
        logger.info("appended %s (stream=%s seq=%s)", stored.type, stored.stream, stored.seq)
        return content, True
