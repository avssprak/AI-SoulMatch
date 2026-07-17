"""Profile lifecycle helpers shared across pages (single delete, bulk delete).

Kept separate from soulmatch.duplicates (which is about merging two profiles
into one) — this module is about removing a profile entirely.
"""

from __future__ import annotations

import re
from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .documents import delete_document
from .models import Activity, Document, MatchResult, Profile, Task


def age_from_dob(dob: date, today: date | None = None) -> int:
    """Age in completed years as of `today` (defaults to real today).

    Age is always derived from DOB rather than trusted from stated/typed
    values, since a stated age in biodata text goes stale between when it
    was written and when it's uploaded.
    """
    today = today or date.today()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def age_display(dob: date | None, fallback_age: int | None = None, today: date | None = None) -> str:
    """'30y 4m' computed live from DOB — the display form of age_from_dob(),
    precise enough to be useful without a stated age going stale between
    when a biodata was written and when it's viewed. Falls back to the
    stored whole-years value for older profiles that only have that."""
    if not dob:
        return f"{fallback_age}" if fallback_age is not None else "—"
    today = today or date.today()
    years = age_from_dob(dob, today)
    months = today.month - dob.month - (today.day < dob.day)
    if months < 0:
        months += 12
    return f"{years}y {months}m"


# The fields a coordinator actually needs filled in to work a profile day to
# day — not every column on the model (e.g. university/company/salary are
# nice-to-have, not blocking).
_COMPLETENESS_FIELDS = [
    "full_name", "gender", "dob", "birth_time", "birth_place", "phone",
    "religion", "caste", "gothram", "qualification", "occupation",
    "current_location", "height_cm", "food_preference",
]


def profile_completeness(profile: Profile) -> tuple[int, list[str]]:
    """Percent of _COMPLETENESS_FIELDS that are filled in, plus the list of
    which are missing (in field order) — drives the completeness meter and
    missing-field caption on the profile detail header."""
    missing = [f for f in _COMPLETENESS_FIELDS if not getattr(profile, f, None)]
    filled = len(_COMPLETENESS_FIELDS) - len(missing)
    percent = round(100 * filled / len(_COMPLETENESS_FIELDS))
    return percent, missing


# Digits chained by optional space/dash, 10-14 digits total, optional +country
# code — deliberately loose (WhatsApp forwards write numbers every which way)
# but the separators exclude dotted dates like 22.04.1994.
_PHONE_RE = re.compile(r"(?:\+\d{1,3}[-\s]?)?\d(?:[-\s]?\d){9,13}")
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]*\w")


def find_contacts_in_text(text: str) -> dict:
    """Regex sweep of a raw message for contact details — the safety net for
    when AI extraction missed a phone/email (e.g. buried in an emoji line or
    labelled 'Mother contact number'). Returns {"phones": [...], "emails": [...]}
    deduped, in order of appearance."""
    phones: list[str] = []
    seen_digits: set[str] = set()
    for m in _PHONE_RE.finditer(text or ""):
        digits = re.sub(r"\D", "", m.group(0))
        if len(digits) < 10 or digits in seen_digits:
            continue
        seen_digits.add(digits)
        phones.append(m.group(0).strip())
    emails = list(dict.fromkeys(m.group(0) for m in _EMAIL_RE.finditer(text or "")))
    return {"phones": phones, "emails": emails}


def is_match_ready(profile: Profile) -> bool:
    """A profile can get a full Ashta Koota score once it has all three birth
    details — this is the same condition the Matching page checks before
    attempting build_chart()."""
    return bool(profile.dob and profile.birth_time and profile.birth_place)


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
