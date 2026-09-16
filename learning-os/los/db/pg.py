"""asyncpg connection-pool helper. Import of ``asyncpg`` is lazy so the in-memory dev/test path
carries no hard dependency on the driver."""

from __future__ import annotations

from typing import Any


async def open_pool(dsn: str, *, min_size: int = 1, max_size: int = 10) -> Any:
    """Create and return an asyncpg pool. Callers own its lifecycle (``await pool.close()``)."""
    import asyncpg  # lazy

    return await asyncpg.create_pool(dsn, min_size=min_size, max_size=max_size)
