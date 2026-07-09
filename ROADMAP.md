# AI-SoulMatch — Roadmap & Open Items

Snapshot as of 2026-07-10, when local hosting was first set up. Update this
file as items are closed or reprioritized — it's the single source of truth
for "what's left."

## MVP status: functional, hosted locally, not yet hardened for unattended production use

All PRD Phase 1–3 features are built and tested (WhatsApp export ingestion,
AI profile extraction, duplicate detection, document repository, practical
+ astrology matching, AI recommendations, tasks/reminders, natural language
search, quick insights, and role-based accounts). What's below is what's
left before this should be trusted with real matrimonial data long-term, or
extended further.

---

## 1. Before real use — do these now

- [ ] **Firewall / network profile.** This network is currently set to
      "Public" — Windows Firewall blocks inbound connections from other
      devices by default. Either switch the network to "Private" (only if
      you trust it) or add an explicit firewall rule. See README → Local
      Hosting for exact commands. Until this is done, only this machine can
      reach the app even though it's bound to `0.0.0.0`.
- [ ] **Real LLM key.** `LLM_PROVIDER=mock` in `.env` right now — extraction,
      search parsing, and AI recommendations all fall back to regex/rule-based
      logic. Functional, but noticeably lower quality than a real model. Add
      a Gemini (free tier) or Anthropic key to `.env` when ready.
- [ ] **Change the bootstrap admin password.** A fresh one was generated for
      this session — treat it as a secret. Log in, change it (sidebar), or
      create a personal named admin account via the Users page and
      deactivate `admin`.
- [ ] **Decide on persistence.** Right now the app only runs while
      `run_local.ps1`'s terminal (or the background process it started) is
      alive. Decide: manual start each session, Task Scheduler at logon, or
      a proper Windows service (NSSM) — see README.
- [ ] **Set up backups.** No automated backup exists for `data/soulmatch.db`
      or `uploads/`. Point a scheduled copy at another drive or cloud folder
      before this holds real profiles you can't afford to lose.

## 2. Production hardening — should do soon, not blocking

- **HTTPS.** Streamlit's built-in server is plain HTTP. Fine for a trusted
  same-building LAN; if this is ever exposed beyond that (e.g. port-forwarded
  to the internet), it needs a reverse proxy (nginx/Caddy) with TLS in front
  — never port-forward this directly.
- **SQLite → PostgreSQL, if usage grows.** Fine for a handful of concurrent
  volunteers; if write concurrency becomes a bottleneck, switching is a
  `DATABASE_URL` change only (SQLAlchemy, no dialect-specific types used
  anywhere in the schema) — no code changes needed.
- **No audit trail.** Activity/Task/Document/MatchResult records don't track
  *which user* performed an action, only that it happened. Worth adding
  `created_by_user_id` columns if per-volunteer accountability matters.
- **No CI.** 68 tests exist and pass locally, but nothing runs them
  automatically on push. Worth a GitHub Actions workflow if more than one
  person will contribute code.
- **No login rate-limiting.** Brute-force risk on the login form. Low
  priority for a small trusted user base; matters more if this is ever
  internet-facing.
- **No CSV/Excel export** of the profile list or search results — a common
  practical need for a coordinator working offline or sharing with a family.
- **No process monitoring.** If the server crashes, nothing restarts it or
  alerts anyone. Relevant once persistence (Task Scheduler/NSSM) is set up.

## 3. Deferred by design — explicit decisions made this session, not oversights

- **WhatsApp live capture (Business API).** Chat-export-file ingestion only.
  Deliberate: avoids the account-ban risk of unofficial live-automation
  bridges. A live source can be added later behind the same `RawMessage`
  ingestion point without touching the rest of the pipeline.
- **Multi-language UI.** English only (+ Telugu astrology term display) —
  explicitly confirmed sufficient for now.
- **Family/Bride/Groom self-service portal & roles.** No UI exists for these
  PRD-listed roles yet. Current roles (Administrator/Volunteer/Coordinator/
  Viewer) are staff-facing only.
- **Mobile apps.** Out of scope for this Streamlit MVP.
- **Community-specific matching rule sets.** The practical matching rules
  (religion/gothram mandatory; age/height/caste/location/etc. weighted) are
  defined in code (`soulmatch/matching/rules.py`), not editable via an admin
  UI. Fine for one community's conventions; would need a rules-editor UI to
  support multiple communities with different criteria.

## 4. Nice-to-have enhancements — not started, no urgency

- Admin-configurable matching rules (weights / mandatory-vs-optional) via UI
  instead of code.
- AI-generated biodata PDF export for a profile.
- Voice-note transcription from WhatsApp exports (voice notes currently show
  as media attachments but aren't transcribed — text messages only).
- Calendar integration for meeting scheduling.
- Consent management / privacy controls (mark a profile private, data
  retention policy).
- Push/email/WhatsApp delivery for task reminders (currently a board you
  check, not a notification).
- Photo thumbnails in the Documents section (currently filename + download
  button only).
- Deeper analytics on successful-match patterns over time.

## 5. Known limitations — working as designed, worth knowing

- Duplicate detection is a soft warning, not a hard block — a determined
  double-entry can still happen.
- Astrology uses Swiss Ephemeris's Moshier model (no external ephemeris data
  files) — accurate for nakshatra/rashi/lagna/koota purposes, not the
  highest-precision mode Swiss Ephemeris can offer with downloaded ephemeris
  files (irrelevant at this use case's precision requirements).
- The Search page's "Best Match Finder" ranks by practical compatibility
  only (not full astrology) for response speed — drill into the Matching
  page for the complete picture on any specific candidate.
