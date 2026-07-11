from datetime import date, datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from soulmatch import insights
from soulmatch.models import Activity, Base, MatchResult, Profile, User

OWNER = 1


def _seed_owner(session: Session) -> None:
    session.add(User(id=OWNER, username="owner@example.com", password_hash="x", role="Member"))
    session.commit()


def _memory_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_incomplete_profiles_flags_missing_fields():
    session = _memory_session()
    _seed_owner(session)
    complete = Profile(owner_user_id=OWNER, 
        full_name="Complete Person", gender="Bride", dob=date(1998, 1, 1), birth_time="10:00",
        birth_place="Chennai", religion="Hindu", caste="Brahmin", current_location="Chennai",
        qualification="B.Tech", occupation="Engineer", height_cm=160, food_preference="Vegetarian",
    )
    incomplete = Profile(owner_user_id=OWNER, full_name="Incomplete Person", gender="Groom")
    session.add_all([complete, incomplete])
    session.commit()

    results = insights.incomplete_profiles(session, OWNER)
    names = {r.profile.full_name: r.missing_fields for r in results}
    assert "Complete Person" not in names
    assert "Incomplete Person" in names
    assert set(names["Incomplete Person"]) == set(insights.IMPORTANT_FIELDS)


def test_pending_horoscope():
    session = _memory_session()
    _seed_owner(session)
    session.add_all([
        Profile(owner_user_id=OWNER, full_name="Has Horoscope", gender="Bride", horoscope_available=True),
        Profile(owner_user_id=OWNER, full_name="No Horoscope", gender="Bride", horoscope_available=False),
        Profile(owner_user_id=OWNER, full_name="Unknown Horoscope", gender="Bride"),
    ])
    session.commit()

    pending = insights.pending_horoscope(session, OWNER)
    names = {p.full_name for p in pending}
    assert names == {"No Horoscope", "Unknown Horoscope"}


def test_top_astrology_matches_sorted_desc():
    session = _memory_session()
    _seed_owner(session)
    bride = Profile(owner_user_id=OWNER, full_name="Bride", gender="Bride")
    groom = Profile(owner_user_id=OWNER, full_name="Groom", gender="Groom")
    session.add_all([bride, groom])
    session.commit()

    session.add_all([
        MatchResult(owner_user_id=OWNER, bride_id=bride.id, groom_id=groom.id, koota_total=18.0),
        MatchResult(owner_user_id=OWNER, bride_id=bride.id, groom_id=groom.id, koota_total=30.0),
        MatchResult(owner_user_id=OWNER, bride_id=bride.id, groom_id=groom.id, koota_total=None),  # not yet scored
    ])
    session.commit()

    top = insights.top_astrology_matches(session, OWNER, limit=5)
    assert [m.koota_total for m in top] == [30.0, 18.0]


def test_stale_cases_excludes_inactive_stages_and_recent_activity():
    session = _memory_session()
    _seed_owner(session)
    today = date(2026, 7, 9)
    old_dt = datetime(2026, 6, 1, tzinfo=timezone.utc)
    recent_dt = datetime(2026, 7, 8, tzinfo=timezone.utc)

    stale_profile = Profile(owner_user_id=OWNER, full_name="Stale", gender="Bride", stage="Interested", created_at=old_dt)
    fresh_profile = Profile(owner_user_id=OWNER, full_name="Fresh", gender="Bride", stage="Interested", created_at=old_dt)
    closed_profile = Profile(owner_user_id=OWNER, full_name="Closed Case", gender="Bride", stage="Marriage", created_at=old_dt)
    session.add_all([stale_profile, fresh_profile, closed_profile])
    session.commit()

    # fresh_profile has recent activity -> not stale; stale_profile has none -> stale
    session.add(Activity(profile_id=fresh_profile.id, event="Followed up", created_at=recent_dt))
    session.commit()

    stale = insights.stale_cases(session, OWNER, days=14, today=today)
    names = {p.full_name for p in stale}
    assert names == {"Stale"}


def test_best_matches_for_ranks_by_practical_score():
    session = _memory_session()
    _seed_owner(session)
    bride = Profile(owner_user_id=OWNER, full_name="Bride", gender="Bride", religion="Hindu", gothram="Bharadwaja",
                     age=26, height_cm=160)
    good_groom = Profile(owner_user_id=OWNER, full_name="Good Groom", gender="Groom", religion="Hindu",
                          gothram="Kashyapa", age=29, height_cm=172, caste="Brahmin")
    bad_groom = Profile(owner_user_id=OWNER, full_name="Bad Groom", gender="Groom", religion="Christian",
                         gothram="Kashyapa", age=29, height_cm=172)
    session.add_all([bride, good_groom, bad_groom])
    session.commit()

    matches = insights.best_matches_for(session, OWNER, bride.id, limit=5)
    assert len(matches) == 2
    top_candidate, top_outcome = matches[0]
    assert top_candidate.full_name == "Good Groom"
    assert top_outcome.mandatory_passed


def test_best_matches_for_unknown_profile_returns_empty():
    session = _memory_session()
    _seed_owner(session)
    assert insights.best_matches_for(session, OWNER, 9999) == []
