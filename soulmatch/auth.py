"""Authentication & role-based access control.

`st.session_state["user"]` holds the authenticated user for the current
connection, but Streamlit ties session_state to the browser's WebSocket —
a page refresh opens a new one and drops it, logging the user out. To survive
a refresh (and a browser restart within the expiry window) without a new
dependency, `mint_session_token`/`validate_session_token` below sign a small
JSON payload (user id + a password-hash fingerprint + expiry) with HMAC-SHA256
and carry it in `st.query_params` — restored at app startup in `app.py`. This
is not general-purpose JWT/API auth (no key rotation, no multi-service
concerns); it exists solely to bridge Streamlit's per-connection session
state across a refresh. Changing the password invalidates every outstanding
token immediately, since the fingerprint is embedded in the signed payload.

Passwords are hashed with PBKDF2-HMAC-SHA256 (stdlib `hashlib`, no extra
dependency), the same scheme Django uses by default.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import time
from datetime import datetime, timedelta, timezone

import streamlit as st
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import config, mailer
from .models import ROLES, EDITOR_ROLES, LoginAttempt, Profile, User, utcnow
from .tenancy import owned

_PBKDF2_ITERATIONS = 260_000
ADMIN_ROLE = "Admin"
MEMBER_ROLE = "Member"
SESSION_TOKEN_TTL_SECONDS = 7 * 24 * 3600
# V5-5-1: the token minted at login/signup keeps its full week of "remember
# me" grace before the member's first return visit. Every restore from the
# URL after that rotates to this much shorter window instead of re-minting
# another 7 days — so a URL that leaks (copied, screenshotted, shared) after
# first use stays a live credential for hours, not most of a week.
SESSION_TOKEN_ROTATE_TTL_SECONDS = 24 * 3600
MIN_PASSWORD_LENGTH = 8

# V3-5-3 login rate-limiting: a table (not an in-process counter) so a
# server restart can't reset a lockout. Rolling window: once locked, every
# further attempt is rejected without checking the password (so it doesn't
# record a new failure) — the lockout naturally expires as old failures
# age out of the window.
LOGIN_LOCKOUT_THRESHOLD = 8
LOGIN_LOCKOUT_MINUTES = 15
LOCKOUT_MESSAGE = (
    f"Too many failed sign-in attempts. Please wait {LOGIN_LOCKOUT_MINUTES} minutes and try again."
)


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS)
    return f"{salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, _ = stored.split("$", 1)
        salt = bytes.fromhex(salt_hex)
    except (ValueError, AttributeError):
        return False
    return hash_password(password, salt) == stored


def create_user(
    session: Session, username: str, password: str, full_name: str | None, role: str,
    email: str | None = None,
) -> User:
    if role not in ROLES:
        raise ValueError(f"Unknown role: {role}")
    user = User(
        username=username.strip().lower(),
        email=(email or None) and email.strip().lower(),
        password_hash=hash_password(password),
        full_name=full_name or None,
        role=role,
        # V5-6: accounts created here (bootstrap admin, admin-created members)
        # are trusted; only self-service signup (register_member) starts
        # unverified — and only while the mailer is configured.
        email_verified_at=utcnow(),
    )
    session.add(user)
    session.flush()
    return user


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def register_member(session: Session, email: str, password: str, full_name: str | None) -> User:
    """Self-service signup (V3-1-4): new accounts are Members on the free
    plan, and email doubles as the username. Raises ValueError with a
    user-displayable message on any problem."""
    email = email.strip().lower()
    if not _EMAIL_RE.match(email):
        raise ValueError("Please enter a valid email address.")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
    if session.scalar(select(User).where(User.username == email)) is not None:
        raise ValueError("An account with this email already exists. Try signing in.")
    user = create_user(session, email, password, full_name, MEMBER_ROLE, email=email)
    if mailer.is_configured():
        # V5-6: self-service accounts must prove ownership of the address
        # before any session is minted — see send_verification_code below.
        user.email_verified_at = None
    session.commit()
    return user


# --- V5-6 email verification -------------------------------------------------
# Code entry, not a click-link: Streamlit is a poor target for deep-link
# callbacks, and parents on phones handle "enter the 6-digit code we emailed
# you" more easily. The whole gate self-disables when the mailer isn't
# configured, so dev/local/tests behave exactly as before V5-6.
VERIFICATION_CODE_TTL_MINUTES = 30
VERIFICATION_MAX_ATTEMPTS = 5
VERIFICATION_MAX_SENDS_PER_HOUR = 3


def verification_required(user: User) -> bool:
    return mailer.is_configured() and user.email_verified_at is None


def _naive_utc(dt: datetime | None) -> datetime | None:
    """SQLite hands back naive datetimes while utcnow() is tz-aware — strip
    tzinfo so arithmetic works either way (same trick as the lockout window)."""
    return dt.replace(tzinfo=None) if dt is not None else None


def send_verification_code(session: Session, user: User, *, now: datetime | None = None) -> None:
    """Generate + email a fresh 6-digit code. Raises ValueError with a
    user-displayable message if the hourly send cap is hit or SMTP fails."""
    now = _naive_utc(now or utcnow())
    window_start = _naive_utc(user.verification_window_start)
    if window_start and (now - window_start) < timedelta(hours=1):
        if (user.verification_sends or 0) >= VERIFICATION_MAX_SENDS_PER_HOUR:
            raise ValueError("Too many codes requested — please try again in an hour.")
        user.verification_sends = (user.verification_sends or 0) + 1
    else:
        user.verification_window_start = now
        user.verification_sends = 1
    code = f"{int.from_bytes(os.urandom(4), 'big') % 1_000_000:06d}"
    user.verification_code = code
    user.verification_sent_at = now
    user.verification_attempts = 0
    session.commit()
    try:
        mailer.send_email(
            user.email or user.username,
            "Your SoulMatch verification code",
            f"Hello{' ' + user.full_name if user.full_name else ''},\n\n"
            f"Your verification code is: {code}\n\n"
            f"Enter it in the app within {VERIFICATION_CODE_TTL_MINUTES} minutes "
            "to finish creating your account.\n\n"
            "If you didn't sign up for SoulMatch by RedPrana, you can ignore this email.",
        )
    except Exception as exc:  # smtplib raises many types; all mean "not sent"
        raise ValueError(
            "We couldn't send the verification email just now — please try again shortly."
        ) from exc


def verify_email_code(session: Session, user: User, code: str, *, now: datetime | None = None) -> str:
    """Check `code` against the current one. Returns "ok" (and marks the user
    verified), "expired", "locked" (too many wrong tries — resend needed), or
    "wrong"."""
    now = _naive_utc(now or utcnow())
    sent_at = _naive_utc(user.verification_sent_at)
    if (
        user.verification_code is None
        or sent_at is None
        or (now - sent_at) > timedelta(minutes=VERIFICATION_CODE_TTL_MINUTES)
    ):
        return "expired"
    if (user.verification_attempts or 0) >= VERIFICATION_MAX_ATTEMPTS:
        return "locked"
    if not hmac.compare_digest(code.strip(), user.verification_code):
        user.verification_attempts = (user.verification_attempts or 0) + 1
        session.commit()
        return "locked" if user.verification_attempts >= VERIFICATION_MAX_ATTEMPTS else "wrong"
    user.email_verified_at = now
    user.verification_code = None
    user.verification_attempts = 0
    session.commit()
    return "ok"


def _recent_failed_attempts(session: Session, username: str, *, now: datetime | None = None) -> int:
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    window_start = now - timedelta(minutes=LOGIN_LOCKOUT_MINUTES)
    return session.scalar(
        select(func.count(LoginAttempt.id)).where(
            LoginAttempt.username == username,
            LoginAttempt.success.is_(False),
            LoginAttempt.attempted_at >= window_start,
        )
    ) or 0


def is_locked_out(session: Session, username: str, *, now: datetime | None = None) -> bool:
    """True if `username` has LOGIN_LOCKOUT_THRESHOLD+ failed attempts in the
    last LOGIN_LOCKOUT_MINUTES minutes. Call this BEFORE authenticate() so
    the caller can show LOCKOUT_MESSAGE instead of a generic invalid-login
    error — authenticate() itself also refuses to check the password while
    locked, so a correct password during lockout still can't sign in."""
    return _recent_failed_attempts(session, username.strip().lower(), now=now) >= LOGIN_LOCKOUT_THRESHOLD


