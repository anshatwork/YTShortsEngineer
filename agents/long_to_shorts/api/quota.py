"""
agents/long_to_shorts/api/quota.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Subscription quota enforcement — the single gate that makes the product
sellable. Each plan has a monthly job cap (env-tunable); job submission is
rejected with HTTP 402 once the cap is hit.

Enforcement is active only when a Supabase backend is configured (i.e. real
deployments). Local/dev runs without SUPABASE_URL are not gated, so the app
still works out of the box. A transient quota-lookup failure fails *open* (logs
a warning, allows the job) — a DB blip should not reject a legitimate user.
"""

from __future__ import annotations

import logging
import os
from typing import Tuple

from fastapi import HTTPException, status

logger = logging.getLogger(__name__)


def _limits() -> dict:
    """Monthly job caps per plan (override via env for tuning without a deploy)."""
    return {
        "free": int(os.getenv("PLAN_FREE_MONTHLY_JOBS", "3")),
        "pro": int(os.getenv("PLAN_PRO_MONTHLY_JOBS", "100")),
        "business": int(os.getenv("PLAN_BUSINESS_MONTHLY_JOBS", "1000")),
    }


def quota_enforced() -> bool:
    """Enforce only with a Supabase backend, and only if not explicitly disabled."""
    if not os.environ.get("SUPABASE_URL"):
        return False
    return os.getenv("QUOTA_ENABLED", "true").lower() not in ("0", "false", "no")


def usage_snapshot(user_id: str) -> Tuple[str, int, int]:
    """Return (plan, jobs_used_this_period, limit) for *user_id*."""
    from agents.long_to_shorts.api.db.subscription_store import subscription_store

    limits = _limits()
    plan = subscription_store.effective_plan(user_id)
    used = subscription_store.jobs_used_this_period(user_id)
    limit = limits.get(plan, limits["free"])
    return plan, used, limit


def enforce_quota(user_id: str) -> None:
    """Raise HTTP 402 if the user has hit their plan's monthly job cap."""
    if not quota_enforced():
        return
    try:
        plan, used, limit = usage_snapshot(user_id)
    except Exception as exc:  # noqa: BLE001 — fail open on a transient lookup error
        logger.warning(
            "Quota check failed for user=%s (%s); allowing job.",
            user_id, type(exc).__name__,
        )
        return
    if used >= limit:
        logger.info("Quota exceeded — user=%s plan=%s used=%d limit=%d",
                    user_id, plan, used, limit)
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=(
                f"Monthly job limit reached for the '{plan}' plan "
                f"({used}/{limit}). Upgrade your plan to run more jobs."
            ),
        )


__all__ = ["enforce_quota", "usage_snapshot", "quota_enforced"]
