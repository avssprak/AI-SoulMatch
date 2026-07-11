"""V3-1-3 — cross-tenant isolation tests (see soulmatch/tenancy.py).

Two Members with parallel data; every module-level query path must return
only the calling owner's rows. This file is permanent: any future data-access
change must keep it green. A failure here is a privacy breach, not a bug.
"""

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from soulmatch import billing, duplicates, insights, search, tasks, tenancy
from soulmatch.models import AiUsage, Base, MatchResult, Profile, RawMessage, Task, User


def _memory_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _seed_two_tenants(session: Session) -> tuple[int, int]:
    a = User(username="a@example.com", password_hash="x", role="Member")
    b = User(username="b@example.com", password_hash="x", role="Member")
    session.add_all([a, b])
    session.flush()
    for owner, tag in ((a.id, "A"), (b.id, "B")):
        bride = Profile(owner_user_id=owner, full_name=f"Bride {tag}", gender="Bride",
                        age=27, caste=f"Caste{tag}", current_location=f"City{tag}",
                        phone=f"98765{owner}0000", horoscope_available=False)
        groom = Profile(owner_user_id=owner, full_name=f"Groom {tag}", gender="Groom", age=30)
        session.add_all([bride, groom])
        session.flush()
        session.add_all([
            Task(owner_user_id=owner, profile_id=bride.id, title=f"Call {tag}"),
            MatchResult(owner_user_id=owner, bride_id=bride.id, groom_id=groom.id, koota_total=20.0),
            RawMessage(owner_user_id=owner, content=f"msg {tag}"),
        ])
    session.commit()
    return a.id, b.id


def _profile_ids(session: Session, owner: int) -> set[int]:
    return {p.id for p in session.scalars(
        tenancy.owned(select(Profile), Profile, owner)
    ).all()}


def test_owned_select_isolates_profiles():
    session = _memory_session()
    a, b = _seed_two_tenants(session)
    assert _profile_ids(session, a).isdisjoint(_profile_ids(session, b))
    assert len(_profile_ids(session, a)) == 2


def test_owned_requires_owner_id():
    with pytest.raises(ValueError):
        tenancy.owned(select(Profile), Profile, None)
    with pytest.raises(ValueError):
        tenancy.get_owned(_memory_session(), Profile, 1, None)


def test_get_owned_blocks_cross_tenant_pk_lookup():
    session = _memory_session()
    a, b = _seed_two_tenants(session)
    b_profile_id = next(iter(_profile_ids(session, b)))
    assert tenancy.get_owned(session, Profile, b_profile_id, a) is None
    assert tenancy.get_owned(session, Profile, b_profile_id, b) is not None


def test_tasks_scoped():
    session = _memory_session()
    a, b = _seed_two_tenants(session)
    assert all(t.owner_user_id == a for t in tasks.pending_tasks(session, a))
    assert len(tasks.pending_tasks(session, a)) == 1


def test_insights_scoped():
    session = _memory_session()
    a, b = _seed_two_tenants(session)
    assert all(r.profile.owner_user_id == a for r in insights.incomplete_profiles(session, a))
    assert all(p.owner_user_id == a for p in insights.pending_horoscope(session, a))
    assert all(m.owner_user_id == a for m in insights.top_astrology_matches(session, a))
    assert all(p.owner_user_id == a for p in insights.stale_cases(session, a, days=0))
    b_bride = session.scalar(tenancy.owned(select(Profile).where(Profile.gender == "Bride"), Profile, b))
    # asking for best matches against another tenant's profile returns nothing
    assert insights.best_matches_for(session, a, b_bride.id) == []


def test_search_scoped():
    session = _memory_session()
    a, b = _seed_two_tenants(session)
    results = search.apply_filters(session, a, {"gender": "Bride"})
    assert [p.owner_user_id for p in results] == [a]
    # mock parser must only learn vocabulary (locations/castes) from the owner's rows
    filters = search._mock_parse_query(session, a, "brides in CityB with CasteB")
    assert filters["current_location"] is None
    assert filters["caste"] is None
    filters = search._mock_parse_query(session, a, "brides in CityA")
    assert filters["current_location"] == "CityA"


def test_duplicates_scoped():
    session = _memory_session()
    a, b = _seed_two_tenants(session)
    # tenant A adds someone identical to tenant B's bride — must NOT be flagged
    cands = duplicates.find_duplicate_candidates(
        session, a, full_name="Bride B", gender="Bride", phone=f"98765{b}0000",
    )
    assert cands == []
    pairs = duplicates.find_all_duplicate_pairs(session, a)
    involved = {p.profile_a.owner_user_id for p in pairs} | {p.profile_b.owner_user_id for p in pairs}
    assert involved <= {a}


def test_ai_usage_scoped():
    session = _memory_session()
    a, b = _seed_two_tenants(session)
    billing.record_usage(session, a, "extract", 100, 100)
    billing.record_usage(session, b, "extract", 100, 100)
    billing.record_usage(session, b, "extract", 100, 100)
    session.commit()

    a_rows = session.scalars(tenancy.owned(select(AiUsage), AiUsage, a)).all()
    b_rows = session.scalars(tenancy.owned(select(AiUsage), AiUsage, b)).all()
    assert len(a_rows) == 1
    assert len(b_rows) == 2
    assert all(r.owner_user_id == a for r in a_rows)

    status_a = billing.quota_status(session, {"id": a, "plan": "free"})
    status_b = billing.quota_status(session, {"id": b, "plan": "free"})
    assert status_a.used == 1
    assert status_b.used == 2
