"""The ``Content`` aggregate — pure domain, no I/O.

Content is *evidence* (a video/article the user chose to remember), not the primary entity. Its
invariants: immutable once saved, one node per ``(owner_id, content_hash)`` where the hash is a
normalized-URL fingerprint (so re-remembering the same link is idempotent). The aggregate knows how
to emit its ``ContentSaved`` fact; it does not know how that fact is persisted or published.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from los.domain_shared.envelope import Event, new_event
from los.domain_shared.ids import stable_uuid

CONTENT_SAVED = "ContentSaved"

# Tracking params dropped during normalization so the same link dedups regardless of referral noise.
_TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "gclid", "si", "feature", "ref", "ref_src", "spm",
}


class SourceType(str, Enum):
    YOUTUBE = "youtube"
    YOUTUBE_SHORTS = "youtube_shorts"
    ARTICLE = "article"
    DOCUMENTATION = "documentation"
    # Extension points (Phase 5) — declared, not yet ingestible:
    # PDF, PODCAST, GITHUB, BOOK, COURSE, MEETING, INTERNAL_DOC


class ContentStatus(str, Enum):
    SAVED = "saved"
    INGESTING = "ingesting"
    INGESTED = "ingested"
    FAILED = "failed"


def normalize_url(url: str) -> str:
    """Canonicalize a URL for dedup: lowercase scheme/host, drop tracking params, sort the rest,
    strip fragment and trailing slash."""
    parts = urlsplit(url.strip())
    scheme = (parts.scheme or "https").lower()
    netloc = parts.netloc.lower()
    path = parts.path.rstrip("/") or "/"
    kept = sorted((k, v) for k, v in parse_qsl(parts.query, keep_blank_values=False)
                  if k.lower() not in _TRACKING_PARAMS)
    query = urlencode(kept)
    return urlunsplit((scheme, netloc, path, query, ""))


def content_hash_for(url: str) -> str:
    """Stable content fingerprint from the normalized URL (sha256 hex)."""
    return hashlib.sha256(normalize_url(url).encode("utf-8")).hexdigest()


@dataclass
class Content:
    owner_id: str
    source_type: SourceType
    url: str
    content_hash: str
    content_id: str
    title: Optional[str] = None
    status: ContentStatus = ContentStatus.SAVED
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @classmethod
    def create(cls, *, owner_id: str, url: str, source_type: SourceType,
               title: Optional[str] = None) -> "Content":
        chash = content_hash_for(url)
        # Deterministic id from (owner, hash) → re-creating the same content yields the same id.
        content_id = stable_uuid(owner_id, chash)
        return cls(
            owner_id=owner_id,
            source_type=source_type,
            url=normalize_url(url),
            content_hash=chash,
            content_id=content_id,
            title=title,
        )

    @property
    def stream(self) -> str:
        return f"content-{self.content_id}"

    def saved_event(self, *, correlation_id: Optional[str] = None) -> Event:
        """The ``ContentSaved`` domain fact for this aggregate."""
        return new_event(
            type=CONTENT_SAVED,
            stream=self.stream,
            owner_id=self.owner_id,
            correlation_id=correlation_id,
            payload={
                "content_id": self.content_id,
                "source_type": self.source_type.value,
                "url": self.url,
                "content_hash": self.content_hash,
                "title": self.title,
            },
            metadata={"source_service": "ingestion"},
        )

    def to_row(self) -> dict:
        return {
            "content_id": self.content_id,
            "owner_id": self.owner_id,
            "source_type": self.source_type.value,
            "url": self.url,
            "content_hash": self.content_hash,
            "title": self.title,
            "status": self.status.value,
            "created_at": self.created_at,
        }
