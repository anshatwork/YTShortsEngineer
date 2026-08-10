"""
agents/long_to_shorts/api/db/credit_store.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Append-only credit ledger store. A user's balance for the current period is the
SUM of their ledger rows (grants +, debits -, refunds +) — there is no mutable
balance column to drift out of sync (same philosophy as counting usage directly
from clip_jobs; see subscription_store).

The active backend depends on the CREDIT_STORE environment variable, mirroring
job_store.py::_make_job_store():

  CREDIT_STORE=supabase  →  SupabaseCreditStore  (requires SUPABASE_* env vars)
  CREDIT_STORE=memory    →  _MemoryCreditStore   (default; no external deps)

Both backends share one surface:

    credit_store.balance(user_id)                       -> int
    credit_store.grant(user_id, amount, reason=..., idempotency_key=...)  -> bool
    credit_store.debit(user_id, amount, reason=...)     -> int  (raises InsufficientCredits)
    credit_store.refund(user_id, amount, reason=...)    -> int

`grant` is idempotent: a repeated call with the same non-null idempotency_key is
a no-op (returns False), so replayed payment webhooks never double-grant.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

_TABLE = "credit_ledger"


class InsufficientCredits(Exception):
    """Raised when a debit would take the balance below zero."""

    def __init__(self, balance: int, cost: int) -> None:
        self.balance = balance
        self.cost = cost
        super().__init__(f"insufficient credits: balance={balance} cost={cost}")


def period_start_utc() -> str:
    """Start of the current UTC calendar month (the period balances are scoped to)."""
    now = datetime.now(tz=timezone.utc)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()


# ---------------------------------------------------------------------------
# In-memory backend (development / testing)
# ---------------------------------------------------------------------------

class _MemoryCreditStore:
    """Thread-safe in-memory ledger keyed by user_id."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # user_id -> list of {amount, kind, reason, idempotency_key, period_start}
        self._rows: Dict[str, List[dict]] = {}
        self._keys: set[str] = set()  # seen idempotency keys (global, like the unique index)

    def _entries(self, user_id: str, period: str) -> List[dict]:
        return [r for r in self._rows.get(user_id, []) if r["period_start"] == period]

    def balance(self, user_id: str) -> int:
        period = period_start_utc()
        with self._lock:
            return sum(r["amount"] for r in self._entries(user_id, period))

    def grant(
        self,
        user_id: str,
        amount: int,
        *,
        reason: str = "",
        idempotency_key: Optional[str] = None,
        period_start: Optional[str] = None,
    ) -> bool:
        with self._lock:
            if idempotency_key is not None and idempotency_key in self._keys:
                return False
            self._rows.setdefault(user_id, []).append({
                "amount": int(amount),
                "kind": "grant",
                "reason": reason,
                "idempotency_key": idempotency_key,
                "period_start": period_start or period_start_utc(),
            })
            if idempotency_key is not None:
                self._keys.add(idempotency_key)
        return True

    def debit(self, user_id: str, amount: int, *, reason: str = "") -> int:
        amount = int(amount)
        period = period_start_utc()
        with self._lock:
            bal = sum(r["amount"] for r in self._entries(user_id, period))
            if bal < amount:
                raise InsufficientCredits(bal, amount)
            self._rows.setdefault(user_id, []).append({
                "amount": -amount,
                "kind": "debit",
                "reason": reason,
                "idempotency_key": None,
                "period_start": period,
            })
            return bal - amount

    def refund(
        self,
        user_id: str,
        amount: int,
        *,
        reason: str = "",
        idempotency_key: Optional[str] = None,
    ) -> int:
        amount = int(amount)
        period = period_start_utc()
        with self._lock:
            if idempotency_key is not None and idempotency_key in self._keys:
                return sum(r["amount"] for r in self._entries(user_id, period))
            self._rows.setdefault(user_id, []).append({
                "amount": amount,
                "kind": "refund",
                "reason": reason,
                "idempotency_key": idempotency_key,
                "period_start": period,
            })
            if idempotency_key is not None:
                self._keys.add(idempotency_key)
            return sum(r["amount"] for r in self._entries(user_id, period))

    # Test/reset helper (mirrors _MemoryJobStore._jobs.clear()).
    def _clear(self) -> None:
        with self._lock:
            self._rows.clear()
            self._keys.clear()


