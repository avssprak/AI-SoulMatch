"""V5-6 email verification at signup — gate self-disables without SMTP config."""

from datetime import timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from soulmatch import auth, mailer
from soulmatch.models import Base, utcnow


def _memory_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


@pytest.fixture
def sent(monkeypatch):
    """Configure the mailer and capture outgoing mail instead of using SMTP."""
    outbox: list[tuple[str, str, str]] = []
    monkeypatch.setattr(mailer, "is_configured", lambda: True)
    monkeypatch.setattr(
        mailer, "send_email", lambda to, subject, body: outbox.append((to, subject, body))
    )
    return outbox


def _signup(session, email="parent@example.com"):
    return auth.register_member(session, email, "longenough1", "Test Parent")


def test_mailer_unconfigured_bypasses_gate():
    # SMTP unset (test env): signup behaves exactly as before V5-6.
    session = _memory_session()
    user = _signup(session)
    assert not mailer.is_configured()
    assert user.email_verified_at is not None
    assert not auth.verification_required(user)


def test_signup_with_mailer_creates_unverified_and_sends_code(sent):
    session = _memory_session()
    user = _signup(session)
    assert user.email_verified_at is None
    assert auth.verification_required(user)
    auth.send_verification_code(session, user)
    assert len(sent) == 1
    assert sent[0][0] == "parent@example.com"
    assert user.verification_code in sent[0][2]
    assert len(user.verification_code) == 6


def test_correct_code_verifies(sent):
    session = _memory_session()
    user = _signup(session)
    auth.send_verification_code(session, user)
    assert auth.verify_email_code(session, user, user.verification_code) == "ok"
    assert user.email_verified_at is not None
    assert user.verification_code is None
    assert not auth.verification_required(user)


def test_wrong_code_then_lockout(sent):
    session = _memory_session()
    user = _signup(session)
    auth.send_verification_code(session, user)
    code = user.verification_code
    for i in range(auth.VERIFICATION_MAX_ATTEMPTS - 1):
        assert auth.verify_email_code(session, user, "000000" if code != "000000" else "111111") == "wrong"
    assert auth.verify_email_code(session, user, "999999" if code != "999999" else "111111") == "locked"
    # Even the right code is refused once locked — a resend is required.
    assert auth.verify_email_code(session, user, code) == "locked"
    # Resend issues a fresh code and clears the lock.
    auth.send_verification_code(session, user)
    assert auth.verify_email_code(session, user, user.verification_code) == "ok"


def test_expired_code(sent):
    session = _memory_session()
    user = _signup(session)
    auth.send_verification_code(session, user)
    late = utcnow() + timedelta(minutes=auth.VERIFICATION_CODE_TTL_MINUTES + 1)
    assert auth.verify_email_code(session, user, user.verification_code, now=late) == "expired"
    assert user.email_verified_at is None


def test_resend_rate_limit(sent):
    session = _memory_session()
    user = _signup(session)
    for _ in range(auth.VERIFICATION_MAX_SENDS_PER_HOUR):
        auth.send_verification_code(session, user)
    with pytest.raises(ValueError, match="Too many codes"):
        auth.send_verification_code(session, user)
    # The cap is a rolling hour — a later send succeeds again.
    auth.send_verification_code(session, user, now=utcnow() + timedelta(hours=1, minutes=1))
    assert len(sent) == auth.VERIFICATION_MAX_SENDS_PER_HOUR + 1


def test_smtp_failure_surfaces_friendly_error(sent, monkeypatch):
    session = _memory_session()
    user = _signup(session)

    def boom(to, subject, body):
        raise ConnectionError("smtp down")

    monkeypatch.setattr(mailer, "send_email", boom)
    with pytest.raises(ValueError, match="couldn't send"):
        auth.send_verification_code(session, user)


def test_admin_created_accounts_are_pre_verified(sent):
    session = _memory_session()
    user = auth.create_user(session, "op@example.com", "longenough1", "Operator", "Member",
                            email="op@example.com")
    session.commit()
    assert not auth.verification_required(user)


def test_pre_existing_users_backfilled_on_migration(tmp_path, monkeypatch):
    # A pre-V5-6 database (users table without the new columns) must come out
    # of the migration with every account marked verified.
    from sqlalchemy import text

    db_path = tmp_path / "old.db"
    old = create_engine(f"sqlite:///{db_path}")
    with old.begin() as conn:
        conn.execute(text(
            "CREATE TABLE users (id INTEGER PRIMARY KEY, username VARCHAR(100),"
            " password_hash VARCHAR(255), role VARCHAR(30))"
        ))
        conn.execute(text(
            "INSERT INTO users (username, password_hash, role) VALUES ('olduser', 'x', 'Member')"
        ))
    old.dispose()

    from soulmatch import db as db_module

    test_engine = create_engine(f"sqlite:///{db_path}")
    monkeypatch.setattr(db_module, "engine", test_engine)
    db_module._apply_column_migrations()
    with test_engine.connect() as conn:
        verified = conn.execute(text("SELECT email_verified_at FROM users")).scalar()
    assert verified is not None
