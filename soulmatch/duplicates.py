"""Module 4 — Duplicate Detection.

Signals: exact phone/WhatsApp match, DOB match, and fuzzy name similarity
(stdlib difflib, no extra dependency). Photo/horoscope similarity is left
for a later phase (would need perceptual hashing / embeddings).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .models import Activity, Document, MatchResult, Profile, Task

NAME_MATCH_THRESHOLD = 0.82  # difflib ratio, 0-1
MIN_REPORT_SCORE = 40  # don't surface weak/coincidental matches


def _normalize_name(name: str | None) -> str:
    if not name:
        return ""
    return " ".join(name.strip().lower().split())


def _normalize_phone(phone: str | None) -> str:
    if not phone:
        return ""
    return "".join(ch for ch in phone if ch.isdigit())[-10:]  # last 10 digits, ignore country code


def name_similarity(a: str | None, b: str | None) -> float:
    na, nb = _normalize_name(a), _normalize_name(b)
    if not na or not nb:
        return 0.0
    return SequenceMatcher(None, na, nb).ratio()


@dataclass
class DuplicateCandidate:
    profile: Profile
    score: int
    reasons: list[str] = field(default_factory=list)


def find_duplicate_candidates(
    session: Session,
    *,
    full_name: str | None,
    gender: str | None,
    phone: str | None = None,
    whatsapp: str | None = None,
    dob=None,
    exclude_id: int | None = None,
) -> list[DuplicateCandidate]:
    """Scan existing profiles (same gender) for likely duplicates of the given data."""
    phone_norm = _normalize_phone(phone) or _normalize_phone(whatsapp)

    query = select(Profile)
    if gender:
        query = query.where(Profile.gender == gender)
    if exclude_id is not None:
        query = query.where(Profile.id != exclude_id)
    candidates = session.scalars(query).all()

    results: list[DuplicateCandidate] = []
    for existing in candidates:
        score = 0
        reasons: list[str] = []

        existing_phone = _normalize_phone(existing.phone) or _normalize_phone(existing.whatsapp)
        if phone_norm and existing_phone and phone_norm == existing_phone:
            score += 60
            reasons.append(f"Same phone number ({existing.phone or existing.whatsapp})")

        if dob and existing.dob and dob == existing.dob:
            score += 30
            reasons.append(f"Same date of birth ({existing.dob})")

        similarity = name_similarity(full_name, existing.full_name)
        if similarity >= NAME_MATCH_THRESHOLD:
            score += int(30 * similarity)
            reasons.append(f"Similar name ({existing.full_name!r}, {similarity:.0%} match)")

        if score >= MIN_REPORT_SCORE:
            results.append(DuplicateCandidate(profile=existing, score=min(score, 100), reasons=reasons))

    results.sort(key=lambda c: c.score, reverse=True)
    return results


@dataclass
class DuplicateProfilePair:
    profile_a: Profile
    profile_b: Profile
    score: int
    reasons: list[str] = field(default_factory=list)


def find_all_duplicate_pairs(session: Session) -> list[DuplicateProfilePair]:
    """Pairwise scan of every profile for likely duplicates, reusing the same
    scoring as find_duplicate_candidates. O(n^2) — fine at the scale this app
    operates at (a coordinator's caseload, not a mass-import pipeline)."""
    all_profiles = session.scalars(select(Profile)).all()
    seen_pairs: set[tuple[int, int]] = set()
    results: list[DuplicateProfilePair] = []
    for profile in all_profiles:
        candidates = find_duplicate_candidates(
            session,
            full_name=profile.full_name,
            gender=profile.gender,
            phone=profile.phone,
            whatsapp=profile.whatsapp,
            dob=profile.dob,
            exclude_id=profile.id,
        )
        for c in candidates:
            pair_key = (min(profile.id, c.profile.id), max(profile.id, c.profile.id))
            if pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)
            results.append(DuplicateProfilePair(profile_a=profile, profile_b=c.profile, score=c.score, reasons=c.reasons))
    results.sort(key=lambda p: p.score, reverse=True)
    return results


def merge_into_profile(target: Profile, data: dict) -> list[str]:
    """Fill only the target's empty fields from `data` — never overwrites a
    value the target already has, so merging is always non-destructive.
    `data` may come from LLM extraction (see soulmatch.extraction) or from
    another Profile's columns (see merge_profiles below)."""
    filled = []
    for key, value in data.items():
        if key not in Profile.__table__.columns.keys() or value in (None, ""):
            continue
        if key in ("expectations", "extra") and isinstance(value, dict):
            current = dict(getattr(target, key) or {})
            added = {k: v for k, v in value.items() if not current.get(k)}
            if added:
                setattr(target, key, {**current, **added})
                filled.append(key)
        elif getattr(target, key, None) in (None, ""):
            setattr(target, key, value)
            filled.append(key)
    return filled


def _profile_to_merge_dict(profile: Profile) -> dict:
    exclude = {"id", "created_at", "updated_at"}
    return {col: getattr(profile, col) for col in Profile.__table__.columns.keys() if col not in exclude}


def merge_profiles(
    session: Session, keep: Profile, remove: Profile, created_by_user_id: int | None = None,
) -> dict:
    """Merge `remove` into `keep`: fill keep's empty fields from remove's data,
    re-point remove's documents/tasks/activities/match-results onto keep, then
    delete remove. Returns counts for UI messaging."""
    filled = merge_into_profile(keep, _profile_to_merge_dict(remove))

    moved_documents = session.scalars(select(Document).where(Document.profile_id == remove.id)).all()
    for doc in moved_documents:
        doc.profile_id = keep.id

    moved_tasks = session.scalars(select(Task).where(Task.profile_id == remove.id)).all()
    for task in moved_tasks:
        task.profile_id = keep.id

    moved_activities = session.scalars(select(Activity).where(Activity.profile_id == remove.id)).all()
    for act in moved_activities:
        act.profile_id = keep.id

    moved_matches = session.scalars(
        select(MatchResult).where(or_(MatchResult.bride_id == remove.id, MatchResult.groom_id == remove.id))
    ).all()
    for mr in moved_matches:
        if mr.bride_id == remove.id:
            mr.bride_id = keep.id
        if mr.groom_id == remove.id:
            mr.groom_id = keep.id

    session.flush()

    removed_id, removed_name = remove.id, remove.full_name
    session.delete(remove)
    session.add(Activity(
        profile_id=keep.id, event="Profiles Merged",
        detail=(
            f"Merged profile #{removed_id} ({removed_name or 'Unnamed'}) into this one: "
            + (f"filled {', '.join(filled)}" if filled else "no new fields")
            + f"; moved {len(moved_documents)} document(s), {len(moved_tasks)} task(s), "
              f"{len(moved_activities)} activity/activities, {len(moved_matches)} match result(s)."
        ),
        created_by_user_id=created_by_user_id,
    ))
    session.commit()
    return {
        "filled": filled,
        "documents": len(moved_documents),
        "tasks": len(moved_tasks),
        "activities": len(moved_activities),
        "matches": len(moved_matches),
    }
