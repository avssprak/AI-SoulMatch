"""Profile Extraction Agent: WhatsApp message text -> structured profile dict.

Field names match soulmatch.models.Profile columns so results can be applied
directly. The mock provider gives a keyless regex fallback.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime

from .. import config
from . import llm

PROFILE_FIELDS = {
    "full_name": "string",
    "gender": '"Bride" or "Groom" (bride = female seeking groom, groom = male)',
    "age": "integer years",
    "dob": "date of birth, ISO format YYYY-MM-DD",
    "birth_time": 'time of birth, 24h "HH:MM"',
    "birth_place": "city/town of birth",
    "father_name": "string",
    "mother_name": "string",
    "siblings": "string description",
    "family_details": "string",
    "phone": "string, digits with country code if present",
    "whatsapp": "string",
    "email": "string",
    "religion": "string",
    "caste": "string",
    "sub_caste": "string",
    "gothram": "string",
    "nakshatra": "birth star, e.g. Rohini",
    "rashi": "moon sign, e.g. Vrishabha/Taurus",
    "lagna": "ascendant if mentioned",
    "horoscope_available": "boolean",
    "manglik": '"Yes", "No", "Partial" or null',
    "doshas": "string listing doshas mentioned",
    "qualification": "highest education, e.g. B.Tech, MBBS",
    "university": "string",
    "occupation": "string",
    "company": "string",
    "salary": "string as stated, e.g. 25 LPA",
    "current_location": "city",
    "native_place": "string",
    "country": "string",
    "height_cm": "number in centimeters (convert 5'6\" -> 167.6)",
    "weight_kg": "number",
    "food_preference": '"Vegetarian", "Non-Vegetarian", "Eggetarian" or null',
    "marital_status": '"Never Married", "Divorced", "Widowed" or null',
    "expectations": "object with any partner preferences (age, height, location, qualification, profession, caste...)",
    "notes": "anything important that does not fit above",
}

_PROMPT_TEMPLATE = """You are a matrimonial profile extraction agent for an Indian community \
matchmaking service. The text below is a WhatsApp message (possibly informal, mixing English \
with Indian languages) describing a bride or groom.

Extract every piece of information into a single JSON object with exactly these keys \
(use null for anything not mentioned; never invent data):

{schema}

Rules:
- Heights like 5'6", 5.6 ft, 168 cms must be converted to centimeters (number).
- If the message describes someone seeking a match FOR their son -> gender "Groom"; \
for their daughter -> gender "Bride".
- "confidence": add this extra key, 0-1, how confident you are this is a matrimonial profile.
- If the text is clearly NOT a matrimonial profile (greetings, admin talk), return \
{{"confidence": 0}}.

Message:
---
{message}
---

Respond with ONLY the JSON object."""


def is_likely_profile(text: str) -> bool:
    """Cheap pre-filter so we don't burn LLM calls on 'Good morning' messages."""
    if len(text) < 60:
        return False
    keywords = (
        "bride", "groom", "alliance", "match", "marriage", "matrimon", "biodata",
        "caste", "gothram", "gotra", "nakshatra", "rashi", "star", "dob",
        "height", "qualification", "employed", "working", "salary", "settled",
        "b.tech", "mbbs", "mba", "engineer", "software",
    )
    lower = text.lower()
    return sum(1 for k in keywords if k in lower) >= 2


def extract_profile(text: str, provider: str | None = None) -> dict:
    provider = (provider or config.LLM_PROVIDER).lower()
    if provider == "mock":
        return _mock_extract(text)
    schema = json.dumps(PROFILE_FIELDS, indent=2)
    prompt = _PROMPT_TEMPLATE.format(schema=schema, message=text.strip()[:8000])
    result = llm.complete_json(prompt, provider=provider)
    return _clean(result)


def _clean(data: dict) -> dict:
    out = {}
    for key in list(PROFILE_FIELDS) + ["confidence"]:
        value = data.get(key)
        if value in ("", "null", "None", "N/A", "unknown", "Unknown"):
            value = None
        out[key] = value
    # normalize dob to a real date object (Profile.dob is a SQL Date column)
    if out.get("dob"):
        try:
            out["dob"] = datetime.fromisoformat(str(out["dob"])[:10]).date()
        except ValueError:
            out["notes"] = f"Unparsed DOB: {out['dob']}. " + (out.get("notes") or "")
            out["dob"] = None
    return out


# --- mock provider -----------------------------------------------------------

_PHONE = re.compile(r"(?:\+91[\s\-]?)?[6-9]\d{4}[\s\-]?\d{5}")
_AGE = re.compile(r"\bage[:\s]*(\d{2})\b", re.I)
_HEIGHT_FT = re.compile(r"(\d)\s*['’.]\s*(\d{1,2})\s*[\"”]?")
_HEIGHT_CM = re.compile(r"(\d{3})\s*cms?\b", re.I)
_NAME = re.compile(r"name[:\s]+([A-Za-z .]{3,40})", re.I)
_DOB = re.compile(r"(?:dob|date of birth)[:\s]*([\d/\-.]{8,10})", re.I)


def _mock_extract(text: str) -> dict:
    out: dict = {k: None for k in PROFILE_FIELDS}
    if m := _NAME.search(text):
        out["full_name"] = m.group(1).strip().rstrip(".")
    if m := _PHONE.search(text):
        out["phone"] = m.group(0)
    if m := _AGE.search(text):
        out["age"] = int(m.group(1))
    if m := _HEIGHT_CM.search(text):
        out["height_cm"] = float(m.group(1))
    elif m := _HEIGHT_FT.search(text):
        out["height_cm"] = round(int(m.group(1)) * 30.48 + int(m.group(2)) * 2.54, 1)
    if m := _DOB.search(text):
        raw = m.group(1).replace(".", "/").replace("-", "/")
        parts = raw.split("/")
        if len(parts) == 3:
            d, mth, y = parts
            if len(y) == 2:
                y = ("19" if int(y) > 30 else "20") + y
            try:
                out["dob"] = date(int(y), int(mth), int(d))
            except ValueError:
                pass
    lower = text.lower()
    if any(w in lower for w in ("bride", "daughter", "girl")):
        out["gender"] = "Bride"
    elif any(w in lower for w in ("groom", "son", "boy")):
        out["gender"] = "Groom"
    if "vegetarian" in lower and "non-vegetarian" not in lower and "non vegetarian" not in lower:
        out["food_preference"] = "Vegetarian"
    out["confidence"] = 0.5 if is_likely_profile(text) else 0.1
    out["notes"] = "Extracted with offline mock provider — verify all fields."
    return out
