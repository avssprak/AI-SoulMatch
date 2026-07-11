from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from soulmatch import config, documents
from soulmatch.models import Activity, Base, MatchResult, Profile, Task
from soulmatch.profiles import delete_profile, is_match_ready, profile_completeness


@pytest.fixture()
def session(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "UPLOAD_DIR", tmp_path / "uploads")
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def test_delete_profile_removes_profile_and_child_rows(session):
    bride = Profile(full_name="Priya Sharma", gender="Bride")
    groom = Profile(full_name="Ravi Kumar", gender="Groom")
    session.add_all([bride, groom])
    session.commit()

    doc = documents.save_document(session, bride.id, "biodata", "bio.pdf", b"data")
    session.add(Task(profile_id=bride.id, title="Call parents"))
    session.add(Activity(profile_id=bride.id, event="Profile Created"))
    session.add(MatchResult(bride_id=bride.id, groom_id=groom.id, practical_score=80))
    session.commit()
    doc_path = Path(doc.path)
    assert doc_path.exists()
    bride_id = bride.id

    summary = delete_profile(session, bride)

    assert summary == {"id": bride_id, "documents": 1, "tasks": 1, "activities": 1, "matches": 1}
    assert session.get(Profile, bride_id) is None
    assert session.query(Task).count() == 0
    assert session.query(Activity).count() == 0
    assert session.query(MatchResult).count() == 0
    assert not doc_path.exists()  # file removed from disk, not just the DB row
    # the unrelated groom profile is untouched
    assert session.get(Profile, groom.id) is not None


def test_delete_profile_with_no_children_is_a_clean_noop_elsewhere():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        profile = Profile(full_name="Solo Profile", gender="Bride")
        session.add(profile)
        session.commit()
        profile_id = profile.id

        summary = delete_profile(session, profile)

        assert summary == {"id": profile_id, "documents": 0, "tasks": 0, "activities": 0, "matches": 0}
        assert session.get(Profile, profile_id) is None


def test_profile_completeness_empty_profile_is_zero_percent():
    profile = Profile()
    percent, missing = profile_completeness(profile)
    assert percent == 0
    assert "full_name" in missing and "dob" in missing


def test_profile_completeness_fully_filled_is_100_percent():
    profile = Profile(
        full_name="Priya Sharma", gender="Bride", dob=None, birth_time="10:30", birth_place="Bangalore",
        phone="9876543210", religion="Hindu", caste="Brahmin", gothram="Bharadwaja",
        qualification="B.Tech", occupation="Engineer", current_location="Bangalore",
        height_cm=160.0, food_preference="Vegetarian",
    )
    from datetime import date
    profile.dob = date(1998, 6, 15)
    percent, missing = profile_completeness(profile)
    assert percent == 100
    assert missing == []


def test_profile_completeness_partial():
    profile = Profile(full_name="Priya Sharma", gender="Bride")
    percent, missing = profile_completeness(profile)
    assert 0 < percent < 100
    assert "full_name" not in missing
    assert "dob" in missing


def test_is_match_ready_requires_all_three_birth_fields():
    from datetime import date
    profile = Profile(dob=date(1998, 6, 15), birth_time="10:30", birth_place="Bangalore")
    assert is_match_ready(profile) is True

    profile.birth_place = None
    assert is_match_ready(profile) is False

    assert is_match_ready(Profile()) is False
