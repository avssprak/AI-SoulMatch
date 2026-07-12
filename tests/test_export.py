"""V3-5-2/V3-5-3 — data export & account deletion. Export completeness is
also a tenancy test: the ZIP for owner A must contain every row A owns and
zero rows belonging to any other tenant."""

import io
import json
import zipfile

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from soulmatch import auth
from soulmatch.documents import save_document
from soulmatch.export import delete_owner_account, export_owner_data_zip
from soulmatch.models import (
    Activity, AiUsage, Base, MatchResult, Profile, RawMessage, Subscription, Task, User,
)


def _memory_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _seed_two_tenants(session: Session) -> tuple[int, int]:
    a = auth.create_user(session, "a@example.com", "correctpass", "Tenant A", "Member")
    b = auth.create_user(session, "b@example.com", "correctpass", "Tenant B", "Member")
    session.flush()
    for owner, tag in ((a.id, "A"), (b.id, "B")):
        bride = Profile(owner_user_id=owner, full_name=f"Bride {tag}", gender="Bride")
        groom = Profile(owner_user_id=owner, full_name=f"Groom {tag}", gender="Groom")
        session.add_all([bride, groom])
        session.flush()
        session.add_all([
            Task(owner_user_id=owner, profile_id=bride.id, title=f"Task {tag}"),
            Activity(owner_user_id=owner, profile_id=bride.id, event=f"Event {tag}"),
            MatchResult(owner_user_id=owner, bride_id=bride.id, groom_id=groom.id, koota_total=20.0),
            RawMessage(owner_user_id=owner, content=f"msg {tag}"),
            AiUsage(owner_user_id=owner, action="extract", tokens_in=10, tokens_out=10, cost_estimate_inr=1.0),
            Subscription(owner_user_id=owner, provider="razorpay", provider_sub_id=f"sub_{tag}", plan="plus"),
        ])
        save_document(session, bride.id, "photo", f"photo_{tag}.jpg", b"fake-image-bytes", owner_user_id=owner)
    session.commit()
    return a.id, b.id


def test_export_zip_contains_every_owned_row_and_zero_foreign_rows():
    session = _memory_session()
    a, b = _seed_two_tenants(session)

    zip_bytes = export_owner_data_zip(session, a)
    zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    names = zf.namelist()

    assert "profiles.json" in names
    profiles = json.loads(zf.read("profiles.json"))
    assert len(profiles) == 2
    assert {p["full_name"] for p in profiles} == {"Bride A", "Groom A"}
    assert all(p["owner_user_id"] == a for p in profiles)

    tasks = json.loads(zf.read("tasks.json"))
    assert len(tasks) == 1 and tasks[0]["title"] == "Task A"

    raw_messages = json.loads(zf.read("raw_messages.json"))
    assert len(raw_messages) == 1 and raw_messages[0]["content"] == "msg A"

    subscriptions = json.loads(zf.read("subscriptions.json"))
    assert len(subscriptions) == 1 and subscriptions[0]["provider_sub_id"] == "sub_A"

    # the uploaded file itself is in the ZIP, and it's tenant A's file, not B's
    file_entries = [n for n in names if n.startswith("files/")]
    assert len(file_entries) == 1
    assert "photo_A.jpg" in file_entries[0]
    assert zf.read(file_entries[0]) == b"fake-image-bytes"


def test_export_zip_dates_are_iso_strings():
    session = _memory_session()
    a, _b = _seed_two_tenants(session)
    zip_bytes = export_owner_data_zip(session, a)
    zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    profiles = json.loads(zf.read("profiles.json"))
    # created_at must serialize as a plain string (dates aren't JSON-native)
    assert isinstance(profiles[0]["created_at"], str)


def test_delete_owner_account_removes_everything_and_only_that_owner():
    session = _memory_session()
    a, b = _seed_two_tenants(session)

    delete_owner_account(session, a)

    assert session.get(User, a) is None
    assert session.scalars(select(Profile).where(Profile.owner_user_id == a)).all() == []
    assert session.scalars(select(Task).where(Task.owner_user_id == a)).all() == []
    assert session.scalars(select(RawMessage).where(RawMessage.owner_user_id == a)).all() == []
    assert session.scalars(select(AiUsage).where(AiUsage.owner_user_id == a)).all() == []
    assert session.scalars(select(Subscription).where(Subscription.owner_user_id == a)).all() == []

    # tenant B is completely untouched
    assert session.get(User, b) is not None
    assert len(session.scalars(select(Profile).where(Profile.owner_user_id == b)).all()) == 2
    assert len(session.scalars(select(Subscription).where(Subscription.owner_user_id == b)).all()) == 1
