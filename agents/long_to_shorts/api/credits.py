"""
agents/long_to_shorts/api/credits.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Per-operation credit metering — the fine-grained meter that sits on top of the
subscription plans (see billing_routes / subscription_store). Each plan grants a
monthly credit allowance; every metered operation (clip jobs AND edit jobs)
debits its cost. Running out returns HTTP 402.

This is the *primary* meter; the coarse monthly job-count quota (quota.py) is
kept as a secondary safety guard. Balances live in an append-only ledger
(credit_store) so there is no counter to drift out of sync.

Enforcement is opt-in via CREDITS_ENABLED (default off) so local/dev runs and the
existing pipeline tests are unaffected out of the box; production sets it true.
On a transient ledger error the check fails *open* (logs, allows the op) — a DB
blip should not reject a legitimate user (same policy as quota.enforce_quota).

Env
    CREDITS_ENABLED                                    (default "false")
    CREDITS_GRANT_FREE / _PRO / _BUSINESS              monthly allowance per plan
    CREDITS_COST_CLIP / _TTS / _MUSIC / _SPLIT / _THUMBNAIL   per-operation cost
"""

from __future__ import annotations

import logging
import os

from fastapi import HTTPException, status

from agents.long_to_shorts.api.db.credit_store import (
    InsufficientCredits,
    credit_store,
    period_start_utc,
)
from agents.long_to_shorts.api.db.subscription_store import subscription_store

logger = logging.getLogger(__name__)


def _grants() -> dict:
    """Monthly credit allowance per plan (override via env, no deploy needed)."""
    return {
        "free": int(os.getenv("CREDITS_GRANT_FREE", "30")),
        "pro": int(os.getenv("CREDITS_GRANT_PRO", "1000")),
        "business": int(os.getenv("CREDITS_GRANT_BUSINESS", "10000")),
    }


def _costs() -> dict:
    """Credit cost per metered operation."""
    return {
        "clip": int(os.getenv("CREDITS_COST_CLIP", "10")),
        "tts": int(os.getenv("CREDITS_COST_TTS", "2")),
        "music": int(os.getenv("CREDITS_COST_MUSIC", "2")),
        "split": int(os.getenv("CREDITS_COST_SPLIT", "3")),
        "thumbnail": int(os.getenv("CREDITS_COST_THUMBNAIL", "1")),
        "ingest": int(os.getenv("CREDITS_COST_INGEST", "5")),
        "publish": int(os.getenv("CREDITS_COST_PUBLISH", "10")),
    }


def credits_enforced() -> bool:
    """Enforce only when explicitly enabled (opt-in; default off)."""
    return os.getenv("CREDITS_ENABLED", "false").lower() not in ("0", "false", "no", "")


def grant_for_plan(user_id: str, plan: str, *, key: str | None = None) -> bool:
    """Grant a plan's monthly allowance to *user_id* (idempotent on *key*).

    Returns True if a grant was written, False if it was a no-op (already granted
    for this key, or the plan grants nothing)."""
    amount = _grants().get(plan, 0)
    if amount <= 0:
        return False
    return credit_store.grant(
        user_id, amount, reason=f"grant:{plan}", idempotency_key=key
    )


def _ensure_free_grant(user_id: str) -> None:
    """Lazily grant the free allowance once per period. Paid grants arrive via
    payment webhooks; free users have no webhook, so seed them on first use."""
    if subscription_store.effective_plan(user_id) != "free":
        return
    period = period_start_utc()
    grant_for_plan(user_id, "free", key=f"grant:free:{user_id}:{period}")


def enforce_and_debit(user_id: str, op: str) -> None:
    """Debit *op*'s cost from *user_id*, or raise HTTP 402 if the balance is short."""
    if not credits_enforced():
        return
    cost = _costs().get(op, 0)
    if cost <= 0:
        return
    try:
        _ensure_free_grant(user_id)
        credit_store.debit(user_id, cost, reason=op)
    except InsufficientCredits as exc:
        logger.info("Credits exhausted — user=%s op=%s balance=%d cost=%d",
                    user_id, op, exc.balance, exc.cost)
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=(
                f"Not enough credits for this action ({exc.balance} left, "
                f"needs {exc.cost}). Upgrade your plan or top up to continue."
            ),
        )
    except Exception as exc:  # noqa: BLE001 — fail open on a transient ledger error
        logger.warning("Credit check failed for user=%s op=%s (%s); allowing.",
                       user_id, op, type(exc).__name__)
        return


def refund_for_op(user_id: str, op: str, *, key: str | None = None) -> None:
    """Credit *op*'s cost back to *user_id* — called when a metered job fails, so
    a failure does not permanently burn credits. No-op when credits are disabled,
    the op is free, or user_id is unknown. Idempotent on *key* (pass one keyed on
    the job id so a retried failure handler refunds only once). Fails silently on
    a transient ledger error — a failed refund must not crash the runner."""
    if not credits_enforced() or not user_id:
        return
    cost = _costs().get(op, 0)
    if cost <= 0:
        return
    try:
        credit_store.refund(user_id, cost, reason=f"refund:{op}", idempotency_key=key)
        logger.info("Credits refunded — user=%s op=%s amount=%d", user_id, op, cost)
    except Exception as exc:  # noqa: BLE001 — never let a refund failure break teardown
        logger.warning("Credit refund failed for user=%s op=%s (%s).",
                       user_id, op, type(exc).__name__)


def credits_snapshot(user_id: str) -> dict:
    """Return {plan, granted, used, remaining} for *user_id* (for the UI meter)."""
    plan = subscription_store.effective_plan(user_id)
    if credits_enforced():
        _ensure_free_grant(user_id)
    granted = _grants().get(plan, 0)
    remaining = credit_store.balance(user_id)
    used = max(0, granted - remaining)
    return {"plan": plan, "granted": granted, "used": used, "remaining": remaining}


__all__ = [
    "enforce_and_debit",
    "refund_for_op",
    "grant_for_plan",
    "credits_snapshot",
    "credits_enforced",
]
