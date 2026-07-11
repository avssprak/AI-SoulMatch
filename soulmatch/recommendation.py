"""Module 8 — AI Recommendation Engine.

Generates a narrative explanation for a bride/groom match, combining the
practical rule-engine outcome and (if available) the astrology result:
why the match is good, concerns, questions to raise with families, and
family/lifestyle/career compatibility notes. Falls back to a deterministic
template when LLM_PROVIDER=mock so this works fully offline.
"""

from __future__ import annotations

import json

from . import config
from .extraction import llm
from .models import Profile

RECOMMENDATION_FIELDS = {
    "summary": "one or two sentence overall verdict",
    "strengths": "array of short strings — what makes this match work",
    "concerns": "array of short strings — potential issues to be aware of",
    "questions_for_families": "array of short strings — good questions to raise before proceeding",
    "family_compatibility": "one sentence assessment of family background fit",
    "lifestyle_compatibility": "one sentence assessment of lifestyle/values fit",
    "career_compatibility": "one sentence assessment of career/education fit",
    "risk_indicators": "array of short strings — red flags, or empty array if none",
    "final_recommendation": '"Recommended", "Proceed with Caution", or "Not Recommended"',
}

_ARRAY_FIELDS = {
    "strengths", "concerns", "questions_for_families", "risk_indicators",
}

_PROMPT_TEMPLATE = """You are a matrimonial matchmaking advisor for an Indian community \
matchmaking service. Analyze this proposed match and produce a JSON object with exactly \
these keys:

{schema}

Bride: {bride}
Groom: {groom}

Practical screening result: {practical}
Astrology (Ashta Koota) result: {astro}

Be concrete and specific to the data given above — do not invent facts that are not \
present. Respond with ONLY the JSON object."""


def _profile_brief(p: Profile) -> dict:
    return {
        "name": p.full_name, "age": p.age, "religion": p.religion, "caste": p.caste,
        "location": p.current_location, "qualification": p.qualification,
        "occupation": p.occupation, "height_cm": p.height_cm,
        "food_preference": p.food_preference, "marital_status": p.marital_status,
        "family_details": p.family_details, "notes": p.notes,
    }


def generate_recommendation(
    bride: Profile, groom: Profile, practical: dict, astro: dict | None,
    provider: str | None = None, usage_out: dict | None = None,
) -> dict:
    """practical: {"score": float, "recommended": bool, "strengths": [...], "weaknesses": [...]}
    astro: full_compatibility() result dict, or None if not computed."""
    provider = (provider or config.LLM_PROVIDER).lower()
    if provider == "mock":
        result = _mock_recommendation(bride, groom, practical, astro)
    else:
        prompt = _PROMPT_TEMPLATE.format(
            schema=json.dumps(RECOMMENDATION_FIELDS, indent=2),
            bride=json.dumps(_profile_brief(bride)),
            groom=json.dumps(_profile_brief(groom)),
            practical=json.dumps(practical),
            astro=json.dumps(astro) if astro else "not available",
        )
        raw = llm.complete_json(prompt, provider=provider, usage_out=usage_out)
        result = _clean(raw)
    result["_provider"] = provider
    return result


def _clean(data: dict) -> dict:
    out = {}
    for key in RECOMMENDATION_FIELDS:
        value = data.get(key)
        if key in _ARRAY_FIELDS and not isinstance(value, list):
            value = [value] if value else []
        out[key] = value
    return out


def _mock_recommendation(bride: Profile, groom: Profile, practical: dict, astro: dict | None) -> dict:
    strengths = list(practical.get("strengths") or [])
    concerns = list(practical.get("weaknesses") or [])
    risk: list[str] = []
    final = "Recommended" if practical.get("recommended") else "Not Recommended"

    if astro:
        if astro.get("dosha_flags"):
            risk.extend(astro["dosha_flags"])
        score = astro.get("overall_score", 36)
        if score < 18:
            final = "Not Recommended"
            concerns.append(f"Low astrology compatibility ({score}/36)")
        elif score >= 25 and practical.get("recommended"):
            final = "Recommended"
        elif risk:
            final = "Proceed with Caution"

    summary = (
        f"{bride.full_name or 'Bride'} and {groom.full_name or 'Groom'}: practical fit "
        f"{practical.get('score', 0)}%"
        + (f", astrology {astro['overall_score']}/36 ({astro['overall_verdict']})" if astro else "")
        + "."
    )

    questions = [
        "Discuss long-term location preferences and career flexibility.",
        "Confirm horoscope details directly with both families.",
    ]
    if risk:
        questions.append("Discuss the flagged doshas with a family priest/astrologer.")

    return {
        "summary": summary,
        "strengths": strengths or ["No specific strengths flagged — review manually."],
        "concerns": concerns or ["None flagged."],
        "questions_for_families": questions,
        "family_compatibility": "Not assessed — offline mock provider does not analyze family details.",
        "lifestyle_compatibility": (
            "Same food preference." if bride.food_preference and bride.food_preference == groom.food_preference
            else "Lifestyle details incomplete or differing — verify with families."
        ),
        "career_compatibility": (
            f"{groom.occupation or 'Groom'} vs {bride.occupation or 'Bride'} — review compatibility manually."
        ),
        "risk_indicators": risk,
        "final_recommendation": final,
    }
