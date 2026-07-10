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
import time

import streamlit as st
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import config
from .models import ROLES, EDITOR_ROLES, User, utcnow

_PBKDF2_ITERATIONS = 260_000
ADMIN_ROLE = "Administrator"
SESSION_TOKEN_TTL_SECONDS = 7 * 24 * 3600


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


def create_user(session: Session, username: str, password: str, full_name: str | None, role: str) -> User:
    if role not in ROLES:
        raise ValueError(f"Unknown role: {role}")
    user = User(
        username=username.strip().lower(),
        password_hash=hash_password(password),
        full_name=full_name or None,
        role=role,
    )
    session.add(user)
    session.flush()
    return user


def authenticate(session: Session, username: str, password: str) -> User | None:
    user = session.scalar(select(User).where(User.username == username.strip().lower()))
    if user is None or not user.is_active:
        return None
    if not verify_password(password, user.password_hash):
        return None
    user.last_login = utcnow()
    session.commit()
    return user


def change_password(session: Session, user: User, new_password: str) -> None:
    user.password_hash = hash_password(new_password)
    session.commit()


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
        "Administrator", ADMIN_ROLE,
    )
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
