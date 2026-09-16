"""Shared domain primitives used by every service: the event envelope, id helpers, owner scope."""

from los.domain_shared.envelope import Event, new_event
from los.domain_shared.ids import new_uuid, stable_uuid

__all__ = ["Event", "new_event", "new_uuid", "stable_uuid"]
