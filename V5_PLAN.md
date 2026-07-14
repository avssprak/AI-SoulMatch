# V5 Plan — Onboarding, Guidance & Mobile Polish

Source: Product-Owner review of the live app (2026-07-14), after V4 shipped.
Field signal: the few live parents "find it difficult to navigate around."

Executor: Claude Sonnet. Each sprint = one commit, tests green (`pytest`),
verified with `AppTest` + a manual run (`run_local.ps1`). Ship in the order
listed — V5-1 and V5-2 attack the reported problem directly.

## Ground rules

- Reuse existing building blocks: `theme.journey_stepper`, `soulmatch/nav.py`
  page constants + `queue_next_step`, `soulmatch/ui.py` `flash`, the My Child
  wizard pattern in `pages_/0_My_Child.py` (session-state step key + data dict).
- New user columns go through `_COLUMN_MIGRATIONS` in `soulmatch/db.py`
  (same as `astro_weight` did in V4-4-1).
- All copy addresses a parent, not an operator. No jargon ("ingest",
  "extraction", "pipeline") in anything user-visible.

---

## Sprint V5-1 — First-login onboarding wizard

**Problem.** A brand-new account lands on the Dashboard: empty metrics, an
empty funnel gate, a stepper — but nothing *forces* the one action that makes
the app make sense (set up the child). Parents wander the sidebar instead.

1. **V5-1-1 `onboarded_at` column** on `users` (datetime, nullable) via
   `_COLUMN_MIGRATIONS`. Backfill rule: existing users who already have any
   owned Profile count as onboarded (set at migration time or lazily on first
   load — lazy is fine).
2. **V5-1-2 Welcome wizard page** `pages_/00_Welcome.py` (hidden from nav —
   do NOT add it to the `sections` dict; reach it only via `st.switch_page`).
   In `app.py`, immediately after the plan-sync block: if
   `onboarded_at is None` and the current page isn't already Welcome,
   `st.switch_page(WELCOME_PAGE)`. Add `WELCOME_PAGE` to `soulmatch/nav.py`.
   Steps (reuse the `journey_stepper` visual):
   - **Step 1 · Welcome** — 3 short cards: "1. Tell us about your child ·
     2. Add candidates from WhatsApp or biodata · 3. Get horoscope + practical
     match scores." One primary button: "Set up my child →".
   - **Step 2 · My Child** — embed the existing 3-step child wizard. Refactor
     `pages_/0_My_Child.py`'s wizard into a reusable
     `soulmatch/child_wizard.py::render_wizard(on_complete)` so both pages
     share one implementation (acceptance: no copy-paste of the form code).
   - **Step 3 · Done** — set `onboarded_at`, show two buttons:
     "Add your first candidate →" (INGEST_PAGE, primary) and
     "Explore the dashboard" (DASHBOARD_PAGE).
   - A quiet "Skip for now" caption-link on every step sets `onboarded_at`
     and goes to the Dashboard. Never trap the user.
3. **V5-1-3 Tests.** AppTest: new member is routed to Welcome; completing the
   wizard creates an `is_own_child` profile and sets `onboarded_at`; skipping
   sets `onboarded_at`; onboarded users never see Welcome.

**Acceptance:** a fresh signup reaches "child profile saved" in under a
minute without touching the sidebar.

## Sprint V5-2 — In-app user guide ("How it works")

**Problem.** Zero help content in the product. The WhatsApp-export flow in
particular assumes knowledge parents don't have (how to export a chat).

1. **V5-2-1 Guide page** `pages_/10_Guide.py`, nav title "How It Works",
   icon `:material/help:`, placed in the "More" section. Content = one
   expander per journey step, written for a parent:
   - Setting up your child's profile (why birth time matters for the score).
   - Adding candidates — **with an illustrated step-by-step of exporting a
     WhatsApp chat on Android and iPhone** (text + screenshots under
     `assets/guide/`; if screenshots aren't available, ship numbered text
     steps now, mark screenshots as a `[HUMAN]` follow-up).
   - Understanding the match score (koota %, practical %, the astro-weight
     slider, what red/amber/green mean).
   - Follow-ups and the pipeline stages.
   - Plans & billing FAQ (caps, AI actions, pause/resume).
   Keep copy in `soulmatch/guide_content.py` as markdown constants so tests
   can assert sections exist and future i18n has one file to translate.
2. **V5-2-2 Contextual help links.** Add a small `theme.help_link(anchor)`
   helper — a caption-level "❓ How does this work?" that switches to the
   Guide page with `st.session_state["guide_anchor"]` set, and the Guide
   auto-expands that section. Place on: Ingest (export how-to), Match &
   Compare scoreboard (score explanation), My Child (birth-details why),
   My Plan (billing FAQ).
