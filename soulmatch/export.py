"""Module 17 — self-service data export & account deletion (V3-5-2).

Both are tenant-scoped by construction: every model exported/deleted here
carries owner_user_id, and every query below filters on it — the same
discipline as soulmatch.tenancy, just not routed through that module since
this code deletes/reads across many models in one pass rather than serving
a single page's query.
"""

from __future__ import annotations

import io
import json
import zipfile
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .documents import read_document
from .models import Activity, AiUsage, Document, MatchResult, Profile, RawMessage, Subscription, Task, User
from .profiles import delete_profile

# (export filename stem, model) — every tenant-scoped table except
# WebhookEvent (a global idempotency ledger, not owned by any one tenant).
_EXPORT_MODELS = [
    ("profiles", Profile),
    ("documents", Document),
    ("tasks", Task),
    ("activities", Activity),
    ("match_results", MatchResult),
    ("raw_messages", RawMessage),
    ("ai_usage", AiUsage),
    ("subscriptions", Subscription),
]


def _row_to_dict(row) -> dict:
    out = {}
    for col in row.__table__.columns.keys():
        value = getattr(row, col)
        if isinstance(value, (date, datetime)):
            value = value.isoformat()
        out[col] = value
    return out


def export_owner_data_zip(session: Session, owner_id: int) -> bytes:
    """Everything this owner's account has produced: one JSON file per
    table (rows scoped to owner_id only) plus the actual uploaded files
    under files/. Used by "Export my data" on My Plan."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, model in _EXPORT_MODELS:
            rows = session.scalars(select(model).where(model.owner_user_id == owner_id)).all()
            zf.writestr(
                f"{name}.json",
                json.dumps([_row_to_dict(r) for r in rows], indent=2, ensure_ascii=False),
            )
        documents = session.scalars(select(Document).where(Document.owner_user_id == owner_id)).all()
        for doc in documents:
            try:
                data = read_document(doc)
            except FileNotFoundError:
                continue
            zf.writestr(f"files/{doc.id}_{doc.filename}", data)
    return buf.getvalue()


def delete_owner_account(session: Session, owner_id: int) -> None:
    """Hard-delete every row this account owns, then the account itself.
    Callers MUST check auth.is_last_admin() first and refuse if true — this
    function has no notion of "how many admins exist", that's a
    caller-level policy decision, not a data-layer one."""
    profiles = session.scalars(select(Profile).where(Profile.owner_user_id == owner_id)).all()
    for p in profiles:
        delete_profile(session, p)  # also removes this profile's documents/tasks/activities/matches

    # Rows that can exist independent of any profile (e.g. a raw WhatsApp
    # message never turned into one).
    for model in (RawMessage, AiUsage, Subscription):
        for row in session.scalars(select(model).where(model.owner_user_id == owner_id)).all():
            session.delete(row)

    user = session.get(User, owner_id)
    if user is not None:
        session.delete(user)
    session.commit()
