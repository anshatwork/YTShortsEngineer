"""Idempotency store for signed Stripe and Razorpay webhook events."""

from __future__ import annotations

import os
import threading


class _MemoryPaymentEventStore:
    def __init__(self) -> None:
        self._seen: set[tuple[str, str]] = set()
        self._lock = threading.Lock()

    def claim(self, provider: str, event_id: str) -> bool:
        with self._lock:
            key = (provider, event_id)
            if key in self._seen:
                return False
            self._seen.add(key)
            return True

    def _clear(self) -> None:
        with self._lock:
            self._seen.clear()


class SupabasePaymentEventStore:
    def claim(self, provider: str, event_id: str) -> bool:
        from agents.long_to_shorts.api.supabase_client import get_worker_client

        try:
            get_worker_client().table("payment_events").insert(
                {"provider": provider, "event_id": event_id}
            ).execute()
            return True
        except Exception as exc:
            text = str(exc).lower()
            if "duplicate" in text or "unique" in text or "23505" in text:
                return False
            raise


def _make_store():
    backend = os.getenv("PAYMENT_EVENT_STORE", "supabase" if os.getenv("SUPABASE_URL") else "memory").lower()
    return SupabasePaymentEventStore() if backend == "supabase" else _MemoryPaymentEventStore()


payment_event_store = _make_store()

__all__ = ["payment_event_store"]