3. **V5-2-3 Guide entry points.** Dashboard: add "New here? Read how it
   works →" caption under the journey stepper until all 4 steps are done.
   Landing page footer: no change (marketing FAQ already exists there).

**Acceptance:** every page that has a help link lands on the right expanded
guide section; guide renders with no horizontal scroll at 390 px width.

## Sprint V5-3 — Mobile responsiveness for the authenticated app

**Problem.** `theme.py` has **no `@media` queries** (the landing page does).
Parents are WhatsApp-first phone users. Known breakpoints that fail on a
~390 px viewport: `.sm-stepper` (fixed flex row, 4 cards squeeze),
`.sm-page-title` at 2.15 rem, metric 4-column rows (Streamlit stacks columns
but the metric cards + their action buttons get tall/noisy), plan cards,
dataframes.

1. **V5-3-1 Add a mobile block to `_CSS`** in `theme.py`:
   - `@media (max-width: 640px)`: `.sm-stepper { flex-wrap: wrap; }` with
     `.sm-step { flex: 1 1 45%; }` (2×2 grid); `.sm-page-title` → 1.6 rem;
     `.block-container` side padding → 1rem; `.sm-empty` padding → 24px 16px.
   - Buttons inside metric rows: full-width (`.stButton button { width:100%; }`
     scoped under a wrapper class if needed — do not make every app button
     full-width on desktop).
2. **V5-3-2 Dashboard column audit.** Change the two 4-metric rows to
   `st.columns(4)` → keep, but move each metric's action into the metric's
   `help`/caption OR a single "Go" link under it — verify stacking order on
   mobile reads metric → action → next metric. The "Today" digest rows
   (`st.columns([5,1])`) squeeze the Go button to a sliver on phones: switch
   to full-width buttons under each item at ≤640 px, or use one column with
   inline link-buttons.
3. **V5-3-3 Manual verification pass** at 390 px and 768 px via browser
   devtools on: Landing/login, Dashboard, My Child wizard, Ingest, Candidates
   drawer, Match scoreboard, My Plan. Fix what's broken; record findings in
   the commit message.

**Acceptance:** no horizontal scrolling and no unreadable/overlapping text on
any page at 390 px; stepper wraps 2×2; login card usable on a phone.

## Sprint V5-4 — Navigation & settings coherence (quick wins)

1. **V5-4-1 Separate Settings from billing.** Move timezone (and future
   preferences) out of `pages_/9_My_Plan.py` into an "Account" expander or
   section — simplest: keep on My Plan but retitle page nav to
   "My Plan & Settings" and add an anchor section "Account settings"
   (timezone, change-password moved here from the sidebar expander). The
   sidebar keeps only identity + Log out.
2. **V5-4-2 Dashboard de-clutter for early users.** When `total < 3`
   profiles: hide the two metric rows entirely (not just the charts) — show
   only Today digest + journey stepper + guide link. The full dashboard
   appears once there's data worth glancing at.
3. **V5-4-3 Consistent CTA labels.** Sweep the repeated "Go →" buttons on
   Dashboard: label each with its destination ("Open Follow-Ups →",
   "Review imports →", …) — screen-reader and scannability win. Acceptance:
   no two adjacent buttons with identical labels on the Dashboard.
4. **V5-4-4 Admin label.** Rename admin nav "Customers" → "Members"
   (matches the Member role terminology used everywhere else).
5. **V5-4-5 Birth details on the Add Manually form** (field-visit finding,
   2026-07-14). The manual-add form on `pages_/3_Profiles.py` (~line 673)
   captures DOB but not **Birth Time** or **Birth Place** — yet those two
   are exactly what `is_match_ready` needs for the astrology score, so
   manually-added candidates are born not-match-ready and the parent only
   finds out later. Add to the DOB row (or a row below):
   - `Birth Time (24h HH:MM)` text input and `Birth Place` text input —
     same widgets/labels as the edit drawer (~line 412-416) and the My Child
     wizard step 2, for consistency.
   - Include both in `pending_manual_profile` and the created `Profile`.
   - After create, if birth place was given but `geo_lookup(birth_place)`
     is None, show the same "not found in the offline place database" info
     the edit drawer shows (reuse that copy).
   - Group the form visually: "Basics" (name/gender/age) then
     "Birth details — needed for the horoscope score" (DOB/time/place) then
     "Background" (religion/caste/gothram/qualification/occupation), using
     `st.caption` row headers. Acceptance: a candidate created manually with
     DOB+time+place shows as ✅ match-ready in the drawer with no edit step.

