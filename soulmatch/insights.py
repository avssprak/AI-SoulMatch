"""Module 14 — AI Assistant (rule-based subset).

These are direct, deterministic database queries — not LLM calls — for the
questions from the PRD that don't actually need natural-language reasoning
to answer correctly ("which profiles are incomplete", "who has the highest
horoscope score", "find best match for X"). Free, instant, and unambiguous;
reserve the LLM for soulmatch/search.py (query parsing) and
soulmatch/recommendation.py (match narratives), where free text genuinely
needs interpretation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .matching.rules import MatchOutcome, evaluate_match
from .models import Activity, MatchResult, Profile, Task
from .tenancy import get_owned, owned

IMPORTANT_FIELDS = [
    "dob", "birth_time", "birth_place", "religion", "caste",
    "current_location", "qualification", "occupation", "height_cm", "food_preference",
]

INACTIVE_STAGES = ("Marriage", "Rejected", "Closed")


@dataclass
class IncompleteProfile:
    profile: Profile
    missing_fields: list[str]


def incomplete_profiles(session: Session, owner_id: int) -> list[IncompleteProfile]:
    profiles = session.scalars(owned(select(Profile), Profile, owner_id)).all()
    results = []
    for p in profiles:
        missing = [f for f in IMPORTANT_FIELDS if getattr(p, f, None) in (None, "")]
        if missing:
            results.append(IncompleteProfile(profile=p, missing_fields=missing))
    results.sort(key=lambda r: len(r.missing_fields), reverse=True)
    return results


def pending_horoscope(session: Session, owner_id: int) -> list[Profile]:
    query = owned(select(Profile).where(Profile.horoscope_available.is_not(True)), Profile, owner_id)
    return list(session.scalars(query.order_by(Profile.created_at.desc())).all())


def top_astrology_matches(session: Session, owner_id: int, limit: int = 10) -> list[MatchResult]:
    query = (
        owned(select(MatchResult), MatchResult, owner_id)
        .where(MatchResult.koota_total.is_not(None))
        .order_by(MatchResult.koota_total.desc())
        .limit(limit)
    )
    return list(session.scalars(query).all())


def stale_cases(session: Session, owner_id: int, *, days: int = 14, today: date | None = None) -> list[Profile]:
    """Active-pipeline profiles with no logged activity in `days` days."""
    today = today or date.today()
    cutoff = today - timedelta(days=days)

    profiles = session.scalars(
        owned(select(Profile).where(Profile.stage.not_in(INACTIVE_STAGES)), Profile, owner_id)
    ).all()

    stale = []
    for p in profiles:
        last_activity = session.scalar(
            select(Activity.created_at)
            .where(Activity.profile_id == p.id)
            .order_by(Activity.created_at.desc())
            .limit(1)
        )
        reference = last_activity.date() if last_activity else p.created_at.date()
        if reference < cutoff:
            stale.append(p)
    stale.sort(key=lambda p: p.created_at)
    return stale


# V4-5-3: shortlisting is the "Interested" stage (see pages_/4_Matching.py
# Scoreboard's Shortlist button) — a narrower, more actionable nudge than
# stale_cases() above, since it only flags candidates the member has
# already decided to pursue and then gone quiet on.
SHORTLIST_STAGE = "Interested"


def stale_shortlisted(session: Session, owner_id: int, *, days: int = 7, today: date | None = None) -> list[Profile]:
    """Shortlisted (stage == "Interested") profiles with no open task and no
    logged activity in `days` days — these are the ones a member meant to
    act on and then forgot."""
    today = today or date.today()
    cutoff = today - timedelta(days=days)

    profiles = session.scalars(
        owned(select(Profile).where(Profile.stage == SHORTLIST_STAGE), Profile, owner_id)
    ).all()

    stale = []
    for p in profiles:
        has_open_task = session.scalar(
            select(Task.id).where(Task.profile_id == p.id, Task.status == "Pending").limit(1)
        ) is not None
        if has_open_task:
            continue
        last_activity = session.scalar(
            select(Activity.created_at)
            .where(Activity.profile_id == p.id)
            .order_by(Activity.created_at.desc())
            .limit(1)
        )
        reference = last_activity.date() if last_activity else p.created_at.date()
        if reference < cutoff:
            stale.append(p)
    stale.sort(key=lambda p: p.created_at)
    return stale


def best_matches_for(session: Session, owner_id: int, profile_id: int, *, limit: int = 5) -> list[tuple[Profile, MatchOutcome]]:
    """Rank opposite-gender profiles by practical compatibility (Module 6/14).
    Astrology is not recomputed here for speed — drill into a specific
    candidate on the Matching page for the full picture."""
    subject = get_owned(session, Profile, profile_id, owner_id)
    if subject is None:
        return []
    opposite_gender = "Groom" if subject.gender == "Bride" else "Bride"
    candidates = session.scalars(
        owned(select(Profile).where(Profile.gender == opposite_gender, Profile.id != profile_id), Profile, owner_id)
    ).all()

    scored = []
    for candidate in candidates:
        bride, groom = (subject, candidate) if subject.gender == "Bride" else (candidate, subject)
        outcome = evaluate_match(bride, groom)
        scored.append((candidate, outcome))

    scored.sort(key=lambda pair: (pair[1].mandatory_passed, pair[1].score), reverse=True)
    return scored[:limit]
