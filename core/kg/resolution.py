"""
core/kg/resolution.py
~~~~~~~~~~~~~~~~~~~~~~
Entity resolution — one canonical node per real-world entity, not one per mention
(design §6).

Two mechanisms:

1. **Exact resolution (free, at write time).** Resolvable entities MERGE on
   ``(owner_id, norm_name)`` where ``norm_name`` is produced by
   :func:`normalize_name`. So "Kubernetes" mentioned in 500 assets collapses to a
   single ``Concept`` automatically — the ingestion nodes just call
   :func:`canonical_key` when building their ``NodeSpec`` key.

2. **Fuzzy resolution (background, embedding-driven).** Variants that don't
   normalize to the same string ("K8s" vs "Kubernetes") are merged by
   :func:`resolve_label`: for each entity it finds embedding-nearest candidates of
   the same label/owner, and above a cosine threshold folds the duplicate into the
   canonical node via ``repository.redirect_edges`` (which also records
   ``MERGED_INTO`` and appends the alias). This is the same pass that implements
   "unknown → later identified": as embeddings improve, previously-separate nodes
   converge and all their edges follow the merge.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from typing import Any, Callable, Dict, List

from core.kg import repository

logger = logging.getLogger(__name__)

_WS = re.compile(r"\s+")
_PUNCT = re.compile(r"[^\w\s]")


def normalize_name(name: str) -> str:
    """Lowercase, unicode-fold, strip punctuation and collapse whitespace.

    The stable key for resolvable entities. Deterministic so the same surface form
    always maps to the same canonical node regardless of casing/punctuation.
    """
    if not name:
        return ""
    n = unicodedata.normalize("NFKD", name)
    n = "".join(c for c in n if not unicodedata.combining(c))
    n = n.casefold()
    n = _PUNCT.sub(" ", n)
    n = _WS.sub(" ", n).strip()
    return n


def canonical_key(owner_id: str, name: str) -> Dict[str, str]:
    """The MERGE key for a resolvable entity: ``{owner_id, norm_name}``."""
    return {"owner_id": owner_id, "norm_name": normalize_name(name)}


def add_alias(label: str, key: Dict[str, Any], alias: str) -> None:
    """Append *alias* to a node's ``aliases`` list (deduped)."""
    from core.kg.models import safe_identifier
    from core.kg import driver

    label = safe_identifier(label)
    key_map = ", ".join(f"{safe_identifier(k)}: $key.{safe_identifier(k)}" for k in key)
    driver.run_write(
        f"MATCH (n:{label} {{{key_map}}}) "
        "SET n.aliases = apoc.coll.toSet(coalesce(n.aliases, []) + [$alias])",
        {"key": key, "alias": alias},
    )


def merge_entity(
    label: str,
    owner_id: str,
    duplicate_name: str,
    canonical_name: str,
) -> Dict[str, int]:
    """Fold the *duplicate_name* entity into the *canonical_name* one.

    Redirects edges, records ``MERGED_INTO`` and records the duplicate's surface
    form as an alias on the canonical node. Idempotent.
    """
    dup_key = canonical_key(owner_id, duplicate_name)
    canon_key = canonical_key(owner_id, canonical_name)
    if dup_key["norm_name"] == canon_key["norm_name"]:
        return {"out": 0, "in": 0}  # same node already
    result = repository.redirect_edges(label, dup_key, label, canon_key)
    try:
        add_alias(label, canon_key, duplicate_name)
    except Exception as exc:  # noqa: BLE001 — apoc missing; alias is best-effort
        logger.debug("alias write skipped for %s: %s", canonical_name, exc)
    logger.info(
        "merged entity %s '%s' → '%s' (edges: %s)",
        label, duplicate_name, canonical_name, result,
    )
    return result


def resolve_label(
    label: str,
    owner_id: str,
    *,
    embed_text: Callable[[List[str]], List[List[float]]],
    threshold: float = 0.92,
    limit: int = 500,
) -> int:
    """Background fuzzy-merge pass for one (label, owner).

    For each entity with an embedding, find nearest same-label candidates and
    merge any above *threshold* into the lexicographically-earliest name (stable
    canonical choice). Returns the number of merges performed. Best-effort: any
    per-entity failure is logged and skipped so the pass always makes progress.
    """
    from core.kg import driver
    from core.kg.models import safe_identifier

    label = safe_identifier(label)
    rows = driver.run_read(
        f"MATCH (n:{label}) WHERE n.owner_id = $owner_id AND n.embedding IS NOT NULL "
        "AND coalesce(n.resolved, false) = false "
        "RETURN n.norm_name AS norm_name, n.name AS name, n.embedding AS embedding "
        "LIMIT $limit",
        {"owner_id": owner_id, "limit": int(limit)},
    )
    merges = 0
    seen: set = set()
    for row in rows:
        norm = row["norm_name"]
        if norm in seen:
            continue
        vec = row.get("embedding")
        if not vec:
            continue
        try:
            candidates = repository.vector_search(
                label, vec, top_k=5, owner_id=owner_id
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("resolve candidate search failed for %s: %s", norm, exc)
            continue
        for cand in candidates:
            props = cand.get("props", {})
            cand_norm = props.get("norm_name")
            if not cand_norm or cand_norm == norm:
                continue
            if (cand.get("score") or 0.0) < threshold:
                continue
            # Canonical = the lexicographically-smaller norm_name (stable).
            keep, drop = sorted([row["name"], props.get("name", cand_norm)])
            try:
                merge_entity(label, owner_id, drop, keep)
                merges += 1
                seen.add(normalize_name(drop))
            except Exception as exc:  # noqa: BLE001
                logger.debug("merge failed (%s → %s): %s", drop, keep, exc)
        seen.add(norm)
    logger.info("resolve_label %s owner=%s → %d merges", label, owner_id, merges)
    return merges


__all__ = [
    "normalize_name",
    "canonical_key",
    "add_alias",
    "merge_entity",
    "resolve_label",
]