# ---------------------------------------------------------------------------
# Supabase backend (production)
# ---------------------------------------------------------------------------

class SupabaseCreditStore:
    """Supabase-backed ledger; all writes use the service-role key (bypasses RLS)."""

    def _client(self):
        from agents.long_to_shorts.api.supabase_client import get_worker_client
        return get_worker_client()

    def balance(self, user_id: str) -> int:
        period = period_start_utc()
        res = (
            self._client().table(_TABLE)
            .select("amount")
            .eq("user_id", user_id)
            .gte("period_start", period)
            .execute()
        )
        return sum(int(r["amount"]) for r in (res.data or []))

    def grant(
        self,
        user_id: str,
        amount: int,
        *,
        reason: str = "",
        idempotency_key: Optional[str] = None,
        period_start: Optional[str] = None,
    ) -> bool:
        # Cheap pre-check; the DB unique index on idempotency_key is the hard guard
        # against a concurrent replay slipping through.
        if idempotency_key is not None:
            existing = (
                self._client().table(_TABLE)
                .select("id")
                .eq("idempotency_key", idempotency_key)
                .limit(1)
                .execute()
            )
            if existing.data:
                return False
        row = {
            "user_id": user_id,
            "amount": int(amount),
            "kind": "grant",
            "reason": reason,
            "idempotency_key": idempotency_key,
            "period_start": period_start or period_start_utc(),
        }
        try:
            self._client().table(_TABLE).insert(row).execute()
        except Exception as exc:  # noqa: BLE001 — unique-index race lost; already granted
            if idempotency_key is not None:
                logger.info("Credit grant idempotency hit — key=%s (%s)",
                            idempotency_key, type(exc).__name__)
                return False
            raise
        logger.info("Credits granted — user=%s amount=%d reason=%s",
                    user_id, amount, reason)
        return True

    def debit(self, user_id: str, amount: int, *, reason: str = "") -> int:
        amount = int(amount)
        bal = self.balance(user_id)
        if bal < amount:
            raise InsufficientCredits(bal, amount)
        row = {
            "user_id": user_id,
            "amount": -amount,
            "kind": "debit",
            "reason": reason,
            "period_start": period_start_utc(),
        }
        self._client().table(_TABLE).insert(row).execute()
        return bal - amount

    def refund(
        self,
        user_id: str,
        amount: int,
        *,
        reason: str = "",
        idempotency_key: Optional[str] = None,
    ) -> int:
        amount = int(amount)
        if idempotency_key is not None:
            existing = (
                self._client().table(_TABLE)
                .select("id")
                .eq("idempotency_key", idempotency_key)
                .limit(1)
                .execute()
            )
            if existing.data:
                return self.balance(user_id)
        row = {
            "user_id": user_id,
            "amount": amount,
            "kind": "refund",
            "reason": reason,
            "idempotency_key": idempotency_key,
            "period_start": period_start_utc(),
        }
        try:
            self._client().table(_TABLE).insert(row).execute()
        except Exception as exc:  # noqa: BLE001 — unique-index race lost; already refunded
            if idempotency_key is not None:
                logger.info("Credit refund idempotency hit — key=%s (%s)",
                            idempotency_key, type(exc).__name__)
                return self.balance(user_id)
            raise
        return self.balance(user_id)


def _make_credit_store():
    """Pick the backend. Defaults to supabase whenever SUPABASE_URL is set and to
    memory otherwise; CREDIT_STORE=memory|supabase forces either."""
    import os
    default = "supabase" if os.environ.get("SUPABASE_URL") else "memory"
    backend = os.getenv("CREDIT_STORE", default).lower()
    if backend == "supabase":
        return SupabaseCreditStore()
    return _MemoryCreditStore()


credit_store = _make_credit_store()

__all__ = ["credit_store", "InsufficientCredits", "period_start_utc",
           "_MemoryCreditStore", "SupabaseCreditStore"]
