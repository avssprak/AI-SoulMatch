"""Module 16 — Payments (V3-3): Razorpay (INR/UPI Autopay) checkout +
Stripe (USD/NRI) checkout, and the webhook handlers that turn gateway events
into plan changes.

Deliberately built on `requests` (already a dependency) rather than the
razorpay/stripe SDKs, to keep this sprint's dependency footprint at zero —
both gateways' REST APIs are simple enough that the SDKs buy little here.

Webhook signature verification (`verify_*_signature`) happens in the HTTP
layer (webhook_server.py), NOT in the `apply_*_event` functions below —
those are pure functions over an already-parsed, already-verified event
dict + a Session, exactly so they can be unit-tested against fixture JSON
without any network or cryptography involved (see V3_PLAN.md V3-3-6).
"""

from __future__ import annotations

import hashlib
import hmac
import time
from datetime import datetime, timedelta, timezone

import requests
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import billing, config
from .models import Subscription, User, WebhookEvent

RAZORPAY_API = "https://api.razorpay.com/v1"
STRIPE_API = "https://api.stripe.com/v1"

# Razorpay subscription-lifecycle events we act on -> (new plan_status, grace).
_RAZORPAY_STATUS_MAP = {
    "subscription.activated": ("active", None),
    "subscription.charged": ("active", None),
    "subscription.halted": ("past_due", billing.GRACE_DAYS),
    "subscription.cancelled": ("free", None),
}

# Same idea for Stripe.
_STRIPE_STATUS_MAP = {
    "checkout.session.completed": ("active", None),
    "invoice.paid": ("active", None),
    "invoice.payment_failed": ("past_due", billing.GRACE_DAYS),
    "customer.subscription.deleted": ("free", None),
}


# --- idempotency -------------------------------------------------------------

def is_new_event(session: Session, provider: str, event_id: str) -> bool:
    """True and records the event if this (provider, event_id) hasn't been
    processed before; False (and no write) if it's a duplicate delivery —
    gateways retry webhooks, so every apply_*_event call must go through
    this first."""
    existing = session.scalar(
        select(WebhookEvent).where(WebhookEvent.provider == provider, WebhookEvent.event_id == event_id)
    )
    if existing is not None:
        return False
    session.add(WebhookEvent(provider=provider, event_id=event_id))
    session.commit()
    return True


# --- Razorpay ----------------------------------------------------------------