def authenticate(session: Session, username: str, password: str) -> User | None:
    username_norm = username.strip().lower()
    if is_locked_out(session, username_norm):
        return None
    user = session.scalar(select(User).where(User.username == username_norm))
    ok = user is not None and user.is_active and verify_password(password, user.password_hash)
    # Recorded even on success, so is_locked_out's window naturally contains
    # only genuine failures — a correct login doesn't need to reset anything.
    session.add(LoginAttempt(username=username_norm, success=ok))
    session.commit()
    if not ok:
        return None
    user.last_login = utcnow()
    session.commit()
    return user


def change_password(session: Session, user: User, new_password: str) -> None:
    if len(new_password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
    user.password_hash = hash_password(new_password)
    session.commit()


def is_last_admin(session: Session, user: User) -> bool:
    """True if `user` is an Admin and no other Admin account exists — used
    to refuse deleting/demoting the only operator account (V3-5-2)."""
    if user.role != ADMIN_ROLE:
        return False
    count = session.scalar(select(func.count(User.id)).where(User.role == ADMIN_ROLE)) or 0
    return count <= 1


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _b64decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sign(payload_b64: str) -> str:
    digest = hmac.new(config.SECRET_KEY.encode(), payload_b64.encode(), hashlib.sha256).digest()
    return _b64encode(digest)


def mint_session_token(user: User, ttl_seconds: int = SESSION_TOKEN_TTL_SECONDS) -> str:
    """Sign a token so login survives a browser refresh (see module docstring)."""
    payload = {
        "uid": user.id,
        "pw": user.password_hash[:12],  # fingerprint only — invalidates on password change
        "epoch": user.session_epoch,  # invalidates on logout (see logout_everywhere)
        "exp": int(time.time()) + ttl_seconds,
    }
    payload_b64 = _b64encode(json.dumps(payload, separators=(",", ":")).encode())
    return f"{payload_b64}.{_sign(payload_b64)}"


def validate_session_token(session: Session, token: str) -> User | None:
    """Reverse of mint_session_token; returns the user if the token is genuine,
    unexpired, and still matches the user's current password."""
    try:
        payload_b64, signature = token.split(".", 1)
    except ValueError:
        return None
    if not hmac.compare_digest(signature, _sign(payload_b64)):
        return None
    try:
        payload = json.loads(_b64decode(payload_b64))
    except (ValueError, UnicodeDecodeError):
        return None
    if payload.get("exp", 0) < time.time():
        return None
    user = session.get(User, payload.get("uid"))
    if user is None or not user.is_active:
        return None
    if user.password_hash[:12] != payload.get("pw"):
        return None
    if user.session_epoch != payload.get("epoch"):
        return None
    return user


def logout_everywhere(session: Session, user: User) -> None:
    """Bump the session epoch so every outstanding persistent-login token for
    this user — including stale copies of the URL in another tab or bookmark —
    stops validating immediately."""
    user.session_epoch += 1
    session.commit()


def ensure_bootstrap_admin(session: Session) -> None:
    """Create the first admin account from config if no users exist yet."""
    if session.scalar(select(User).limit(1)) is not None:
        return
    create_user(
        session, config.BOOTSTRAP_ADMIN_USERNAME, config.BOOTSTRAP_ADMIN_PASSWORD,
        "Platform Admin", ADMIN_ROLE,
    )
    session.commit()


def needs_onboarding(session: Session, user: User) -> bool:
    """V5-1-1: True iff `user` should be routed to the first-login wizard
    (pages_/00_Welcome.py) instead of the normal app. Admins never see it —
    it's the parent journey, not an operator concern. A member who already
    has any owned Profile (pre-V5 account, or restored from an export)
    doesn't need it either; callers should follow a False here by persisting
    onboarded_at via mark_onboarded() so this check is cheap on every future
    page load."""
    if user.onboarded_at is not None or is_admin(user.role):
        return False
    return session.scalar(owned(select(Profile.id), Profile, user.id).limit(1)) is None


def mark_onboarded(session: Session, user: User) -> None:
    user.onboarded_at = utcnow()
    session.commit()


def can_edit(role: str) -> bool:
    return role in EDITOR_ROLES


def is_admin(role: str) -> bool:
    return role == ADMIN_ROLE


def current_user() -> dict | None:
    return st.session_state.get("user")


def require_login() -> dict:
    """Call at the top of every page. Pages are independently runnable
    Streamlit scripts, so app.py's login gate alone isn't sufficient if
    someone launches a page file directly (e.g. `streamlit run pages_/X.py`)."""
    user = current_user()
    if user is None:
        st.error("Please sign in from the main app page.")
        st.stop()
    return user


def require_admin() -> dict:
    user = require_login()
    if not is_admin(user["role"]):
        st.error("Administrator access required.")
        st.stop()
    return user
