"""Module 13 — Natural Language Search.

Translates a free-text query into a structured Profile filter, then runs it
as an ordinary SQLAlchemy query — the LLM (or mock parser) only ever
produces a filter specification, never a query string, so there is no SQL
injection surface. The mock parser matches known distinct values already in
the database (religion, caste, location, ...) against the query text, so it
adapts to real data without a hardcoded vocabulary.
"""

from __future__ import annotations

import json
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import config
from .extraction import llm
from .models import PIPELINE_STAGES, Profile
from .tenancy import owned

SEARCH_FIELDS = {
    "gender": '"Bride" or "Groom" or null',
    "religion": "string or null",
    "caste": "string or null",
    "current_location": "string or null",
    "country": "string or null",
    "min_age": "integer or null",
    "max_age": "integer or null",
    "qualification_contains": "string or null (matches qualification field)",
    "occupation_contains": "string or null",
    "food_preference": '"Vegetarian" / "Non-Vegetarian" / "Eggetarian" or null',
    "marital_status": "string or null",
    "horoscope_available": "true, false, or null",
    "stage": f"one of {PIPELINE_STAGES} or null",
}

_ILIKE_FIELDS = {
    "religion": Profile.religion,
    "caste": Profile.caste,
    "current_location": Profile.current_location,
    "country": Profile.country,
    "qualification_contains": Profile.qualification,
    "occupation_contains": Profile.occupation,
}

_PROMPT_TEMPLATE = """You are translating a matrimonial-search query written in plain English into a \
structured JSON filter for a profile database. Return a single JSON object with exactly these keys \
(use null for anything not mentioned in the query; never invent values not implied by the query):

{schema}

Query: "{query}"

Respond with ONLY the JSON object."""


def parse_query(
    session: Session, owner_id: int, text: str, provider: str | None = None,
    usage_out: dict | None = None,
) -> dict:
    provider = (provider or config.LLM_PROVIDER).lower()
    if provider == "mock":
        return _mock_parse_query(session, owner_id, text)
    prompt = _PROMPT_TEMPLATE.format(schema=json.dumps(SEARCH_FIELDS, indent=2), query=text.strip()[:500])
    raw = llm.complete_json(prompt, provider=provider, usage_out=usage_out)
    return _clean(raw)


def _clean(data: dict) -> dict:
    out = {}
    for key in SEARCH_FIELDS:
        value = data.get(key)
        if value in ("", "null", "None", "N/A", "unknown"):
            value = None
        if key in ("min_age", "max_age") and value is not None:
            try:
                value = int(value)
            except (TypeError, ValueError):
                value = None
        if key == "horoscope_available" and isinstance(value, str):
            value = value.strip().lower() == "true"
        if key == "stage" and value not in PIPELINE_STAGES:
            value = None
        out[key] = value
    return out


def apply_filters(session: Session, owner_id: int, filters: dict) -> list[Profile]:
    query = owned(select(Profile), Profile, owner_id)
    if filters.get("gender") in ("Bride", "Groom"):
        query = query.where(Profile.gender == filters["gender"])
    for key, column in _ILIKE_FIELDS.items():
        if filters.get(key):
            query = query.where(column.ilike(f"%{filters[key]}%"))
    if filters.get("min_age") is not None:
        query = query.where(Profile.age >= filters["min_age"])
    if filters.get("max_age") is not None:
        query = query.where(Profile.age <= filters["max_age"])
    if filters.get("food_preference"):
        query = query.where(Profile.food_preference == filters["food_preference"])
    if filters.get("marital_status"):
        query = query.where(Profile.marital_status == filters["marital_status"])
    if filters.get("horoscope_available") is not None:
        query = query.where(Profile.horoscope_available.is_(filters["horoscope_available"]))
    if filters.get("stage"):
        query = query.where(Profile.stage == filters["stage"])
    return list(session.scalars(query.order_by(Profile.created_at.desc())).all())


def describe_filters(filters: dict) -> str:
    parts = [f"{k}={v!r}" for k, v in filters.items() if v is not None]
    return ", ".join(parts) if parts else "no filters recognized — showing all profiles"


# --- mock provider ------------------------------------------------------------

_MAX_AGE_RE = re.compile(r"(?:below|under|younger than|less than|max(?:imum)?)\s+(\d{2})")
_MIN_AGE_RE = re.compile(r"(?:above|over|older than|more than|min(?:imum)?)\s+(\d{2})")
_EXACT_AGE_RE = re.compile(r"\bage[d]?\s+(\d{2})\b")


def _mock_parse_query(session: Session, owner_id: int, text: str) -> dict:
    filters: dict = {k: None for k in SEARCH_FIELDS}
    lower = text.lower()

    if any(w in lower for w in ("bride", "girl", "daughter", "woman", "women")):
        filters["gender"] = "Bride"
    elif any(w in lower for w in ("groom", "boy", "son", "man", "men")):
        filters["gender"] = "Groom"

    if m := _MAX_AGE_RE.search(lower):
        filters["max_age"] = int(m.group(1))
    if m := _MIN_AGE_RE.search(lower):
        filters["min_age"] = int(m.group(1))
    if filters["min_age"] is None and filters["max_age"] is None:
        if m := _EXACT_AGE_RE.search(lower):
            filters["min_age"] = filters["max_age"] = int(m.group(1))

    if "non-vegetarian" in lower or "non vegetarian" in lower:
        filters["food_preference"] = "Non-Vegetarian"
    elif "eggetarian" in lower:
        filters["food_preference"] = "Eggetarian"
    elif "vegetarian" in lower:
        filters["food_preference"] = "Vegetarian"

    if "horoscope" in lower:
        if any(w in lower for w in ("pending", "missing", "without", "no horoscope")):
            filters["horoscope_available"] = False
        elif any(w in lower for w in ("available", "have", "ready", "with horoscope")):
            filters["horoscope_available"] = True

    # Skip single common words like "New" — too likely to false-match
    # unrelated text (e.g. "New Delhi"); the LLM-backed parser handles
    # these correctly via semantic understanding, this is the offline
    # fallback only.
    for stage in PIPELINE_STAGES:
        if len(stage.split()) > 1 and stage.lower() in lower:
            filters["stage"] = stage
            break

    for key, column in _ILIKE_FIELDS.items():
        # distinct values are matched from the OWNER's data only — matching
        # against other tenants' values would leak their vocabulary here.
        values = session.scalars(
            select(column).distinct().where(column.is_not(None), Profile.owner_user_id == owner_id)
        ).all()
        for v in values:
            if v and v.lower() in lower:
                filters[key] = v
                break

    return filters
