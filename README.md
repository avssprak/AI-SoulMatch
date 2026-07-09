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

On first run, a default admin account is created automatically — username
`admin`, password `changeme123` (or whatever you set `BOOTSTRAP_ADMIN_USERNAME` /
`BOOTSTRAP_ADMIN_PASSWORD` to in `.env` before that first run). **Change the
password immediately** via the sidebar "Change password" panel, or create your
own admin account via the Users page and deactivate the default one.

## Local Hosting

`run_local.ps1` starts the app bound to `0.0.0.0:8501` (not just `localhost`),
so other devices on the same Wi-Fi/LAN can reach it at `http://<this-machine's-LAN-IP>:8501`:

```powershell
.\run_local.ps1
```

**Windows Firewall / network profile:** if your network connection is set to
"Public" (Windows' default for unrecognized networks), inbound connections
from *other* devices are blocked by default even though the server is
listening — only this machine can reach itself. Either:

- Switch the network to "Private" in Settings → Network & Internet (only do
  this for a network you actually trust, e.g. your home/office Wi-Fi), or
- Allow the port explicitly, from an **elevated** (Run as Administrator) PowerShell:
  ```powershell
  New-NetFirewallRule -DisplayName "AI-SoulMatch" -Direction Inbound -Protocol TCP -LocalPort 8501 -Action Allow
  ```

**Persistence across reboots:** `run_local.ps1` runs in the foreground of
whatever terminal launches it — closing that terminal stops the app. For a
volunteer team that needs this always available, set it up as a scheduled
task that starts at logon (Task Scheduler → Create Task → Trigger: "At log
on" → Action: run `powershell.exe -File run_local.ps1`), or use a tool like
[NSSM](https://nssm.cc/) to register it as a proper Windows service.

**Backups:** nothing backs up `data/soulmatch.db` (all profiles/matches/tasks)
or `uploads/` (documents/photos) automatically. If this machine's disk fails,
that data is gone. Point a scheduled copy of both folders at another drive or
cloud-synced folder.

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
  Ashta Koota (Guna Milan) score with Manglik/Rajju/Vedha dosha checks. From there,
  generate an **AI Recommendation** — a narrative summary (strengths, concerns,
  questions to ask the families, family/lifestyle/career compatibility, final
  verdict) via the configured LLM provider — before saving the match result.
- **Astrology**: standalone chart lookup for verifying a single horoscope, with
  nakshatra/rashi/lagna shown in both English/Sanskrit and Telugu.
- **Tasks**: per-profile task list (Call parents, Collect horoscope, Upload
  biodata, Follow up after meeting, Schedule second meeting, or custom) with
  due dates; a global Tasks page filters by status and surfaces overdue items
  as the reminder mechanism.
- **Dashboard**: pipeline funnel, score distribution, pending/overdue task
  counts, recent activity.
- **Users** (Administrator only): create accounts, assign roles, deactivate/
  reactivate, reset passwords.
- **Search & Insights**: a natural-language search box ("Brahmin brides in
  Bangalore under 28 with a horoscope") translated into structured profile
  filters, plus a Quick Insights panel — pending horoscope, incomplete
  profiles, top astrology-scored matches, stale cases (no activity in 14+
  days), and a best-match finder for any profile.

## Accounts & roles

Sign-in is required for every page. Four staff-facing roles (the PRD's
Family/Bride/Groom self-service roles are deferred to a future parent-portal
phase — there's no UI surface for them yet):

| Role | Can do |
|---|---|
| **Administrator** | Everything, plus the Users page (create accounts, assign roles, deactivate, reset passwords) |
| **Volunteer** / **Coordinator** | Full read/write: ingest, edit profiles, upload documents, manage tasks, evaluate and save matches |
| **Viewer** | Read-only: browse profiles/documents/tasks/matches and evaluate matches, but cannot save, edit, upload, or ingest anything |

Any signed-in user can change their own password from the sidebar.

## Architecture notes

- Database is SQLite by default (`data/soulmatch.db`); the `DATABASE_URL` env var
  switches to PostgreSQL later without code changes (SQLAlchemy, no dialect-specific
  types used).
- Astrology uses Swiss Ephemeris's built-in Moshier model (`pyswisseph`, no external
  ephemeris data files needed) with Lahiri (Chitrapaksha) ayanamsa — the same
  ayanamsa used by the Rashtriya Panchang and the great majority of regional
  panchangams, including Telugu ones — plus an offline city database
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
- AI recommendations (`soulmatch/recommendation.py`) reuse the same pluggable
  LLM provider as extraction, with a deterministic offline template when
  `LLM_PROVIDER=mock`. The Matching page persists the generated recommendation
  JSON in `MatchResult.notes` when a match is saved.
- Tasks (`soulmatch/tasks.py`, `models.Task`) are a lightweight reminder
  mechanism: no push/email/WhatsApp delivery in this MVP, "reminders" surface
  as overdue/upcoming counters on the Dashboard and a filterable board on the
  Tasks page that a volunteer checks.
- Auth (`soulmatch/auth.py`) is server-side session state, not JWT — this is
  a single-process Streamlit app, not a multi-service API, so a signed token
  would add complexity (secret rotation, cookie storage) without a security
  benefit over `st.session_state`. Passwords are hashed with PBKDF2-HMAC-SHA256
  (stdlib `hashlib`, no extra dependency), the same scheme Django uses by
  default. Each page calls `auth.require_login()` itself (not just `app.py`)
  since Streamlit pages are independently runnable scripts.
- Natural language search (`soulmatch/search.py`) translates free text into a
  structured filter object, never a raw query string — the LLM (or offline
  mock parser) only ever fills in known fields, so there's no SQL injection
  surface. The mock parser matches distinct values already in the database
  (religion, caste, location, ...) against the query text, so it adapts to
  real data without a hardcoded vocabulary.
- Quick Insights (`soulmatch/insights.py`) are deterministic database queries,
  not LLM calls — questions like "which profiles are incomplete" or "who has
  the highest horoscope score" don't need natural-language reasoning to
  answer correctly, so they're free and instant. The LLM is reserved for
  where free text genuinely needs interpretation (search parsing, match
  narratives).

## Tests

```powershell
pytest
```

## Roadmap & Open Items

See [ROADMAP.md](ROADMAP.md) for the current punch list — what to do before
trusting this with real data long-term, production-hardening items, features
deliberately deferred (and why), and nice-to-have enhancements.
