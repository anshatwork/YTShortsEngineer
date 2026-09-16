"""Thin async-Postgres helpers shared by services that use the ``postgres`` backend."""

from los.db.pg import open_pool

__all__ = ["open_pool"]
