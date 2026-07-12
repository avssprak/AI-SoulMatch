"""Module 5 (Minimum Criteria Screening) + Module 6 (Match Engine).

Configurable rule-based scoring between a bride and groom profile, run
before astrology. Each rule is mandatory or optional with a weight; the
overall practical_score is a weighted percentage of optional rules passed,
gated by all mandatory rules passing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from ..models import Profile


@dataclass
class RuleResult:
    name: str
    passed: bool
    mandatory: bool
    weight: float
    detail: str


@dataclass
class Rule:
    name: str
    mandatory: bool
    weight: float
    check: Callable[[Profile, Profile], tuple[bool, str]]


def _age_diff_ok(bride: Profile, groom: Profile, max_groom_older: int = 10, max_bride_older: int = 2) -> tuple[bool, str]:
    if bride.age is None or groom.age is None:
        return True, "Age missing — skipped"
    diff = groom.age - bride.age
    ok = -max_bride_older <= diff <= max_groom_older
    return ok, f"Groom is {diff:+d} yrs vs bride"


def _height_ok(bride: Profile, groom: Profile, min_diff_cm: float = 0.0) -> tuple[bool, str]:
    if not bride.height_cm or not groom.height_cm:
        return True, "Height missing — skipped"
    diff = groom.height_cm - bride.height_cm
    ok = diff >= min_diff_cm
    return ok, f"Groom {diff:+.0f} cm vs bride"


def _religion_ok(bride: Profile, groom: Profile) -> tuple[bool, str]:
    if not bride.religion or not groom.religion:
        return True, "Religion missing — skipped"
    ok = bride.religion.strip().lower() == groom.religion.strip().lower()
    return ok, f"{groom.religion} vs {bride.religion}"


def _caste_ok(bride: Profile, groom: Profile) -> tuple[bool, str]:
    if not bride.caste or not groom.caste:
        return True, "Caste missing — skipped"
    ok = bride.caste.strip().lower() == groom.caste.strip().lower()
    return ok, f"{groom.caste} vs {bride.caste}"


def _gothram_ok(bride: Profile, groom: Profile) -> tuple[bool, str]:
    """Same gothram is traditionally avoided (sagothra dosha)."""
    if not bride.gothram or not groom.gothram:
        return True, "Gothram missing — skipped"
    ok = bride.gothram.strip().lower() != groom.gothram.strip().lower()
    return ok, f"{groom.gothram} vs {bride.gothram}" + ("" if ok else " — same gothram")


def _location_ok(bride: Profile, groom: Profile) -> tuple[bool, str]:
    if not bride.current_location or not groom.current_location:
        return True, "Location missing — skipped"
    ok = bride.current_location.strip().lower() == groom.current_location.strip().lower()
    return ok, f"{groom.current_location} vs {bride.current_location}"


def _country_ok(bride: Profile, groom: Profile) -> tuple[bool, str]:
    if not bride.country or not groom.country:
        return True, "Country missing — skipped"
    ok = bride.country.strip().lower() == groom.country.strip().lower()
    return ok, f"{groom.country} vs {bride.country}"


def _food_ok(bride: Profile, groom: Profile) -> tuple[bool, str]:
    if not bride.food_preference or not groom.food_preference:
        return True, "Food preference missing — skipped"
    ok = bride.food_preference == groom.food_preference
    return ok, f"{groom.food_preference} vs {bride.food_preference}"


def _marital_status_ok(bride: Profile, groom: Profile) -> tuple[bool, str]:
    if not bride.marital_status or not groom.marital_status:
        return True, "Marital status missing — skipped"
    ok = bride.marital_status == groom.marital_status
    return ok, f"{groom.marital_status} vs {bride.marital_status}"


def default_rules() -> list[Rule]:
    """Administrator-configurable rule set. Mandatory rules gate the match;
    optional rules contribute to the weighted score."""
    return [
        Rule("Religion", mandatory=True, weight=0, check=_religion_ok),
        Rule("Same Gothram", mandatory=True, weight=0, check=_gothram_ok),
        Rule("Age Difference", mandatory=False, weight=25, check=_age_diff_ok),
        Rule("Height", mandatory=False, weight=15, check=_height_ok),
        Rule("Caste", mandatory=False, weight=20, check=_caste_ok),
        Rule("Location", mandatory=False, weight=15, check=_location_ok),
        Rule("Country", mandatory=False, weight=10, check=_country_ok),
        Rule("Food Preference", mandatory=False, weight=10, check=_food_ok),
        Rule("Marital Status", mandatory=False, weight=5, check=_marital_status_ok),
    ]


@dataclass
class MatchOutcome:
    results: list[RuleResult] = field(default_factory=list)
    mandatory_passed: bool = True
    score: float = 0.0
    recommended: bool = False
    missing_fields: list[str] = field(default_factory=list)

    def strengths(self) -> list[str]:
        return [r.detail for r in self.results if r.passed and not r.detail.endswith("skipped")]

    def weaknesses(self) -> list[str]:
        return [r.detail for r in self.results if not r.passed]


def evaluate_match(bride: Profile, groom: Profile, rules: list[Rule] | None = None) -> MatchOutcome:
    rules = rules or default_rules()
    outcome = MatchOutcome()

    optional_total_weight = sum(r.weight for r in rules if not r.mandatory) or 1.0
    earned = 0.0

    for rule in rules:
        passed, detail = rule.check(bride, groom)
        outcome.results.append(RuleResult(rule.name, passed, rule.mandatory, rule.weight, detail))
        if rule.mandatory and not passed:
            outcome.mandatory_passed = False
        if not rule.mandatory and passed:
            earned += rule.weight

    outcome.score = round(100 * earned / optional_total_weight, 1)
    outcome.recommended = outcome.mandatory_passed and outcome.score >= 50

    required_fields = [
        "age", "height_cm", "religion", "caste", "current_location",
        "food_preference", "marital_status",
    ]
    for field_name in required_fields:
        if getattr(bride, field_name, None) is None or getattr(groom, field_name, None) is None:
            outcome.missing_fields.append(field_name)

    return outcome


KOOTA_MAX = 36.0


def composite_score(practical_score: float | None, koota_total: float | None, astro_weight: int) -> float | None:
    """V4-4-1 Scoreboard composite: `astro_weight`% (0-100, a member
    preference — see User.astro_weight) of the astrology score (koota_total
    out of 36, converted to a percentage) blended with the rest as the
    practical score. Falls back to whichever single score is available; None
    only when neither is."""
    if practical_score is None and koota_total is None:
        return None
    if koota_total is None:
        return practical_score
    if practical_score is None:
        return round(100 * koota_total / KOOTA_MAX, 1)
    astro_pct = 100 * koota_total / KOOTA_MAX
    weight = astro_weight / 100
    return round(weight * astro_pct + (1 - weight) * practical_score, 1)


def score_band(score: float | None) -> str:
    """Red/amber/green threshold label for the Scoreboard (V4-4-2)."""
    if score is None:
        return "—"
    if score >= 70:
        return "🟢"
    if score >= 40:
        return "🟡"
    return "🔴"