def verify_razorpay_signature(raw_body: bytes, signature: str, secret: str) -> bool:
    if not secret or not signature:
        return False
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def create_razorpay_subscription_checkout(owner_id: int, plan: str, interval: str) -> str:
    """Create a Razorpay Subscription and return its checkout short_url.
    Raises PaymentConfigError if Razorpay isn't configured yet (V3-3-2 is a
    [HUMAN] task: create the account, the four plans, and the webhook)."""
    entry = billing.price_entry(plan, interval, "INR")
    plan_id = entry["provider_price_id"]
    if not config.RAZORPAY_KEY_ID or not config.RAZORPAY_KEY_SECRET or not plan_id:
        raise billing.PaymentConfigError(
            "Razorpay isn't configured yet — contact support@redprana.com to subscribe for now."
        )
    resp = requests.post(
        f"{RAZORPAY_API}/subscriptions",
        auth=(config.RAZORPAY_KEY_ID, config.RAZORPAY_KEY_SECRET),
        json={
            "plan_id": plan_id,
            "customer_notify": 1,
            # Razorpay requires a finite cycle count, and total_count counts
            # BILLING CYCLES, not months — 120 monthly cycles is 10 years, but
            # the same 120 on an annual plan is 120 years, which the API 400s
            # on. 10 cycles gives an annual plan the same ~10-year horizon.
            "total_count": 10 if interval == "annual" else 120,
            "notes": {"owner_user_id": str(owner_id), "plan": plan, "interval": interval},
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["short_url"]


def apply_razorpay_event(session: Session, event: dict) -> None:
    """Pure event application — call only after verify_razorpay_signature()
    and is_new_event() have both passed."""
    event_type = event.get("event")
    if event_type not in _RAZORPAY_STATUS_MAP:
        return
    entity = (event.get("payload") or {}).get("subscription", {}).get("entity", {})
    sub_id = entity.get("id")
    if not sub_id:
        return
    notes = entity.get("notes") or {}
    owner_id = int(notes["owner_user_id"]) if notes.get("owner_user_id") else None
    plan = notes.get("plan")
    interval = notes.get("interval")

    sub = session.scalar(select(Subscription).where(Subscription.provider_sub_id == sub_id))
    if sub is None:
        if owner_id is None:
            return  # can't attribute this subscription to any tenant — drop it
        sub = Subscription(provider="razorpay", provider_sub_id=sub_id, owner_user_id=owner_id)
        session.add(sub)
    if plan:
        sub.plan = plan
    if interval:
        sub.interval = interval

    new_status, grace_days = _RAZORPAY_STATUS_MAP[event_type]
    sub.status = new_status
    _apply_status_to_user(session, sub.owner_user_id, sub.plan, new_status, grace_days)
    session.commit()


# --- Stripe --------------------------------------------------------------------

def verify_stripe_signature(raw_body: bytes, sig_header: str, secret: str, *, tolerance_seconds: int = 300) -> bool:
    if not secret or not sig_header:
        return False
    parts = dict(p.split("=", 1) for p in sig_header.split(",") if "=" in p)
    timestamp, v1 = parts.get("t"), parts.get("v1")
    if not timestamp or not v1:
        return False
    signed_payload = f"{timestamp}.{raw_body.decode('utf-8')}"
    expected = hmac.new(secret.encode(), signed_payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, v1):
        return False
    return abs(time.time() - int(timestamp)) <= tolerance_seconds


def create_stripe_checkout_session(owner_id: int, plan: str, interval: str) -> str:
    """Create a Stripe Checkout Session (subscription mode) and return its
    hosted checkout URL. Raises PaymentConfigError if Stripe isn't
    configured yet (V3-3-3 is a [HUMAN] task)."""
    entry = billing.price_entry(plan, interval, "USD")
    price_id = entry["provider_price_id"]
    if not config.STRIPE_SECRET_KEY or not price_id:
        raise billing.PaymentConfigError(
            "Stripe isn't configured yet — contact support@redprana.com to subscribe for now."
        )
    # metadata is set on both the Session and the Subscription it creates so
    # every downstream webhook (checkout.session.completed, invoice.*,
    # customer.subscription.deleted) can attribute the event to a tenant
    # without a second API call back to Stripe.
    meta = {"owner_user_id": str(owner_id), "plan": plan, "interval": interval}
    data = {
        "mode": "subscription",
        "line_items[0][price]": price_id,
        "line_items[0][quantity]": "1",
        "success_url": f"{config.APP_BASE_URL}/?checkout=success",
        "cancel_url": f"{config.APP_BASE_URL}/?checkout=cancelled",
        "client_reference_id": str(owner_id),
        **{f"metadata[{k}]": v for k, v in meta.items()},
        **{f"subscription_data[metadata][{k}]": v for k, v in meta.items()},
    }
    resp = requests.post(
        f"{STRIPE_API}/checkout/sessions",
        auth=(config.STRIPE_SECRET_KEY, ""),
        data=data,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["url"]


def _stripe_object_metadata(obj: dict) -> dict:
    """checkout.session.completed / customer.subscription.deleted carry
    `metadata` directly. invoice.* events carry it under
    `subscription_details.metadata` (Stripe API 2022-11-15+); fall back to
    top-level `metadata` for older payload shapes."""
    return obj.get("metadata") or (obj.get("subscription_details") or {}).get("metadata") or {}


def apply_stripe_event(session: Session, event: dict) -> None:
    """Pure event application — call only after verify_stripe_signature()
    and is_new_event() have both passed."""
    event_type = event.get("type")
    if event_type not in _STRIPE_STATUS_MAP:
        return
    obj = (event.get("data") or {}).get("object") or {}
    meta = _stripe_object_metadata(obj)
    owner_id = int(meta["owner_user_id"]) if meta.get("owner_user_id") else (
        int(obj["client_reference_id"]) if obj.get("client_reference_id") else None
    )
    if owner_id is None:
        return
    plan, interval = meta.get("plan"), meta.get("interval")
    sub_id = obj.get("subscription") or obj.get("id")
    if not sub_id:
        return

    sub = session.scalar(select(Subscription).where(Subscription.provider_sub_id == sub_id))
    if sub is None:
        sub = Subscription(provider="stripe", provider_sub_id=sub_id, owner_user_id=owner_id)
        session.add(sub)
    if plan:
        sub.plan = plan
    if interval:
        sub.interval = interval

    new_status, grace_days = _STRIPE_STATUS_MAP[event_type]
    sub.status = new_status
    _apply_status_to_user(session, owner_id, sub.plan, new_status, grace_days)
    session.commit()


# --- shared lifecycle application -------------------------------------------

def _latest_subscription(session: Session, owner_id: int) -> Subscription | None:
    return session.scalar(
        select(Subscription).where(Subscription.owner_user_id == owner_id)
        .order_by(Subscription.updated_at.desc())
    )


def cancel_subscription_at_period_end(session: Session, owner_id: int) -> None:
    """Used by the Pause action on My Plan: tells the gateway to stop
    billing at the end of the current period. The local plan_status flip
    to 'paused' (billing.pause_subscription) happens separately and takes
    effect immediately, ahead of the gateway's own cancellation webhook."""
    sub = _latest_subscription(session, owner_id)
    if sub is None:
        raise billing.PaymentConfigError("No subscription found to pause — contact support@redprana.com.")
    if sub.provider == "razorpay":
        if not config.RAZORPAY_KEY_ID:
            raise billing.PaymentConfigError("Razorpay isn't configured — contact support@redprana.com.")
        requests.post(
            f"{RAZORPAY_API}/subscriptions/{sub.provider_sub_id}/cancel",
            auth=(config.RAZORPAY_KEY_ID, config.RAZORPAY_KEY_SECRET),
            json={"cancel_at_cycle_end": 1}, timeout=30,
        ).raise_for_status()
    elif sub.provider == "stripe":
        if not config.STRIPE_SECRET_KEY:
            raise billing.PaymentConfigError("Stripe isn't configured — contact support@redprana.com.")
        requests.post(
            f"{STRIPE_API}/subscriptions/{sub.provider_sub_id}",
            auth=(config.STRIPE_SECRET_KEY, ""),
            data={"cancel_at_period_end": "true"}, timeout=30,
        ).raise_for_status()


def _apply_status_to_user(session: Session, owner_id: int, plan: str | None, new_status: str, grace_days: int | None) -> None:
    user = session.get(User, owner_id)
    if user is None:
        return
    if new_status == "active":
        if plan:
            user.plan = plan
        user.plan_status = "active"
        user.plan_grace_until = None
    elif new_status == "past_due":
        user.plan_status = "past_due"
        # Stored naive-UTC: SQLite drops tzinfo on round-trip, and comparing
        # a tz-aware "now" against a value that comes back naive raises
        # TypeError — keep every write/read of this column naive-UTC so
        # billing.sync_plan_status's comparison is always apples-to-apples.
        user.plan_grace_until = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=grace_days or billing.GRACE_DAYS)
    elif new_status == "free":
        user.plan = "free"
        user.plan_status = "free"
        user.plan_grace_until = None
