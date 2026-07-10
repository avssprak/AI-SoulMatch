"""Profile lifecycle helpers shared across pages (single delete, bulk delete).

Kept separate from soulmatch.duplicates (which is about merging two profiles
into one) — this module is about removing a profile entirely.
"""

from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .documents import delete_document
from .models import Activity, Document, MatchResult, Profile, Task


def delete_profile(session: Session, profile: Profile) -> dict:
    """Permanently delete a profile and everything that references it —
    documents (including the files on disk), tasks, activities, and any
    saved match results — so nothing is left orphaned. Returns counts for
    UI messaging."""
    documents = session.scalars(select(Document).where(Document.profile_id == profile.id)).all()
    for doc in documents:
        delete_document(session, doc)

    tasks = session.scalars(select(Task).where(Task.profile_id == profile.id)).all()
    for task in tasks:
        session.delete(task)

    activities = session.scalars(select(Activity).where(Activity.profile_id == profile.id)).all()
    for act in activities:
        session.delete(act)

    matches = session.scalars(
        select(MatchResult).where(or_(MatchResult.bride_id == profile.id, MatchResult.groom_id == profile.id))
    ).all()
    for mr in matches:
        session.delete(mr)

    deleted_id = profile.id
    session.delete(profile)
    session.commit()
    return {
        "id": deleted_id,
        "documents": len(documents),
        "tasks": len(tasks),
        "activities": len(activities),
        "matches": len(matches),
    }
