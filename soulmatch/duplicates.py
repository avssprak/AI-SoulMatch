"""Module 4 — Duplicate Detection.

Signals: exact phone/WhatsApp match, DOB match, and fuzzy name similarity
(stdlib difflib, no extra dependency). Photo/horoscope similarity is left
for a later phase (would need perceptual hashing / embeddings).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Profile

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
