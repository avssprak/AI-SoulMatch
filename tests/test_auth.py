from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from soulmatch import auth
from soulmatch.models import Base, User


def _memory_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_hash_and_verify_roundtrip():
    hashed = auth.hash_password("correct-horse-battery-staple")
    assert auth.verify_password("correct-horse-battery-staple", hashed)
    assert not auth.verify_password("wrong-password", hashed)


def test_hash_is_salted_differently_each_time():
    h1 = auth.hash_password("same-password")
    h2 = auth.hash_password("same-password")
    assert h1 != h2  # different random salts
    assert auth.verify_password("same-password", h1)
    assert auth.verify_password("same-password", h2)


def test_verify_password_rejects_malformed_hash():
    assert not auth.verify_password("anything", "not-a-valid-hash-format")


def test_create_user_and_authenticate():
    session = _memory_session()
    auth.create_user(session, "member1", "secretpass1", "Test Member", "Member")
    session.commit()

    user = auth.authenticate(session, "member1", "secretpass1")  # case-insensitive username
    assert user is not None
    assert user.role == "Member"
    assert user.last_login is not None


def test_authenticate_wrong_password_fails():
    session = _memory_session()
    auth.create_user(session, "user1", "correctpass", None, "Member")
    session.commit()

    assert auth.authenticate(session, "user1", "wrongpass") is None


def test_authenticate_unknown_username_fails():
    session = _memory_session()
    assert auth.authenticate(session, "nobody", "whatever") is None


def test_authenticate_inactive_user_fails():
    session = _memory_session()
    user = auth.create_user(session, "user1", "correctpass", None, "Member")
    session.commit()
    user.is_active = False
    session.commit()

    assert auth.authenticate(session, "user1", "correctpass") is None


def test_create_user_rejects_unknown_role():
    session = _memory_session()
    with pytest.raises(ValueError):
        auth.create_user(session, "user1", "pass123456", None, "SuperAdmin")


def test_change_password():
    session = _memory_session()
    user = auth.create_user(session, "user1", "oldpass123", None, "Member")
    session.commit()

    auth.change_password(session, user, "newpass456")
    assert auth.authenticate(session, "user1", "newpass456") is not None
    assert auth.authenticate(session, "user1", "oldpass123") is None


def test_ensure_bootstrap_admin_creates_once():
    session = _memory_session()
    auth.ensure_bootstrap_admin(session)
    count_after_first = session.query(User).count()
    assert count_after_first == 1

    admin = session.query(User).first()
    assert admin.role == auth.ADMIN_ROLE

    # Idempotent — calling again does not create a second admin
    auth.ensure_bootstrap_admin(session)
    assert session.query(User).count() == 1


def test_session_token_roundtrip():
    session = _memory_session()
    user = auth.create_user(session, "user1", "correctpass", None, "Member")
    session.commit()

    token = auth.mint_session_token(user)
    restored = auth.validate_session_token(session, token)
    assert restored is not None
    assert restored.id == user.id


def test_session_token_rejects_tampered_signature():
    session = _memory_session()
    user = auth.create_user(session, "user1", "correctpass", None, "Member")
    session.commit()

    token = auth.mint_session_token(user)
    payload_b64, _sig = token.split(".", 1)
    tampered = f"{payload_b64}.not-the-real-signature"
    assert auth.validate_session_token(session, tampered) is None


def test_session_token_rejects_malformed_token():
    session = _memory_session()
    assert auth.validate_session_token(session, "not-a-valid-token") is None
    assert auth.validate_session_token(session, "") is None


def test_session_token_expires():
    session = _memory_session()
    user = auth.create_user(session, "user1", "correctpass", None, "Member")
    session.commit()

    token = auth.mint_session_token(user, ttl_seconds=-1)  # already expired
    assert auth.validate_session_token(session, token) is None


def test_session_token_invalidated_by_password_change():
    session = _memory_session()
    user = auth.create_user(session, "user1", "oldpass123", None, "Member")
    session.commit()

    token = auth.mint_session_token(user)
    assert auth.validate_session_token(session, token) is not None

    auth.change_password(session, user, "newpass456")
    assert auth.validate_session_token(session, token) is None


