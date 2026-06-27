"""
agents/long_to_shorts/api/billing_routes.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Subscription billing via Stripe (international) and Razorpay (India).

Both use hosted checkout — card data never touches our servers (minimal PCI
scope). Webhooks are the source of truth for plan state: they verify the
provider signature, then write to the subscriptions table (see
subscription_store). Plan resolution is config-driven so adding a tier is an env
change, not a code change.

Endpoints (mounted at /api/v1/billing)
    GET  /plans            Available plans + which providers are configured
    POST /checkout         Start a hosted checkout for {provider, plan}  (auth)
    POST /webhook/stripe   Stripe webhook (signature-verified, no auth)
    POST /webhook/razorpay Razorpay webhook (signature-verified, no auth)

Env
    STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET
    STRIPE_PRICE_PRO, STRIPE_PRICE_BUSINESS              (Stripe price ids)
    RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET, RAZORPAY_WEBHOOK_SECRET
    RAZORPAY_PLAN_PRO, RAZORPAY_PLAN_BUSINESS            (Razorpay plan ids)
    FRONTEND_URL                                         (checkout return urls)
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from agents.long_to_shorts.api.auth import get_current_user_id

logger = logging.getLogger(__name__)

router = APIRouter()

_PAID_PLANS = ("pro", "business")


# ---------------------------------------------------------------------------
# Config helpers — map our plan names <-> provider price/plan ids
# ---------------------------------------------------------------------------

def _stripe_price_for_plan(plan: str) -> Optional[str]:
    return {
        "pro": os.getenv("STRIPE_PRICE_PRO"),
        "business": os.getenv("STRIPE_PRICE_BUSINESS"),
    }.get(plan)


def _plan_for_stripe_price(price_id: str) -> Optional[str]:
    for plan in _PAID_PLANS:
        if _stripe_price_for_plan(plan) == price_id:
            return plan
    return None


def _razorpay_plan_for_plan(plan: str) -> Optional[str]:
    return {
        "pro": os.getenv("RAZORPAY_PLAN_PRO"),
        "business": os.getenv("RAZORPAY_PLAN_BUSINESS"),
    }.get(plan)


def _frontend_base() -> str:
    return (os.getenv("FRONTEND_URL", "").split(",")[0].strip().rstrip("/")
            or "http://localhost:3000")


def _stripe():
    """Return the configured stripe module, or raise 503 if not set up."""
    key = os.getenv("STRIPE_SECRET_KEY")
    if not key:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Stripe is not configured.")
    import stripe  # lazy import

    stripe.api_key = key
    return stripe


def _razorpay_client():
    key_id, key_secret = os.getenv("RAZORPAY_KEY_ID"), os.getenv("RAZORPAY_KEY_SECRET")
    if not (key_id and key_secret):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Razorpay is not configured.")
    import razorpay  # lazy import

    return razorpay.Client(auth=(key_id, key_secret))


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class CheckoutIn(BaseModel):
    provider: str  # "stripe" | "razorpay"
    plan: str      # "pro" | "business"


class CheckoutOut(BaseModel):
    provider: str
    plan: str
    checkout_url: str


# ---------------------------------------------------------------------------
# GET /plans
# ---------------------------------------------------------------------------

@router.get("/plans", summary="Available plans and configured providers")
async def list_plans() -> dict:
    from agents.long_to_shorts.api.quota import _limits

    limits = _limits()
    return {
        "plans": [
            {"id": p, "monthly_jobs": limits.get(p)} for p in ("free",) + _PAID_PLANS
        ],
        "providers": {
            "stripe": bool(os.getenv("STRIPE_SECRET_KEY")),
            "razorpay": bool(os.getenv("RAZORPAY_KEY_ID")),
        },
    }


# ---------------------------------------------------------------------------
# POST /checkout
# ---------------------------------------------------------------------------

@router.post("/checkout", response_model=CheckoutOut, summary="Start hosted checkout")
async def create_checkout(
    body: CheckoutIn,
    user_id: str = Depends(get_current_user_id),
) -> CheckoutOut:
    if body.plan not in _PAID_PLANS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            f"plan must be one of {_PAID_PLANS}")
    base = _frontend_base()

    if body.provider == "stripe":
        stripe = _stripe()
        price = _stripe_price_for_plan(body.plan)
        if not price:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                                f"No Stripe price configured for '{body.plan}'.")
        # client_reference_id + metadata carry our user/plan back via the webhook.
        session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{"price": price, "quantity": 1}],
            client_reference_id=user_id,
            metadata={"user_id": user_id, "plan": body.plan},
            subscription_data={"metadata": {"user_id": user_id, "plan": body.plan}},
            success_url=f"{base}/billing?status=success",
            cancel_url=f"{base}/billing?status=cancelled",
        )
        return CheckoutOut(provider="stripe", plan=body.plan, checkout_url=session.url)

    if body.provider == "razorpay":
        client = _razorpay_client()
        plan_id = _razorpay_plan_for_plan(body.plan)
        if not plan_id:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                                f"No Razorpay plan configured for '{body.plan}'.")
        # notes carry our user/plan back via the webhook; total_count is the max
        # number of billing cycles (12 monthly = 1 year, auto-renew on resubscribe).
        sub = client.subscription.create({
            "plan_id": plan_id,
            "total_count": 12,
            "customer_notify": 1,
            "notes": {"user_id": user_id, "plan": body.plan},
        })
        short_url = sub.get("short_url")
        if not short_url:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY,
                                "Razorpay did not return a checkout URL.")
        return CheckoutOut(provider="razorpay", plan=body.plan, checkout_url=short_url)

    raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                        "provider must be 'stripe' or 'razorpay'")


# ---------------------------------------------------------------------------
# POST /webhook/stripe
# ---------------------------------------------------------------------------

@router.post("/webhook/stripe", summary="Stripe webhook (signature-verified)")
async def stripe_webhook(request: Request) -> dict:
    secret = os.getenv("STRIPE_WEBHOOK_SECRET")
    if not secret:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Stripe webhook not configured.")
    import stripe

    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    try:
        event = stripe.Webhook.construct_event(payload, sig, secret)
    except Exception:  # noqa: BLE001 — bad signature / malformed; never log the body
        logger.warning("Stripe webhook rejected — invalid signature.")
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid signature.")

    etype = event["type"]
    obj = event["data"]["object"]
    logger.info("Stripe webhook — id=%s type=%s", event.get("id"), etype)

    from agents.long_to_shorts.api.db.subscription_store import subscription_store

    if etype == "checkout.session.completed":
        user_id = (obj.get("client_reference_id")
                   or (obj.get("metadata") or {}).get("user_id"))
        plan = (obj.get("metadata") or {}).get("plan")
        if user_id and plan:
            subscription_store.upsert_from_webhook(
                user_id=user_id, plan=plan, status="active", provider="stripe",
                provider_customer_id=obj.get("customer"),
                provider_subscription_id=obj.get("subscription"),
            )
    elif etype in ("customer.subscription.updated", "customer.subscription.deleted"):
        sub_id = obj.get("id")
        row = subscription_store.find_by_provider_subscription("stripe", sub_id) if sub_id else None
        if row:
            new_status = "canceled" if etype.endswith("deleted") else _map_stripe_status(obj.get("status"))
            period_end = obj.get("current_period_end")
            from datetime import datetime, timezone
            cpe = (datetime.fromtimestamp(period_end, tz=timezone.utc).isoformat()
                   if period_end else None)
            subscription_store.update_status(row["user_id"], status=new_status, current_period_end=cpe)

    return {"received": True}


def _map_stripe_status(s: Optional[str]) -> str:
    if s in ("active", "trialing", "past_due", "canceled"):
        return s
    if s in ("incomplete", "incomplete_expired", "unpaid"):
        return "past_due"
    return "canceled"


# ---------------------------------------------------------------------------
# POST /webhook/razorpay
# ---------------------------------------------------------------------------

@router.post("/webhook/razorpay", summary="Razorpay webhook (signature-verified)")
async def razorpay_webhook(request: Request) -> dict:
    secret = os.getenv("RAZORPAY_WEBHOOK_SECRET")
    if not secret:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Razorpay webhook not configured.")

    payload = await request.body()
    sig = request.headers.get("x-razorpay-signature", "")
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        logger.warning("Razorpay webhook rejected — invalid signature.")
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid signature.")

    import json
    event = json.loads(payload)
    etype = event.get("event", "")
    logger.info("Razorpay webhook — type=%s", etype)

    sub_entity = (
        event.get("payload", {}).get("subscription", {}).get("entity", {})
    )
    notes = sub_entity.get("notes") or {}
    user_id = notes.get("user_id")
    plan = notes.get("plan")
    sub_id = sub_entity.get("id")

    from agents.long_to_shorts.api.db.subscription_store import subscription_store

    if etype in ("subscription.activated", "subscription.charged", "subscription.resumed"):
        if user_id and plan:
            subscription_store.upsert_from_webhook(
                user_id=user_id, plan=plan, status="active", provider="razorpay",
                provider_subscription_id=sub_id,
            )
    elif etype in ("subscription.cancelled", "subscription.completed", "subscription.halted"):
        row = (subscription_store.find_by_provider_subscription("razorpay", sub_id)
               if sub_id else None)
        target = row["user_id"] if row else user_id
        if target:
            new_status = "past_due" if etype == "subscription.halted" else "canceled"
            subscription_store.update_status(target, status=new_status)

    return {"received": True}


__all__ = ["router"]
