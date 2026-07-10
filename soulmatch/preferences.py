"""Candidate preference filtering — narrows the candidate pool in the
Matching page's "seeking" flow before scoring, e.g. "only show grooms aged
28-35, 165-180cm, in Bangalore, Hindu, Brahmin."

A filter only excludes a candidate when the relevant field IS present on
that profile and fails the check. A profile with the field left blank is
never excluded on that basis — incomplete profiles are common in this app
(see soulmatch.insights.incomplete_profiles) and hiding them from every
preference-filtered search would bury real candidates behind a data-entry
gap, not an actual mismatch.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import Profile


@dataclass
class CandidatePreferences:
    min_age: int | None = None
    max_age: int | None = None
    min_height_cm: float | None = None
    max_height_cm: float | None = None
    location_contains: str | None = None
    religion_contains: str | None = None
    caste_contains: str | None = None
    qualification_contains: str | None = None
    occupation_contains: str | None = None
    marital_status: str | None = None  # None/"" = any
    food_preference: str | None = None  # None/"" = any
    horoscope_available: bool | None = None  # None = any

    def is_default(self) -> bool:
        return self == CandidatePreferences()


def matches_preferences(profile: Profile, prefs: CandidatePreferences) -> bool:
    def _contains(value: str | None, needle: str | None) -> bool:
        return not needle or value is None or needle.lower() in value.lower()

    if prefs.min_age is not None and profile.age is not None and profile.age < prefs.min_age:
        return False
    if prefs.max_age is not None and profile.age is not None and profile.age > prefs.max_age:
        return False
    if prefs.min_height_cm is not None and profile.height_cm is not None and profile.height_cm < prefs.min_height_cm:
        return False
    if prefs.max_height_cm is not None and profile.height_cm is not None and profile.height_cm > prefs.max_height_cm:
        return False
    if not _contains(profile.current_location, prefs.location_contains):
        return False
    if not _contains(profile.religion, prefs.religion_contains):
        return False
    if not _contains(profile.caste, prefs.caste_contains):
        return False
    if not _contains(profile.qualification, prefs.qualification_contains):
        return False
    if not _contains(profile.occupation, prefs.occupation_contains):
        return False
    if prefs.marital_status and profile.marital_status and profile.marital_status != prefs.marital_status:
        return False
    if prefs.food_preference and profile.food_preference and profile.food_preference != prefs.food_preference:
        return False
    if (
        prefs.horoscope_available is not None
        and profile.horoscope_available is not None
        and profile.horoscope_available != prefs.horoscope_available
    ):
        return False
    return True


def filter_candidates(candidates: list[Profile], prefs: CandidatePreferences) -> list[Profile]:
    return [c for c in candidates if matches_preferences(c, prefs)]