def test_session_token_invalidated_by_logout_everywhere():
    session = _memory_session()
    user = auth.create_user(session, "user1", "correctpass", None, "Member")
    session.commit()

    token = auth.mint_session_token(user)
    assert auth.validate_session_token(session, token) is not None

    auth.logout_everywhere(session, user)
    assert auth.validate_session_token(session, token) is None

    # a freshly minted token after logout still works
    new_token = auth.mint_session_token(user)
    assert auth.validate_session_token(session, new_token) is not None


def test_session_token_invalidated_by_deactivation():
    session = _memory_session()
    user = auth.create_user(session, "user1", "correctpass", None, "Member")
    session.commit()

    token = auth.mint_session_token(user)
    user.is_active = False
    session.commit()
    assert auth.validate_session_token(session, token) is None


def test_can_edit_and_is_admin():
    assert auth.can_edit("Admin")
    assert auth.can_edit("Member")

    assert auth.is_admin("Admin")
    assert not auth.is_admin("Member")


def test_register_member():
    session = _memory_session()
    user = auth.register_member(session, "Parent@Example.com", "longenough1", "A Parent")
    assert user.role == "Member" and user.plan == "free"
    assert user.username == "parent@example.com" == user.email
    # duplicate email rejected
    import pytest as _pytest
    with _pytest.raises(ValueError):
        auth.register_member(session, "parent@example.com", "longenough1", None)
    with _pytest.raises(ValueError):
        auth.register_member(session, "not-an-email", "longenough1", None)
    with _pytest.raises(ValueError):
        auth.register_member(session, "new@example.com", "short", None)


def test_change_password_rejects_short_password():
    session = _memory_session()
    user = auth.create_user(session, "user1", "oldpass123", None, "Member")
    session.commit()
    with pytest.raises(ValueError):
        auth.change_password(session, user, "short")
    # original password must still work — the rejected change had no effect
    assert auth.authenticate(session, "user1", "oldpass123") is not None


def test_lockout_after_threshold_failures():
    session = _memory_session()
    auth.create_user(session, "user1", "correctpass", None, "Member")
    session.commit()

    for _ in range(auth.LOGIN_LOCKOUT_THRESHOLD):
        assert auth.authenticate(session, "user1", "wrongpass") is None
    assert auth.is_locked_out(session, "user1")
    # even the correct password is refused once locked out
    assert auth.authenticate(session, "user1", "correctpass") is None


def test_lockout_not_triggered_below_threshold():
    session = _memory_session()
    auth.create_user(session, "user1", "correctpass", None, "Member")
    session.commit()

    for _ in range(auth.LOGIN_LOCKOUT_THRESHOLD - 1):
        auth.authenticate(session, "user1", "wrongpass")
    assert not auth.is_locked_out(session, "user1")
    assert auth.authenticate(session, "user1", "correctpass") is not None


def test_lockout_expires_after_window():
    session = _memory_session()
    auth.create_user(session, "user1", "correctpass", None, "Member")
    session.commit()

    old_time = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=auth.LOGIN_LOCKOUT_MINUTES + 1)
    for _ in range(auth.LOGIN_LOCKOUT_THRESHOLD):
        session.add(auth.LoginAttempt(username="user1", success=False, attempted_at=old_time))
    session.commit()

    assert not auth.is_locked_out(session, "user1")
    assert auth.authenticate(session, "user1", "correctpass") is not None


def test_lockout_scoped_per_username():
    session = _memory_session()
    auth.create_user(session, "user1", "correctpass", None, "Member")
    auth.create_user(session, "user2", "correctpass", None, "Member")
    session.commit()

    for _ in range(auth.LOGIN_LOCKOUT_THRESHOLD):
        auth.authenticate(session, "user1", "wrongpass")
    assert auth.is_locked_out(session, "user1")
    assert not auth.is_locked_out(session, "user2")
    assert auth.authenticate(session, "user2", "correctpass") is not None


def test_is_last_admin():
    session = _memory_session()
    admin1 = auth.create_user(session, "admin1", "correctpass", None, "Admin")
    session.commit()
    assert auth.is_last_admin(session, admin1)

    admin2 = auth.create_user(session, "admin2", "correctpass", None, "Admin")
    session.commit()
    assert not auth.is_last_admin(session, admin1)
    assert not auth.is_last_admin(session, admin2)

    member = auth.create_user(session, "member1", "correctpass", None, "Member")
    session.commit()
    assert not auth.is_last_admin(session, member)
