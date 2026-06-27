"""
agents/long_to_shorts/api/db/subscription_store.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Supabase-backed store for subscription/plan state and usage counting.

A user with no row is on the free plan. Plan rows are written by the worker from
verified payment webhooks (see billing). Usage is counted directly from
``clip_jobs`` (created this calendar month) so there is no separate counter to
drift out of sync.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from agents.long_to_shorts.api.supabase_client import get_worker_client

logger = logging.getLogger(__name__)

_TABLE = "subscriptions"
_JOBS_TABLE = "clip_jobs"
_ACTIVE_STATUSES = ("active", "trialing")


def _month_start_utc() -> str:
    now = datetime.now(tz=timezone.utc)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()


class SupabaseSubscriptionStore:
    def get(self, user_id: str) -> Optional[dict]:
        res = (
            get_worker_client().table(_TABLE)
            .select("*")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        rows = res.data or []
        return rows[0] if rows else None

    def effective_plan(self, user_id: str) -> str:
        """The plan to bill against: the row's plan if its status is active,
        otherwise 'free' (lapsed/canceled subscribers drop to free limits)."""
        row = self.get(user_id)
        if not row:
            return "free"
        if row.get("status") in _ACTIVE_STATUSES:
            return row.get("plan", "free")
        return "free"

    def jobs_used_this_period(self, user_id: str) -> int:
        """Count this user's clip jobs created since the start of the UTC month."""
        res = (
            get_worker_client().table(_JOBS_TABLE)
            .select("job_id", count="exact")
            .eq("user_id", user_id)
            .gte("created_at", _month_start_utc())
            .execute()
        )
        # supabase-py exposes the exact count on the response.
        return res.count or 0

    def find_by_provider_subscription(
        self, provider: str, provider_subscription_id: str
    ) -> Optional[dict]:
        """Locate the row a provider webhook refers to (for status updates)."""
        res = (
            get_worker_client().table(_TABLE)
            .select("*")
            .eq("provider", provider)
            .eq("provider_subscription_id", provider_subscription_id)
            .limit(1)
            .execute()
        )
        rows = res.data or []
        return rows[0] if rows else None

    def update_status(
        self, user_id: str, *, status: str, current_period_end: Optional[str] = None
    ) -> None:
        """Patch status (and optionally period end) for an existing subscriber."""
        patch: dict = {"status": status}
        if current_period_end is not None:
            patch["current_period_end"] = current_period_end
        get_worker_client().table(_TABLE).update(patch).eq("user_id", user_id).execute()
        logger.info("Subscription status — user=%s status=%s", user_id, status)

    def upsert_from_webhook(
        self,
        *,
        user_id: str,
        plan: str,
        status: str,
        provider: str,
        provider_customer_id: Optional[str] = None,
        provider_subscription_id: Optional[str] = None,
        current_period_end: Optional[str] = None,
    ) -> None:
        """Idempotently set a user's plan from a verified payment webhook."""
        row = {
            "user_id": user_id,
            "plan": plan,
            "status": status,
            "provider": provider,
            "provider_customer_id": provider_customer_id,
            "provider_subscription_id": provider_subscription_id,
            "current_period_end": current_period_end,
        }
        get_worker_client().table(_TABLE).upsert(row).execute()
        logger.info(
            "Subscription updated — user=%s plan=%s status=%s provider=%s",
            user_id, plan, status, provider,
        )


subscription_store = SupabaseSubscriptionStore()

__all__ = ["SupabaseSubscriptionStore", "subscription_store"]