## Sprint V5-5 — Security & robustness follow-ups (from this review)

1. **V5-5-1 Session token out of the URL.** `?token=` in the query string
   leaks via copied/shared links and screenshots. Replace with a cookie
   (e.g. `streamlit-cookies-controller` or `st.context.cookies` read + a
   small JS set via `st.markdown`) — keep the signed-token format and
   `validate_session_token` unchanged; only the transport moves. Must survive
   refresh exactly as today. If a reliable cookie write proves impractical in
   Streamlit, fallback: keep the URL token but shorten its TTL and re-mint on
   every load, and strip it from the URL after restoring the session
   (`del st.query_params["token"]` post-restore, re-set only on login).
2. **V5-5-2 Self-hosted fonts.** `@import` of Google Fonts in `theme.py` is
   a render-blocking third-party call (and fails offline). Download the two
   families into `static/fonts/`, serve via `@font-face`. Landing page too.

## Sprint V5-6 — Email verification at signup

**Problem.** `auth.register_member` creates the account and logs it straight
in — any string that looks like an email works. No proof of ownership, so
quota abuse via throwaway signups is trivial and password reset (future) has
no trustworthy address.

1. **V5-6-1 SMTP plumbing.** `soulmatch/mailer.py`: `send_email(to, subject,
   body_md)` using stdlib `smtplib` + `email.message.EmailMessage`. Config in
   `soulmatch/config.py` from env: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`,
   `SMTP_PASSWORD`, `SMTP_FROM`, `APP_BASE_URL`. Add to `.env.example` with a
   `[HUMAN]` note (e.g. an SES/Zoho/Brevo account must be provisioned).
   If `SMTP_HOST` is unset, `mailer.is_configured()` is False and the whole
   verification gate below is bypassed (dev/local keeps working untouched).
2. **V5-6-2 Verification flow.** Columns on `users` via `_COLUMN_MIGRATIONS`:
   `email_verified_at` (datetime, nullable), plus a `verification_code`
   (6-digit) and `verification_sent_at`. Flow — code entry, not a click-link:
   Streamlit is a poor target for deep-link callbacks, and parents on phones
   handle "enter the 6-digit code we emailed you" more easily.
   - On signup: create the account **unverified**, email the code, and show
     a code-entry form in the signup tab (don't log in yet).
   - Correct code within 30 min → set `email_verified_at`, log in, proceed
     to onboarding (V5-1). Wrong code → error; 5 wrong tries or expiry →
     "Resend code" button (rate-limit: max 3 sends per hour per email).
   - On sign-in: if the user is unverified (and mailer configured), block
     with the same code-entry + resend UI instead of a session.
   - Backfill: existing users get `email_verified_at = now` at migration
     time — never lock out the live cohort.
3. **V5-6-3 Tests.** Monkeypatch the mailer; cover: signup sends code and
   does not create a session; correct/wrong/expired code paths; resend
   rate limit; unverified sign-in blocked; mailer-unconfigured bypass;
   pre-existing users unaffected.

**Acceptance:** with SMTP configured, no session is ever minted for an
account whose email was never verified; with SMTP unconfigured, behavior is
exactly today's (so local dev and tests don't need a mail server).

## Backlog (not this release — evaluate after V5 ships)

- **AI weekly digest**: one AI action per week summarizing "what moved, what
  to do next" on the Dashboard (Plus/Pro).
- **Draft a WhatsApp reply**: from a candidate drawer, AI-draft a polite
  inquiry/decline message the parent can copy — high delight, low effort.
- **i18n groundwork** (Telugu/Hindi): the guide-content module (V5-2-1) is
  the pilot surface.
- **PWA/manifest** so the app installs to the phone home screen.

## Suggested sequence & dependencies

1. V5-1 (onboarding) — depends on nothing; refactor of child wizard first.
2. V5-2 (guide) — independent; do after V5-1 so Welcome can link to it.
3. V5-3 (mobile CSS) — independent; verify V5-1/V5-2 pages in the same pass.
4. V5-4 (quick wins) — small, anytime after V5-1.
5. V5-5 (security/perf) — independent; V5-5-1 needs its own careful testing
   (login, refresh, logout-everywhere, password change re-mint).
6. V5-6 (email verification) — code can ship anytime (it self-disables
   without SMTP config), but schedule the [HUMAN] SMTP provisioning before
   flipping it on in production. Do V5-4-5 (birth fields on manual add)
   immediately — it's a 30-minute fix for a live data-quality leak.
