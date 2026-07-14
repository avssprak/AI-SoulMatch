"""V3-3-6 — payments: signature verification, idempotency, and pure webhook
event application against fixture JSON. No live gateway calls anywhere here.
"""

import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from soulmatch import billing, config, payments
from soulmatch.models import Base, Subscription, User, WebhookEvent

FIXTURES = Path(__file__).parent / "fixtures"
OWNER = 1


def _memory_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _seed_owner(session: Session) -> None:
    session.add(User(id=OWNER, username="owner@example.com", password_hash="x", role="Member", plan="free"))
    session.commit()


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


# --- signature verification --------------------------------------------------

# --- subscription creation: total_count must fit the billing interval --------
# Razorpay's total_count is a count of BILLING CYCLES, not months — reusing
# the same value for monthly and annual plans asks Razorpay for a 120-year
# subscription on the annual path and the API 400s (found live 2026-07-14).

def _mock_post(monkeypatch, captured: dict):
    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"short_url": "https://rzp.io/i/mock"}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["json"] = kwargs.get("json")
        return _Resp()

    monkeypatch.setattr(payments.requests, "post", fake_post)


def test_razorpay_monthly_uses_120_cycles(monkeypatch):
    monkeypatch.setattr(config, "RAZORPAY_KEY_ID", "key_id")
    monkeypatch.setattr(config, "RAZORPAY_KEY_SECRET", "key_secret")
    monkeypatch.setattr(config, "RAZORPAY_PLAN_PLUS_MONTHLY", "plan_monthly")
    captured: dict = {}
    _mock_post(monkeypatch, captured)
    payments.create_razorpay_subscription_checkout(OWNER, "plus", "monthly")
    assert captured["json"]["total_count"] == 120


def test_razorpay_annual_uses_10_cycles_not_120(monkeypatch):
    monkeypatch.setattr(config, "RAZORPAY_KEY_ID", "key_id")
    monkeypatch.setattr(config, "RAZORPAY_KEY_SECRET", "key_secret")
    monkeypatch.setattr(config, "RAZORPAY_PLAN_PLUS_ANNUAL", "plan_annual")
    captured: dict = {}
    _mock_post(monkeypatch, captured)
    payments.create_razorpay_subscription_checkout(OWNER, "plus", "annual")
    assert captured["json"]["total_count"] == 10


def test_razorpay_signature_roundtrip():
    body = b'{"event":"subscription.activated"}'
    secret = "whsec_test"
    sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert payments.verify_razorpay_signature(body, sig, secret)
    assert not payments.verify_razorpay_signature(body, "bogus", secret)
    assert not payments.verify_razorpay_signature(body, sig, "wrong-secret")
    assert not payments.verify_razorpay_signature(body, "", secret)


def test_stripe_signature_roundtrip():
    body = b'{"type":"checkout.session.completed"}'
    secret = "whsec_test"
    timestamp = str(int(time.time()))
    signed_payload = f"{timestamp}.{body.decode()}"
    v1 = hmac.new(secret.encode(), signed_payload.encode(), hashlib.sha256).hexdigest()
    header = f"t={timestamp},v1={v1}"
    assert payments.verify_stripe_signature(body, header, secret)
    assert not payments.verify_stripe_signature(body, f"t={timestamp},v1=bogus", secret)
    assert not payments.verify_stripe_signature(body, header, "wrong-secret")


def test_stripe_signature_rejects_stale_timestamp():
    body = b'{"type":"checkout.session.completed"}'
    secret = "whsec_test"
    old_timestamp = str(int(time.time()) - 3600)  # 1 hour old
    signed_payload = f"{old_timestamp}.{body.decode()}"
    v1 = hmac.new(secret.encode(), signed_payload.encode(), hashlib.sha256).hexdigest()
    header = f"t={old_timestamp},v1={v1}"
    assert not payments.verify_stripe_signature(body, header, secret, tolerance_seconds=300)


# --- idempotency --------------------------------------------------------------

def test_is_new_event_only_true_once():
    session = _memory_session()
    assert payments.is_new_event(session, "stripe", "evt_1") is True
    assert payments.is_new_event(session, "stripe", "evt_1") is False
    # same event id, different provider -> distinct
    assert payments.is_new_event(session, "razorpay", "evt_1") is True
    assert session.scalar(select(WebhookEvent)) is not None


