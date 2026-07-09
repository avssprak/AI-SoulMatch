# AI-SoulMatch

AI-powered matrimonial intelligence platform — MVP implementing WhatsApp chat-export
ingestion, AI profile extraction, duplicate detection, a document repository,
practical rule-based screening, and Vedic Ashta Koota astrology matching, on a
Streamlit dashboard.

## Setup

```powershell
# 1. Create/activate the venv (Python 3.12)
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure
copy .env.example .env
# edit .env: set LLM_PROVIDER=gemini and GEMINI_API_KEY=... to use real extraction,
# or leave LLM_PROVIDER=mock to run fully offline with regex-based extraction.

# 4. Run
streamlit run app.py
```

## How it works

- **Ingest**: upload a WhatsApp "Export Chat" `.txt` or `.zip` file. Messages are
  parsed and stored; each message can then be run through the extraction agent to
  produce a structured profile. Before saving, the pending profile is checked
  against existing same-gender profiles for likely duplicates (matching phone,
  DOB, or a fuzzy name match) and flagged for review — the volunteer can still
  save anyway if it's a genuine new profile.
- **Profiles**: search, edit, and move profiles through the CRM pipeline stages
  (New → AI Extracted → ... → Marriage/Rejected/Closed), with an activity timeline,
  a **Documents** section (upload/download/delete biodata PDFs, horoscopes, photos,
  family photos, certificates — stored under `uploads/<profile_id>/`), and the
  same duplicate check when adding a profile manually.
- **Matching**: pick a bride and groom, run the configurable practical-criteria
  rule engine (religion/gothram are mandatory; age/height/caste/location/etc. are
  weighted), and — if both have DOB, birth time, and birth place — compute a full
  Ashta Koota (Guna Milan) score with Manglik/Rajju/Vedha dosha checks.
- **Astrology**: standalone chart lookup for verifying a single horoscope.
- **Dashboard**: pipeline funnel, score distribution, recent activity.

## Architecture notes

- Database is SQLite by default (`data/soulmatch.db`); the `DATABASE_URL` env var
  switches to PostgreSQL later without code changes (SQLAlchemy, no dialect-specific
  types used).
- Astrology uses Swiss Ephemeris's built-in Moshier model (`pyswisseph`, no external
  ephemeris data files needed) with Lahiri ayanamsa, plus an offline city database
  (`geonamescache` + `timezonefinder`) for birth-place geocoding — no network calls.
- LLM extraction is provider-pluggable (`soulmatch/extraction/llm.py`): `gemini`
  (Google AI Studio free tier), `anthropic`, or `mock` (offline regex fallback).
- WhatsApp ingestion works off exported chat files only (no live bridge) — see
  `soulmatch/ingest/whatsapp_export.py`. This keeps the WhatsApp account safe from
  automation bans; a live-capture source can be added later behind the same
  `RawMessage` ingestion point.
- Duplicate detection (`soulmatch/duplicates.py`) uses exact phone/WhatsApp match,
  DOB match, and stdlib `difflib` fuzzy name similarity — no extra dependency, no
  network call. Photo/horoscope similarity is a later-phase enhancement.
- Documents (`soulmatch/documents.py`) are stored on local disk under `uploads/`;
  uploaded filenames are sanitized (basename + random prefix) so a crafted
  filename can't escape the profile's upload directory.

## Tests

```powershell
pytest
```
