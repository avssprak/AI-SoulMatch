"""Authentication & role-based access control.

Session-based auth, not JWT: this is a single-process Streamlit app, not a
multi-service API, so a signed token would add complexity (secret rotation,
cookie storage) without a security benefit over server-side session state —
`st.session_state["user"]` is already tied to one authenticated session.

Passwords are hashed with PBKDF2-HMAC-SHA256 (stdlib `hashlib`, no extra
dependency), the same scheme Django uses by default.
"""

from __future__ import annotations

import hashlib
import os

import streamlit as st
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import config
from .models import ROLES, EDITOR_ROLES, User, utcnow

_PBKDF2_ITERATIONS = 260_000
ADMIN_ROLE = "Administrator"


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
