from datetime import date

from soulmatch.duplicates import (
    find_all_duplicate_pairs,
    find_duplicate_candidates,
    merge_into_profile,
    merge_profiles,
    name_similarity,
)
from soulmatch.models import Activity, Base, Document, MatchResult, Profile, Task
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


OWNER = 1


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
    session.add(Profile(owner_user_id=OWNER, full_name="Priya Sharma", gender="Bride", phone="9876543210"))
    session.commit()

    candidates = find_duplicate_candidates(session, OWNER, full_name="Priya S", gender="Bride", phone="+91 98765 43210",
    )
    assert len(candidates) == 1
    assert candidates[0].score >= 60
    assert any("phone" in r.lower() for r in candidates[0].reasons)


def test_dob_plus_similar_name_is_duplicate():
    session = _memory_session()
    session.add(Profile(owner_user_id=OWNER, full_name="Priya Sharma", gender="Bride", dob=date(1998, 6, 15)))
    session.commit()

    candidates = find_duplicate_candidates(session, OWNER, full_name="Priya Sharmaa", gender="Bride", dob=date(1998, 6, 15),
    )
    assert len(candidates) == 1
    assert candidates[0].score >= 40


def test_different_gender_not_flagged():
    session = _memory_session()
    session.add(Profile(owner_user_id=OWNER, full_name="Priya Sharma", gender="Bride", phone="9876543210"))
    session.commit()

    candidates = find_duplicate_candidates(session, OWNER, full_name="Priya Sharma", gender="Groom", phone="9876543210",
    )
    assert candidates == []


def test_no_overlap_no_duplicate():
    session = _memory_session()
    session.add(Profile(owner_user_id=OWNER, full_name="Priya Sharma", gender="Bride", phone="9876543210"))
    session.commit()

    candidates = find_duplicate_candidates(session, OWNER, full_name="Anjali Rao", gender="Bride", phone="9111111111",
    )
    assert candidates == []


def test_exclude_id_skips_self():
    session = _memory_session()
    p = Profile(owner_user_id=OWNER, full_name="Priya Sharma", gender="Bride", phone="9876543210")
    session.add(p)
    session.commit()

    candidates = find_duplicate_candidates(session, OWNER, full_name="Priya Sharma", gender="Bride", phone="9876543210",
        exclude_id=p.id,
    )
    assert candidates == []


def test_find_all_duplicate_pairs_finds_and_dedupes_pair():
    session = _memory_session()
    session.add(Profile(owner_user_id=OWNER, full_name="Priya Sharma", gender="Bride", phone="9876543210"))
    session.add(Profile(owner_user_id=OWNER, full_name="Priya Sharma", gender="Bride", phone="9876543210"))
    session.add(Profile(owner_user_id=OWNER, full_name="Anjali Rao", gender="Bride", phone="9111111111"))
    session.commit()

    pairs = find_all_duplicate_pairs(session, OWNER)
    assert len(pairs) == 1  # not reported twice (once as A-B, once as B-A)
    assert pairs[0].score >= 60


def test_find_all_duplicate_pairs_empty_when_no_overlap():
    session = _memory_session()
    session.add(Profile(owner_user_id=OWNER, full_name="Priya Sharma", gender="Bride", phone="9876543210"))
    session.add(Profile(owner_user_id=OWNER, full_name="Anjali Rao", gender="Bride", phone="9111111111"))
    session.commit()

    assert find_all_duplicate_pairs(session, OWNER) == []


def test_merge_into_profile_fills_gaps_without_overwriting():
    session = _memory_session()
    target = Profile(owner_user_id=OWNER, full_name="Priya Sharma", gender="Bride", phone="9876543210")
    session.add(target)
    session.commit()

    filled = merge_into_profile(target, {"phone": "0000000000", "caste": "Brahmin", "religion": None})
    assert "phone" not in filled  # already set, not overwritten
    assert target.phone == "9876543210"
    assert "caste" in filled
    assert target.caste == "Brahmin"
    assert "religion" not in filled  # incoming value was None


def test_merge_into_profile_merges_expectations_dict_key_by_key():
    session = _memory_session()
    target = Profile(owner_user_id=OWNER, full_name="Priya", gender="Bride", expectations={"age": "existing-pref"})
    session.add(target)
    session.commit()

    filled = merge_into_profile(target, {"expectations": {"age": "should-not-overwrite", "location": "Bangalore"}})
    assert "expectations" in filled
    assert target.expectations == {"age": "existing-pref", "location": "Bangalore"}


def test_merge_profiles_moves_children_and_deletes_duplicate():
    session = _memory_session()
    keep = Profile(owner_user_id=OWNER, full_name="Priya Sharma", gender="Bride", phone="9876543210")
    remove = Profile(owner_user_id=OWNER, full_name="Priya Sharma", gender="Bride", caste="Brahmin")
    session.add_all([keep, remove])
    session.commit()

    session.add(Document(profile_id=remove.id, kind="biodata", filename="bio.pdf", path="/tmp/bio.pdf"))
    session.add(Task(profile_id=remove.id, title="Call parents"))
    session.add(Activity(profile_id=remove.id, event="Profile Created"))
    other = Profile(owner_user_id=OWNER, full_name="Ravi", gender="Groom")
    session.add(other)
    session.commit()
    session.add(MatchResult(bride_id=remove.id, groom_id=other.id, practical_score=80))
    session.commit()
    removed_id = remove.id

    summary = merge_profiles(session, keep=keep, remove=remove, created_by_user_id=42)

    assert summary["documents"] == 1
    assert summary["tasks"] == 1
    assert summary["matches"] == 1
    assert "caste" in summary["filled"]
    assert keep.caste == "Brahmin"  # gap filled from the removed profile

    merge_activity = session.query(Activity).filter_by(profile_id=keep.id, event="Profiles Merged").one()
    assert merge_activity.created_by_user_id == 42

    assert session.get(Profile, removed_id) is None  # removed profile is gone
    assert session.query(Document).filter_by(profile_id=keep.id).count() == 1
    assert session.query(Task).filter_by(profile_id=keep.id).count() == 1
    assert session.query(MatchResult).filter_by(bride_id=keep.id).count() == 1
    # the pre-existing activity plus the merge-summary activity now both live on keep
    assert session.query(Activity).filter_by(profile_id=keep.id).count() == 2
