"""UUID helpers. Deterministic ids (``stable_uuid``) give content/idempotency keys that converge on
re-ingest, mirroring the parent repo's content-hash → stable-key convention."""

from __future__ import annotations

import uuid

# Fixed namespace for the Learning OS so deterministic ids are stable across processes/machines.
_NAMESPACE = uuid.UUID("6f9619ff-8b86-d011-b42d-00c04fc964ff")


def new_uuid() -> str:
    return str(uuid.uuid4())


def stable_uuid(*parts: str) -> str:
    """Deterministic UUIDv5 from the given parts (e.g. ``stable_uuid(owner_id, content_hash)``)."""
    return str(uuid.uuid5(_NAMESPACE, "\x00".join(parts)))
