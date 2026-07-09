from datetime import date

from soulmatch.duplicates import find_duplicate_candidates, name_similarity
from soulmatch.models import Base, Profile
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def _memory_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_name_similarity_basic():
    assert name_similarity("Priya Sharma", "Priya Sharma") == 1.0
    assert name_similarity("Priya Sharma", "priya   sharma") == 1.0
    assert name_similarity("Priya Sharma", "Rahul Verma") < 0.82  # below NAME_MATCH_THRESHOLD
    assert name_similarity(None, "Priya") == 0.0


def test_exact_phone_match_is_strong_duplicate():
    session = _memory_session()
    session.add(Profile(full_name="Priya Sharma", gender="Bride", phone="9876543210"))
    session.commit()

    candidates = find_duplicate_candidates(
        session, full_name="Priya S", gender="Bride", phone="+91 98765 43210",
    )
    assert len(candidates) == 1
    assert candidates[0].score >= 60
    assert any("phone" in r.lower() for r in candidates[0].reasons)


def test_dob_plus_similar_name_is_duplicate():
    session = _memory_session()
    session.add(Profile(full_name="Priya Sharma", gender="Bride", dob=date(1998, 6, 15)))
    session.commit()

    candidates = find_duplicate_candidates(
        session, full_name="Priya Sharmaa", gender="Bride", dob=date(1998, 6, 15),
    )
    assert len(candidates) == 1
    assert candidates[0].score >= 40


def test_different_gender_not_flagged():
    session = _memory_session()
    session.add(Profile(full_name="Priya Sharma", gender="Bride", phone="9876543210"))
    session.commit()

    candidates = find_duplicate_candidates(
        session, full_name="Priya Sharma", gender="Groom", phone="9876543210",
    )
    assert candidates == []


def test_no_overlap_no_duplicate():
    session = _memory_session()
    session.add(Profile(full_name="Priya Sharma", gender="Bride", phone="9876543210"))
    session.commit()

    candidates = find_duplicate_candidates(
        session, full_name="Anjali Rao", gender="Bride", phone="9111111111",
    )
    assert candidates == []


def test_exclude_id_skips_self():
    session = _memory_session()
    p = Profile(full_name="Priya Sharma", gender="Bride", phone="9876543210")
    session.add(p)
    session.commit()

    candidates = find_duplicate_candidates(
        session, full_name="Priya Sharma", gender="Bride", phone="9876543210",
        exclude_id=p.id,
    )
    assert candidates == []
