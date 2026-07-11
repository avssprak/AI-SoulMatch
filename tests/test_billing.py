from datetime import date, datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from soulmatch import billing
from soulmatch.models import AiUsage, Base, Profile, User

OWNER = 1
OTHER = 2


def _memory_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _seed_users(session: Session) -> None:
    session.add_all([
        User(id=OWNER, username="owner@example.com", password_hash="x", role="Member", plan="free"),
        User(id=OTHER, username="other@example.com", password_hash="x", role="Member", plan="free"),
    ])
    session.commit()


def test_record_usage_computes_cost():
    session = _memory_session()
    _seed_users(session)
    row = billing.record_usage(session, OWNER, "extract", tokens_in=1_000_000, tokens_out=1_000_000)
    session.commit()
    # 1M in @ $0.30 + 1M out @ $2.50 = $2.80 -> * USD_INR
    from soulmatch import config
    expected = 2.80 * config.USD_INR
    assert row.cost_estimate_inr == expected


def test_record_usage_rejects_unknown_action():
    session = _memory_session()
    _seed_users(session)
    import pytest
    with pytest.raises(ValueError):
        billing.record_usage(session, OWNER, "bogus", 10, 10)


def test_quota_status_counts_only_current_owner_and_month():
    session = _memory_session()
    _seed_users(session)
    today = date(2026, 7, 15)
    billing.record_usage(session, OWNER, "extract", 100, 100)
    billing.record_usage(session, OWNER, "extract", 100, 100)
    billing.record_usage(session, OTHER, "extract", 100, 100)
    # last month's row for OWNER must not count
    old_row = AiUsage(owner_user_id=OWNER, action="extract", tokens_in=1, tokens_out=1,
                       cost_estimate_inr=0.01, created_at=datetime(2026, 6, 15, tzinfo=timezone.utc))
    session.add(old_row)
    session.commit()

    user = {"id": OWNER, "plan": "free"}
    status = billing.quota_status(session, user, today=today)
    assert status.used == 2
    assert status.limit == billing.PLAN_LIMITS["free"]["ai_actions"]
    assert status.resets_on == date(2026, 8, 1)


def test_require_quota_raises_at_limit():
    session = _memory_session()
    _seed_users(session)
    user = {"id": OWNER, "plan": "free"}
    limit = billing.PLAN_LIMITS["free"]["ai_actions"]
    for _ in range(limit):
        billing.record_usage(session, OWNER, "extract", 1, 1)
    session.commit()

    import pytest
    with pytest.raises(billing.QuotaExceeded):
        billing.require_quota(session, user)


def test_require_quota_ok_below_limit():
    session = _memory_session()
    _seed_users(session)
    user = {"id": OWNER, "plan": "free"}
    status = billing.require_quota(session, user)
    assert not status.exhausted


def test_quota_status_reflects_pro_limit():
    session = _memory_session()
    _seed_users(session)
    user = {"id": OWNER, "plan": "pro"}
    status = billing.quota_status(session, user)
    assert status.limit == billing.PLAN_LIMITS["pro"]["ai_actions"]


def test_failed_llm_call_does_not_consume_quota():
    session = _memory_session()
    _seed_users(session)
    user = {"id": OWNER, "plan": "free"}
    # Simulate: quota checked, LLM call fails, caller must NOT call record_usage.
    billing.require_quota(session, user)
    # no record_usage call here — this is the contract, not code under test directly
    status = billing.quota_status(session, user)
    assert status.used == 0


def test_can_add_profile_at_cap():
    session = _memory_session()
    _seed_users(session)
    limit = billing.PLAN_LIMITS["free"]["profiles"]
    for i in range(limit):
        session.add(Profile(owner_user_id=OWNER, full_name=f"P{i}", gender="Bride"))
    session.commit()

    user = {"id": OWNER, "plan": "free"}
    ok, message = billing.can_add_profile(session, user)
    assert ok is False
    assert "25" in message


def test_can_add_profile_below_cap():
    session = _memory_session()
    _seed_users(session)
    session.add(Profile(owner_user_id=OWNER, full_name="Only one", gender="Bride"))
    session.commit()

    user = {"id": OWNER, "plan": "free"}
    ok, message = billing.can_add_profile(session, user)
    assert ok is True
    assert message == ""


def test_can_add_profile_unlimited_for_plus():
    session = _memory_session()
    _seed_users(session)
    for i in range(100):
        session.add(Profile(owner_user_id=OWNER, full_name=f"P{i}", gender="Bride"))
    session.commit()

    user = {"id": OWNER, "plan": "plus"}
    ok, message = billing.can_add_profile(session, user)
    assert ok is True


def test_can_add_profile_scoped_to_owner():
    session = _memory_session()
    _seed_users(session)
    limit = billing.PLAN_LIMITS["free"]["profiles"]
    for i in range(limit):
        session.add(Profile(owner_user_id=OTHER, full_name=f"P{i}", gender="Bride"))
    session.commit()

    user = {"id": OWNER, "plan": "free"}
    ok, _ = billing.can_add_profile(session, user)
    assert ok is True  # OTHER's profiles must not count against OWNER's cap


def test_plan_gate_flags():
    assert billing.can_use_ai_explanations({"plan": "free"}) is False
    assert billing.can_use_ai_explanations({"plan": "plus"}) is True
    assert billing.can_use_ai_explanations({"plan": "pro"}) is True
    assert billing.can_use_nl_search({"plan": "free"}) is False
    assert billing.can_use_nl_search({"plan": "plus"}) is True


def test_monthly_usage_summary_is_owner_scoped_and_ranked():
    session = _memory_session()
    _seed_users(session)
    billing.record_usage(session, OWNER, "extract", 1_000_000, 0)
    billing.record_usage(session, OTHER, "extract", 100, 0)
    session.commit()

    summary = billing.monthly_usage_summary(session)
    assert summary["by_action"]["extract"] == 2
    assert summary["top_users"][0]["user"] == "owner@example.com"
    assert summary["total_cost_inr"] > 0
