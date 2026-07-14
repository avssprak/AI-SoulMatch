"""Outbound email (V5-6) — stdlib SMTP, no new dependency.

Deliberately tiny: one `send_email` used for signup verification codes.
If SMTP_HOST is unset, `is_configured()` is False and every caller must
skip its email step entirely (the verification gate self-disables), so
local dev and the test suite never need a mail server.
"""

from __future__ import annotations

import smtplib
from email.message import EmailMessage

from . import config


def is_configured() -> bool:
    return bool(config.SMTP_HOST)


def send_email(to: str, subject: str, body_md: str) -> None:
    """Send a plain-text email (markdown reads fine as text for our copy).
    Raises on failure — callers surface a user-friendly error."""
    msg = EmailMessage()
    msg["From"] = config.SMTP_FROM
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body_md)
    with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=20) as smtp:
        smtp.starttls()
        if config.SMTP_USER:
            smtp.login(config.SMTP_USER, config.SMTP_PASSWORD)
        smtp.send_message(msg)