# --- start_checkout: switching plan/interval must not double-bill -----------
# create_*_checkout always starts a brand-new gateway subscription without
# touching whatever the member already had — left alone, an interval switch
# or plan upgrade left two live subscriptions both billing the member
# (found immediately after shipping the V5-7 interval-switch button).

def _mock_post_sequence(monkeypatch):
    calls: list[str] = []

    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"short_url": "https://rzp.io/i/mock"}

    def fake_post(url, **kwargs):
        calls.append(url)
        return _Resp()

    monkeypatch.setattr(payments.requests, "post", fake_post)
    return calls


def test_start_checkout_cancels_active_subscription_first(monkeypatch):
    session = _memory_session()
    _seed_owner(session)
    payments.apply_razorpay_event(session, _load("razorpay_subscription_activated.json"))  # plus/monthly, active
    monkeypatch.setattr(config, "RAZORPAY_KEY_ID", "key_id")
    monkeypatch.setattr(config, "RAZORPAY_KEY_SECRET", "key_secret")
    monkeypatch.setattr(config, "RAZORPAY_PLAN_PLUS_ANNUAL", "plan_annual")
    calls = _mock_post_sequence(monkeypatch)

    payments.start_checkout(session, OWNER, "plus", "annual", "INR", cancel_existing=True)

    assert len(calls) == 2
    assert calls[0].endswith("/subscriptions/sub_test_001/cancel")  # cancel happens first
    assert calls[1].endswith("/subscriptions")  # then the new one is created


def test_start_checkout_skips_cancel_when_no_active_subscription(monkeypatch):
    session = _memory_session()
    _seed_owner(session)  # free — no subscription at all
    monkeypatch.setattr(config, "RAZORPAY_KEY_ID", "key_id")
    monkeypatch.setattr(config, "RAZORPAY_KEY_SECRET", "key_secret")
    monkeypatch.setattr(config, "RAZORPAY_PLAN_PLUS_MONTHLY", "plan_monthly")
    calls = _mock_post_sequence(monkeypatch)

    payments.start_checkout(session, OWNER, "plus", "monthly", "INR", cancel_existing=True)

    assert len(calls) == 1  # no cancel call — nothing to cancel
    assert calls[0].endswith("/subscriptions")


def test_start_checkout_skips_cancel_when_flag_is_false(monkeypatch):
    session = _memory_session()
    _seed_owner(session)
    payments.apply_razorpay_event(session, _load("razorpay_subscription_activated.json"))
    monkeypatch.setattr(config, "RAZORPAY_KEY_ID", "key_id")
    monkeypatch.setattr(config, "RAZORPAY_KEY_SECRET", "key_secret")
    monkeypatch.setattr(config, "RAZORPAY_PLAN_PLUS_MONTHLY", "plan_monthly")
    calls = _mock_post_sequence(monkeypatch)

    payments.start_checkout(session, OWNER, "plus", "monthly", "INR", cancel_existing=False)

    assert len(calls) == 1
    assert calls[0].endswith("/subscriptions")


def test_start_checkout_aborts_new_subscription_if_cancel_fails(monkeypatch):
    session = _memory_session()
    _seed_owner(session)
    payments.apply_razorpay_event(session, _load("razorpay_subscription_activated.json"))
    monkeypatch.setattr(config, "RAZORPAY_KEY_ID", "")  # cancel_subscription_at_period_end raises
    calls = _mock_post_sequence(monkeypatch)

    with pytest.raises(billing.PaymentConfigError):
        payments.start_checkout(session, OWNER, "plus", "annual", "INR", cancel_existing=True)
    assert calls == []  # never got as far as creating the new subscription


# --- current_billing_interval (V5-7: same-plan interval switch on My Plan) ---

def test_current_billing_interval_none_for_free_user():
    session = _memory_session()
    _seed_owner(session)
    assert payments.current_billing_interval(session, OWNER) is None


def test_current_billing_interval_reflects_latest_subscription():
    session = _memory_session()
    _seed_owner(session)
    payments.apply_razorpay_event(session, _load("razorpay_subscription_activated.json"))
    assert payments.current_billing_interval(session, OWNER) == "monthly"


# --- Razorpay event application ----------------------------------------------

