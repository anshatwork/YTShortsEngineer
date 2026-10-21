"""Owner-scope helpers. Tenant isolation is the platform's top invariant: every stored node/row/
vector carries ``owner_id`` and every read is filtered by it (Neo4j has no RLS). These helpers keep
the owner check in one place so services can't forget it."""

from __future__ import annotations


class OwnershipError(PermissionError):
    """Raised when a resource's owner does not match the requesting user."""


def require_owner(resource_owner_id: str | None, requester_owner_id: str) -> None:
    """Assert the requester owns the resource. Raise :class:`OwnershipError` otherwise.

    ``resource_owner_id is None`` is treated as not-found-for-this-owner (also raises), so callers
    can map both to a 404 without leaking existence across tenants.
    """
    if resource_owner_id is None or resource_owner_id != requester_owner_id:
        raise OwnershipError("resource not owned by requester")
