"""Content persistence port + memory/postgres adapters.

Every read is owner-scoped (tenant isolation invariant). ``get_by_hash`` powers idempotent capture:
re-remembering the same URL returns the existing row instead of inserting a duplicate.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Optional

from los.services.ingestion.domain.content import Content, ContentStatus, SourceType


class ContentRepository(ABC):
    @abstractmethod
    async def start(self) -> None: ...

    @abstractmethod
    async def close(self) -> None: ...

    @abstractmethod
    async def get_by_hash(self, owner_id: str, content_hash: str) -> Optional[Content]: ...

    @abstractmethod
    async def get(self, owner_id: str, content_id: str) -> Optional[Content]: ...

    @abstractmethod
    async def insert(self, content: Content) -> None: ...

    @abstractmethod
    async def list_for_owner(self, owner_id: str, limit: int = 100) -> list[Content]: ...

    @abstractmethod
    async def set_status(self, owner_id: str, content_id: str, status: ContentStatus) -> None: ...


class MemoryContentRepository(ContentRepository):
    def __init__(self) -> None:
        self._by_id: dict[str, Content] = {}
        self._by_hash: dict[tuple[str, str], str] = {}  # (owner, hash) -> content_id

    async def start(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def get_by_hash(self, owner_id: str, content_hash: str) -> Optional[Content]:
        cid = self._by_hash.get((owner_id, content_hash))
        return self._by_id.get(cid) if cid else None

    async def get(self, owner_id: str, content_id: str) -> Optional[Content]:
        c = self._by_id.get(content_id)
        return c if c and c.owner_id == owner_id else None

    async def insert(self, content: Content) -> None:
        self._by_id[content.content_id] = content
        self._by_hash[(content.owner_id, content.content_hash)] = content.content_id

    async def list_for_owner(self, owner_id: str, limit: int = 100) -> list[Content]:
        items = [c for c in self._by_id.values() if c.owner_id == owner_id]
        items.sort(key=lambda c: c.created_at, reverse=True)
        return items[:limit]

    async def set_status(self, owner_id: str, content_id: str, status: ContentStatus) -> None:
        c = await self.get(owner_id, content_id)
        if c is not None:
            c.status = status


class PostgresContentRepository(ContentRepository):
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._pool: Any = None

    async def start(self) -> None:
        from los.db.pg import open_pool

        self._pool = await open_pool(self._dsn)

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    async def get_by_hash(self, owner_id: str, content_hash: str) -> Optional[Content]:
        row = await self._pool.fetchrow(
            "SELECT * FROM content WHERE owner_id = $1 AND content_hash = $2",
            owner_id, content_hash,
        )
        return _row_to_content(row) if row else None

    async def get(self, owner_id: str, content_id: str) -> Optional[Content]:
        row = await self._pool.fetchrow(
            "SELECT * FROM content WHERE owner_id = $1 AND content_id = $2",
            owner_id, content_id,
        )
        return _row_to_content(row) if row else None

    async def insert(self, content: Content) -> None:
        r = content.to_row()
        # ON CONFLICT DO NOTHING keeps insert idempotent under the unique(owner_id, content_hash).
        await self._pool.execute(
            """
            INSERT INTO content
              (content_id, owner_id, source_type, url, content_hash, title, status, created_at)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
            ON CONFLICT (owner_id, content_hash) DO NOTHING
            """,
            r["content_id"], r["owner_id"], r["source_type"], r["url"], r["content_hash"],
            r["title"], r["status"], r["created_at"],
        )

    async def list_for_owner(self, owner_id: str, limit: int = 100) -> list[Content]:
        rows = await self._pool.fetch(
            "SELECT * FROM content WHERE owner_id = $1 ORDER BY created_at DESC LIMIT $2",
            owner_id, limit,
        )
        return [_row_to_content(r) for r in rows]

    async def set_status(self, owner_id: str, content_id: str, status: ContentStatus) -> None:
        await self._pool.execute(
            "UPDATE content SET status = $3 WHERE owner_id = $1 AND content_id = $2",
            owner_id, content_id, status.value,
        )


def _row_to_content(row: Any) -> Content:
    created = row["created_at"]
    if created is not None and created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return Content(
        content_id=str(row["content_id"]),
        owner_id=str(row["owner_id"]),
        source_type=SourceType(row["source_type"]),
        url=row["url"],
        content_hash=row["content_hash"],
        title=row["title"],
        status=ContentStatus(row["status"]),
        created_at=created or datetime.now(timezone.utc),
    )


def make_content_repository(backend: str, dsn: str) -> ContentRepository:
    if backend == "postgres":
        return PostgresContentRepository(dsn)
    return MemoryContentRepository()