def test_razorpay_activated_creates_subscription_and_activates_user():
    session = _memory_session()
    _seed_owner(session)
    event = _load("razorpay_subscription_activated.json")
    payments.apply_razorpay_event(session, event)

    sub = session.scalar(select(Subscription).where(Subscription.provider_sub_id == "sub_test_001"))
    assert sub is not None
    assert sub.owner_user_id == OWNER
    assert sub.plan == "plus" and sub.interval == "monthly"
    assert sub.status == "active"

    user = session.get(User, OWNER)
    assert user.plan == "plus"
    assert user.plan_status == "active"
    assert user.plan_grace_until is None


def test_razorpay_halted_sets_past_due_with_grace():
    session = _memory_session()
    _seed_owner(session)
    payments.apply_razorpay_event(session, _load("razorpay_subscription_activated.json"))
    before = datetime.now(timezone.utc).replace(tzinfo=None)
    payments.apply_razorpay_event(session, _load("razorpay_subscription_halted.json"))

    user = session.get(User, OWNER)
    assert user.plan_status == "past_due"
    assert user.plan_grace_until is not None
    assert user.plan_grace_until > before + timedelta(days=6)


def test_razorpay_cancelled_downgrades_to_free():
    session = _memory_session()
    _seed_owner(session)
    payments.apply_razorpay_event(session, _load("razorpay_subscription_activated.json"))
    payments.apply_razorpay_event(session, _load("razorpay_subscription_cancelled.json"))

    user = session.get(User, OWNER)
    assert user.plan == "free"
    assert user.plan_status == "free"


def test_razorpay_unknown_event_type_is_ignored():
    session = _memory_session()
    _seed_owner(session)
    payments.apply_razorpay_event(session, {"event": "payment.captured", "payload": {}})
    assert session.scalar(select(Subscription)) is None


def test_razorpay_missing_owner_notes_is_dropped_not_crashed():
    session = _memory_session()
    _seed_owner(session)
    event = _load("razorpay_subscription_activated.json")
    event["payload"]["subscription"]["entity"]["notes"] = {}
    payments.apply_razorpay_event(session, event)  # must not raise
    assert session.scalar(select(Subscription)) is None


# --- Stripe event application -------------------------------------------------

def test_stripe_checkout_completed_activates_user():
    session = _memory_session()
    _seed_owner(session)
    payments.apply_stripe_event(session, _load("stripe_checkout_session_completed.json"))

    sub = session.scalar(select(Subscription).where(Subscription.provider_sub_id == "sub_stripe_test_001"))
    assert sub is not None and sub.provider == "stripe" and sub.plan == "plus"
    user = session.get(User, OWNER)
    assert user.plan == "plus" and user.plan_status == "active"


def test_stripe_invoice_payment_failed_sets_past_due():
    session = _memory_session()
    _seed_owner(session)
    payments.apply_stripe_event(session, _load("stripe_checkout_session_completed.json"))
    payments.apply_stripe_event(session, _load("stripe_invoice_payment_failed.json"))

    user = session.get(User, OWNER)
    assert user.plan_status == "past_due"
    assert user.plan_grace_until is not None


def test_stripe_subscription_deleted_downgrades_to_free():
    session = _memory_session()
    _seed_owner(session)
    payments.apply_stripe_event(session, _load("stripe_checkout_session_completed.json"))
    payments.apply_stripe_event(session, _load("stripe_subscription_deleted.json"))

    user = session.get(User, OWNER)
    assert user.plan == "free" and user.plan_status == "free"


def test_stripe_unknown_event_type_is_ignored():
    session = _memory_session()
    _seed_owner(session)
    payments.apply_stripe_event(session, {"type": "customer.created", "data": {"object": {}}})
    assert session.scalar(select(Subscription)) is None


# --- end-to-end idempotent replay --------------------------------------------

def test_duplicate_webhook_delivery_applies_once():
    session = _memory_session()
    _seed_owner(session)
    event = _load("razorpay_subscription_activated.json")

    for _ in range(3):  # simulate 3 retried deliveries of the same event
        if payments.is_new_event(session, "razorpay", "sub_test_001-activated"):
            payments.apply_razorpay_event(session, event)

    assert session.scalar(select(WebhookEvent)) is not None
    subs = session.scalars(select(Subscription)).all()
    assert len(subs) == 1  # not duplicated
