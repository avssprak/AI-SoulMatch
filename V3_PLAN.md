# AI-SoulMatch — V3 Plan: Multi-Tenant SaaS under the RedPrana Brand

Created 2026-07-11. This is the **execution backlog for the V3 release** — the
pivot from a shared-workspace staff tool to a **subscription SaaS for
individual customers** (a parent, or any individual managing a marriage
search). Everything in "How to work on any task" in `SPRINT_PLAN.md`
(conventions, verification via pytest + `AppTest`, Streamlit pitfalls) applies
verbatim to every task here. V2_PLAN.md (UX/product polish) remains valid;
V3 tasks below note where they touch the same surfaces.

Companion financial model: `docs/AI-SoulMatch_Unit_Economics.xlsx`
(tier pricing, per-action API costs, break-even ≈ 8–9 paid subscribers).

---

## Part 0 — Decisions locked in (do not re-litigate in tasks)

| Decision | Value |
|---|---|
| Customer model | **Single customer-facing role: `Member`.** A Member is a parent or individual; each Member sees **only their own data** (hard tenant isolation). One internal `Admin` role remains for the operator (support, metrics, plan management). The old Volunteer/Coordinator/Viewer roles are retired. |
| Business model | Monthly subscription, 3 tiers: **Free / Plus ₹149 / Pro ₹399** (annual: ₹1,499 / ₹3,999). Metered by "AI actions". |
| NRI tiers | Same product, USD price list for international customers: **Plus $4.99/mo, Pro $9.99/mo** (annual $49/$99). Detected by billing choice, not geo-IP guessing. |
| Brand | Product of **RedPrana**. App lives at **soulmatch.redprana.com** (domain already owned, DNS at GoDaddy). Product name: "SoulMatch by RedPrana". |
| LLM | Pluggable layer stays (`soulmatch/extraction/llm.py`). Default paid path: Gemini Flash. Cost model assumes paid-tier pricing (~₹0.31/action blended). |
| Free tier limits | 1 child/search, 25 candidate profiles, 15 AI actions/mo, unlimited koota scores (local/free), **no** AI explanations or NL search. |
| Plus limits | 1 child, unlimited profiles, 150 AI actions/mo, all AI features, 1 bulk WhatsApp import/mo. |
| Pro limits | 3 children, 500 AI actions/mo (fair use), unlimited bulk import, unlimited compare. |
| Payments | Razorpay (UPI Autopay) for INR; Stripe for USD/NRI. Web billing only — never in-app purchases. |
| Privacy stance | Private-by-default forever. No public profiles, no cross-tenant discovery in V3. |

---

## Part 1 — What changes architecturally (read before any sprint)

Today (`soulmatch/models.py`, `soulmatch/auth.py`): staff roles
(`Administrator/Volunteer/Coordinator/Viewer`), one shared profile pool,
records carry `created_by_user_id` for audit only. **Every query in the app
returns all rows.**

V3 target: every domain row (Profile, MatchResult, Task, Document, Note,
saved searches, activity log) carries a **non-null `owner_user_id`**, and
every read/write path filters on it. This is the single riskiest change in
the plan: a missed filter is a privacy breach, not a bug. Hence Sprint V3-1
introduces a **scoped-session helper** so filtering is structural, not
per-query discipline.

```
users.role ∈ {"Member", "Admin"}        # Member = customer; Admin = operator
users.plan ∈ {"free", "plus", "pro"}    # + plan_expires_at, billing_currency
ai_usage(user_id, action, tokens_in, tokens_out, cost_estimate, created_at)
subscriptions(user_id, provider, provider_sub_id, status, current_period_end)
```

---

## Part 1.5 — State after V3-1 + rules for every task from V3-2 on (READ FIRST)

V3-1 shipped on 2026-07-12. What a fresh session must know before touching code:

**Current role/tenancy model (supersedes anything older docs say):**
- `ROLES = ["Member", "Admin"]` and `PLANS = ["free", "plus", "pro"]` in
  `soulmatch/models.py`. The SPRINT_PLAN.md AppTest example that uses
  `"role": "Administrator"` is OUTDATED — use `"Admin"` or `"Member"`, and
  the session-state user dict now also carries `"plan"`:
  `{"id": 1, "username": "x", "full_name": None, "role": "Member", "plan": "free"}`.
- Every domain table (Profile, RawMessage, Document, MatchResult, Activity,
  Task) has `owner_user_id`. **Every new query or row-create MUST be
  tenant-scoped** via `soulmatch/tenancy.py`:
  - `owned(select(Model)..., Model, owner_id)` — list queries
  - `get_owned(session, Model, pk, owner_id)` — replaces `session.get()` on
    domain models; returns None cross-tenant
  - `owner_id_of(user_dict)` — the tenant key, called once at page top:
    `current_user = auth.require_login()` then `owner = owner_id_of(current_user)`
  - When creating rows, always set `owner_user_id=owner`.
- `tests/test_tenancy.py` is the permanent isolation suite — it must stay
  green in every task. If you add a new query path, add an isolation test.
- Schema changes: add the column to `models.py` AND to `_COLUMN_MIGRATIONS`
  in `soulmatch/db.py` (create_all only creates missing *tables*). Data
  migrations follow the `_apply_tenancy_migration()` pattern — idempotent,
  safe to run every startup.
- Signup exists (`auth.register_member`), login card in `app.py` has
  Sign in / Create account tabs. `pages_/7_Users.py` is the Admin-only
  Customers page with a manual plan override (V3-3 replaces the manual
  override with webhook-driven plan changes but the override stays as a
  support tool).
- **V3-2 shipped (2026-07-12):** `soulmatch/billing.py` has `PLAN_LIMITS`,
  `record_usage`, `quota_status`/`require_quota` (raises `QuotaExceeded`),
  `can_add_profile`, `can_use_ai_explanations`/`can_use_nl_search`,
  `monthly_usage_summary`. `AiUsage` model exists. `llm.complete_json` and
  its three call sites (`extract_profile`, `generate_recommendation`,
  `parse_query`) all accept an optional `usage_out: dict` filled with
  `tokens_in`/`tokens_out` for real providers (never for mock — mock
  records no usage and is NOT quota-checked, since it costs nothing).
  `pages_/9_My_Plan.py` exists. When building V3-3 checkout/webhooks, wire
  the (currently `disabled=True`) upgrade buttons on My Plan to it, and
  extend `billing.py` with `PRICE_CATALOG` — don't create a second limits
  source.
- **V3-3 shipped (2026-07-12):** `soulmatch/payments.py` (checkout links,
  webhook signature verification + pure `apply_*_event` handlers) and
  `webhook_server.py` (stdlib HTTP sidecar, port 8502 by default — run
  alongside Streamlit, see `run_local.ps1`) both exist. `users.plan_status`
  / `users.plan_grace_until` drive the active/past_due/paused/free
  lifecycle via `billing.effective_plan`/`sync_plan_status`/
  `pause_subscription`/`resume_subscription`. `Subscription` and
  `WebhookEvent` models exist. Gateways are NOT yet connected to real
  accounts — see the `[HUMAN]` note under V3-3's own heading before
  assuming checkout works.
- **V3-4 shipped (2026-07-12):** `Dockerfile`, `docker-compose.yml`,
  `Caddyfile`, `deploy/backup.sh`, `docs/DEPLOY.md`, `docs/RESTORE_DRILL.md`
  all exist and are verified (real `docker build`, real container runs,
  real Caddy validation, a real restore drill against production data —
  see V3-4's own heading for specifics). `soulmatch/errors.py` has the
  optional Sentry hook. Branding: use "SoulMatch by RedPrana" going
  forward, not "AI-SoulMatch" — `page_title`, hero, footer, and login card
  all say this now; match it in any new user-facing copy. The site is NOT
  actually deployed anywhere yet — these are the artifacts a human runs on
  a real VPS, not a running production instance.

**Verification recipe for every V3 task** (extends SPRINT_PLAN.md's):
1. `.venv/Scripts/python.exe -m pytest -q` — all pass (126+ at V3-2 handoff).
2. AppTest each touched page twice: once as `{"role": "Admin", "id": 1}` and
   once as a second seeded Member — assert the Member never sees tenant-1
   data and no exceptions are raised.
3. For DB-effecting flows, assert the rows changed (and carry the right
   `owner_user_id`), not just that the page rendered.

**Windows pitfalls observed during V3-1:**
- NEVER do bulk find/replace on source files with PowerShell `-replace` +
  `Set-Content` — PS 5.1 reads UTF-8 files as cp1252 and corrupts em-dashes
  and emoji (mojibake). Use a small Python script (`pathlib.Path.read_text
  (encoding='utf-8')` / `.write_text(encoding='utf-8')`) for bulk edits.
- When printing emoji/₹ from Python on Windows, wrap stdout first:
  `sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")`.

**Tasks marked `[HUMAN]` need the owner** (account signups, DNS, payments
dashboards). Do NOT stub, fake, or work around them — implement everything
up to the boundary (config keys in `.env.example`, code paths behind them),
then list the exact `[HUMAN]` steps left in your final report.

---

## Part 2 — Sprints

Execute strictly in order — each sprint builds on the previous one's schema
and helpers. **Next up: V3-5.** Work task-by-task, verify per Part 1.5 after
each task, and end every session by updating the sprint's status line here
(✅ DONE date, or a "partially done: …" note listing exactly what remains).

### Sprint V3-1 — Tenant isolation & the Member role  *(the foundation; nothing ships before this)* — ✅ DONE 2026-07-12

- **V3-1-1** Migration: add `owner_user_id` (FK users, indexed) to Profile,
  MatchResult, Task, Document, and every user-data table. Backfill from
  `created_by_user_id` where present; orphan rows go to the bootstrap admin.
  Collapse roles: map all existing staff roles → `Admin` for the operator
  account, everything else → `Member`. Keep `ROLES = ["Member", "Admin"]`.
- **V3-1-2** Scoped data access: add `soulmatch/tenancy.py` with
  `owned(query, user)` / a `scoped_session(user)` wrapper. **Refactor every
  page and module** (profiles, matching, search, tasks, insights, duplicates,
  documents, recommendation) to go through it. Admin bypass is explicit
  (`user.role == "Admin"` and only on the Admin pages).
- **V3-1-3** Tests that prove isolation: two Members, seeded data, assert
  user B can never read/edit/delete/search/match user A's rows on any page.
  This test file is permanent and every future PR must keep it green.
- **V3-1-4** Self-service signup: public register page (email + password,
  email stored for billing/receipts), new accounts are `Member` on `free`.
  Bootstrap admin flow unchanged. Rate-limit signup attempts.
- **V3-1-5** Retire staff-role UI: Users page becomes Admin-only "Customers"
  view (list members, plan, usage, disable account). Remove role pickers
  from any Member-facing surface.

### Sprint V3-2 — Metering, quotas & plan gates — ✅ DONE 2026-07-12

Plan limits are locked in Part 0. Implement them as data, not scattered ifs —
single source of truth `PLAN_LIMITS` in a new `soulmatch/billing.py`:

```python
PLAN_LIMITS = {
    "free": {"ai_actions": 15,  "profiles": 25,   "children": 1,
             "ai_explanations": False, "nl_search": False, "bulk_imports": 0},
    "plus": {"ai_actions": 150, "profiles": None, "children": 1,
             "ai_explanations": True,  "nl_search": True,  "bulk_imports": 1},
    "pro":  {"ai_actions": 500, "profiles": None, "children": 3,
             "ai_explanations": True,  "nl_search": True,  "bulk_imports": None},
}   # None = unlimited
```

- **V3-2-1 `ai_usage` table + recording.** New model in `models.py`
  (+ `_COLUMN_MIGRATIONS` not needed — new table, create_all handles it):
  `AiUsage(id, owner_user_id FK indexed, action String(40), tokens_in Int,
  tokens_out Int, cost_estimate_inr Float, created_at)`.
  `action` values: `"extract"`, `"recommend"`, `"nl_search"`.
  Recording layer: change `llm.complete_json(prompt, provider=None)` to
  return `(parsed_dict, usage)` OR (lower-risk, preferred) add an optional
  `usage_out: dict` param the providers fill with
  `{"tokens_in": int, "tokens_out": int}` — Gemini returns
  `usageMetadata.promptTokenCount/candidatesTokenCount` in the same response;
  Anthropic SDK returns `message.usage.input_tokens/output_tokens`; for
  local/mock record zeros. Then `billing.record_usage(session, owner, action,
  tokens_in, tokens_out)` computes `cost_estimate_inr` from constants
  `LLM_PRICE_IN_USD_PER_MTOK = 0.30`, `LLM_PRICE_OUT_USD_PER_MTOK = 2.50`,
  `USD_INR = 86` (module-level, overridable via .env) and inserts a row.
  Call sites (the ONLY four paid paths): `extraction/extractor.py
  extract_profile` (both Ingest and Profiles use it), `recommendation.py
  generate_recommendation`, `search.py parse_query` (non-mock branch only).
  Mock provider must record nothing.
- **V3-2-2 Quota enforcement.** `billing.quota_status(session, user) ->
  QuotaStatus(used, limit, resets_on)` counting `AiUsage` rows for the
  calendar month (UTC), and `billing.require_quota(session, user)` which
  raises `QuotaExceeded(Exception)` with a ready-to-display message:
  `"You've used 150/150 AI actions this month — upgrade or wait until 1 Aug."`
  Wrap every call site so pages catch `QuotaExceeded` and `st.warning()` it —
  never a stack trace, and never block koota/dosha/rule-matching (those stay
  free and unmetered). Enforce BEFORE the LLM call, record AFTER success
  (a failed LLM call must not consume quota).
- **V3-2-3 Plan gates.**
  - Free + AI explanation: on the Matching page, replace the "Generate AI
    Recommendation" button for free-plan users with a disabled-style teaser:
    koota score still fully shown, plus an `st.info` panel "🔒 **Why this
    match works** — AI match explanations are on the Plus plan (₹149/mo).
    [See plans]" linking to My Plan. Same gate on NL search (8_Search and
    the Profiles-page NL expander): free users see the input disabled with
    the same message.
  - Profile cap: in every Profile-create path (Ingest auto-process, Ingest
    manual save, Profiles Add Manually) call `billing.can_add_profile(
    session, user) -> tuple[bool, str]` first; on False show the message
    ("Free plan stores up to 25 candidate profiles — upgrade to Plus for
    unlimited."). Auto-process should stop at the cap and report how many
    were skipped.
  - Children cap: deferred to V3-6 alongside the "my children" concept —
    the current schema has no child/search entity, do NOT invent one here.
- **V3-2-4 Usage UI.** New page `pages_/9_My_Plan.py` (nav title "My Plan",
  icon `:material/workspace_premium:`, visible to all users): current plan
  card, `st.progress` of actions used / limit with reset date, plan
  comparison table (from PLAN_LIMITS + prices in Part 0), and for now an
  `st.link_button`-style placeholder "Upgrade — payments arrive in V3-3"
  (disabled). Admin extra section on the Customers page: this month's total
  `cost_estimate_inr`, actions by type, top-5 heaviest users.
- **V3-2-5 Tests.** `tests/test_billing.py`: quota counts only the calling
  owner's rows and only the current month; `require_quota` raises at the
  limit; failed-LLM-call-doesn't-record; profile cap at exactly 25;
  free-vs-plus gate flags. Extend `test_tenancy.py`: AiUsage rows are
  owner-scoped.
- **Verification:** AppTest the Matching page as a free Member (teaser
  shows, no LLM call), as a plus Member with mock provider (explanations
  run), and drive a member to their profile cap via the manual-add flow.

### Sprint V3-3 — Billing (Razorpay + Stripe) — ✅ DONE 2026-07-12

**Implementation notes for V3-4+ sessions:** all code-side tasks (V3-3-1
through V3-3-6) are complete and tested (147 tests, incl. 14 in
`tests/test_payments.py` against fixture JSON in `tests/fixtures/`).
`soulmatch/payments.py` holds checkout creation (`create_razorpay_
subscription_checkout`, `create_stripe_checkout_session`), signature
verification, idempotent webhook application (`apply_razorpay_event`,
`apply_stripe_event`), and pause/resume support
(`cancel_subscription_at_period_end`). `webhook_server.py` (repo root) is
the stdlib-only HTTP sidecar — no new dependency added; verified live
end-to-end (valid signature activates a plan, forged signature gets 400).
`billing.py` gained `PRICE_CATALOG`, `effective_plan`/`sync_plan_status`
(paused/past_due/grace lifecycle), `pause_subscription`/
`resume_subscription`. `pages_/9_My_Plan.py` has real checkout buttons
(currency + interval toggle) and a Pause button; `app.py` refreshes
plan/lifecycle from the DB on every page load and shows a past_due/paused
banner. **`[HUMAN]` — nothing works end-to-end until these are done:**
create the Razorpay account + 4 recurring Plans + webhook (secret into
`.env`), create the Stripe account + 4 recurring Prices + webhook (secret
into `.env`), and point each gateway's webhook config at
`https://soulmatch.redprana.com/webhooks/{razorpay,stripe}` once V3-4's
Caddy proxy exists (locally: `http://<ngrok-or-similar>/webhooks/...` for
testing against a public URL, since gateways can't reach `localhost`).
Until those exist, every checkout button shows a support-ready error
instead of a link — this is intentional, not a bug to fix.

Architecture constraint to decide FIRST: Streamlit cannot receive payment
webhooks (it serves a websocket app, not arbitrary HTTP routes). Ship a tiny
sidecar `webhook_server.py` (FastAPI or stdlib http.server, new dependency
needs owner OK) that listens on a second port, shares `soulmatch/` code and
the same DB, and is run alongside Streamlit (update `run_local.ps1` and the
V3-4 Docker Compose). Do not try to hack webhooks into Streamlit.

- **V3-3-1** Plan catalog: `billing.PRICE_CATALOG` mapping
  `(plan, interval, currency)` → `{amount, provider, provider_price_id}` with
  provider IDs read from `.env` (`RAZORPAY_PLAN_PLUS_MONTHLY=...` etc., all
  listed in `.env.example`). Amounts from Part 0 (₹149/₹399, ₹1,499/₹3,999;
  $4.99/$9.99, $49/$99).
- **V3-3-2** `Subscription` model: `(id, owner_user_id FK, provider
  'razorpay'|'stripe', provider_sub_id unique, plan, interval, status,
  current_period_end, created_at, updated_at)`. Razorpay Subscriptions +
  UPI Autopay: `[HUMAN]` create Razorpay account, plans, and webhook secret;
  code side = checkout link generation from My Plan (razorpay python SDK or
  plain REST) and webhook handler for `subscription.activated`, `.charged`,
  `.halted`, `.cancelled` → update Subscription + `users.plan`. Webhooks:
  verify signature (`X-Razorpay-Signature`, HMAC-SHA256 of body with webhook
  secret), and be idempotent — store processed event ids in a
  `webhook_events(provider, event_id unique, received_at)` table and skip
  duplicates.
- **V3-3-3** Stripe Checkout for USD: `[HUMAN]` Stripe account + prices.
  Code: My Plan gets a currency toggle (₹ default; "Paying from outside
  India? Pay in USD"), Stripe Checkout session creation, webhook handler for
  `checkout.session.completed`, `invoice.paid`, `invoice.payment_failed`,
  `customer.subscription.deleted` with `stripe.Webhook.construct_event`
  signature verification. Same idempotency table.
- **V3-3-4** Lifecycle: add `users.plan_status` ('active'|'past_due'|
  'paused'|'free') + `plan_grace_until` (via `_COLUMN_MIGRATIONS`).
  payment failed → past_due with `plan_grace_until = now+7d` and a yellow
  banner on every page (add once in `app.py` after login, not per-page);
  grace expiry (check lazily at login/page load, no cron needed) → plan
  'free', keep `plan` history in Subscription. Over-cap data on downgrade is
  retained and readable but the create paths from V3-2-3 block additions.
  **Pause**: button on My Plan → cancels gateway sub at period end, sets
  'paused' (read-only: reuse the V3-2 gates by treating paused as 'free'
  for limits but keep a "Resume" banner). Resume → new checkout.
- **V3-3-5** Receipts: rely on gateway-generated email receipts for V3
  (enable in both dashboards — `[HUMAN]`). Park GST as a Part 3 note.
- **V3-3-6** Tests: webhook handlers are pure functions over a parsed
  event dict + Session — test activation, duplicate event id (no double
  apply), halted→past_due→free flow with a frozen clock, and signature
  rejection. No live API calls in tests; fixture JSON payloads checked into
  `tests/fixtures/`.

### Sprint V3-4 — Deployment, domain & RedPrana branding — ✅ DONE 2026-07-12

**Implementation notes for V3-5+ sessions:** all code-side tasks are
complete and verified beyond unit tests — `docker build .` succeeds,
both container commands (`streamlit run app.py` and `python
webhook_server.py`) were run live and each served HTTP 200, `docker
compose config` validates, and the `Caddyfile` was validated (and
auto-formatted) with the real Caddy binary. `docs/RESTORE_DRILL.md`'s
drill was actually rehearsed against a real snapshot of the production
database (via SQLite's backup API), not just written as a hypothetical.
Branding: `soulmatch/landing.py` and `app.py` now say "SoulMatch by
RedPrana" (hero, footer, login card, `page_title`); the pricing table on
the landing page and My Plan page both read from `billing.PLAN_PRICES_*`
so they can't drift; the privacy promise is above the fold in the hero.
Logo: code checks for `static/redprana-logo.svg` and falls back to a text
wordmark if absent (no broken-image icon either way) — `[HUMAN]` drop the
real file into **both** `assets/` and `static/` (this repo keeps them
manually in sync, see the comment in `landing.py`) when it exists.
`soulmatch/errors.py` wraps optional Sentry init — `sentry-sdk` is
deliberately NOT added to `requirements.txt`; it only activates if both
`SENTRY_DSN` is set and the package happens to be installed.
**`[HUMAN]` steps still required before this is live** (all documented in
`docs/DEPLOY.md`): rent the VPS, add the GoDaddy DNS A record, install
Docker on the server, fill in `.env` (SECRET_KEY above all), run
`docker compose up -d`, then point the Razorpay/Stripe webhook configs at
the real domain (V3-3's own `[HUMAN]` list). Nothing here was stubbed —
every piece of code runs correctly today against `mock`/no gateway
config; it's the external accounts and DNS that don't exist yet.

- **V3-4-1** Production deploy artifacts (all writable locally, no server
  needed to author them): `Dockerfile` (python:3.12-slim, install
  requirements, run streamlit + webhook sidecar via a small supervisor
  script), `docker-compose.yml` (app + `caddy:2` with a `Caddyfile` for
  `soulmatch.redprana.com` auto-HTTPS, reverse_proxy to :8501 and
  `/webhooks/*` to the sidecar port; volumes for `data/`, `uploads/`,
  caddy state), `deploy/backup.sh` (nightly `sqlite3 data/soulmatch.db
  ".backup ..."` + upload — target `[HUMAN]` choice, default rclone remote)
  and `docs/DEPLOY.md` with the exact first-deploy commands.
  `[HUMAN]` rent the VPS (Hetzner CX22-class) and run DEPLOY.md.
  Postgres deliberately deferred until >~1–2k users.
- **V3-4-2** `[HUMAN]` DNS in GoDaddy: `A` record `soulmatch` →
  VPS IP on redprana.com (root site untouched). Caddy issues the cert
  automatically once DNS resolves. Document in DEPLOY.md.
- **V3-4-3** Branding pass (pure code): "SoulMatch **by RedPrana**" in
  `soulmatch/landing.py` hero + footer, `app.py` `page_title`, auth card;
  logo slot expects `assets/redprana-logo.svg` (`[HUMAN]` supplies file,
  code falls back to text lockup if missing). Landing page adds the pricing
  table (₹/$ toggle, amounts from billing.PRICE_CATALOG so it can't drift)
  and the above-the-fold privacy promise: "Your data is yours. Private by
  default. No public profiles, ever."
- **V3-4-4** Ops hygiene (code + doc): startup warning already exists for
  ephemeral SECRET_KEY — make DEPLOY.md's checklist include setting it;
  add optional Sentry via `SENTRY_DSN` env (init only if set, guarded
  import); `docs/RESTORE_DRILL.md` with the restore-from-backup steps,
  actually rehearsed once against a scratch dir as the verification for
  this task. `[HUMAN]` uptime ping (e.g. UptimeRobot) on /.

### Sprint V3-5 — Trust, legal & data rights  *(cheap now, existential later)*

- **V3-5-1** Privacy Policy + Terms: static markdown rendered on two new
  unauthenticated pages (add to `app.py` nav for logged-out state or render
  as landing-page anchors — pick whichever Streamlit allows cleanly; a
  `st.dialog` from the signup form is an acceptable fallback). Content
  drafted DPDP-aware (what's stored, third-party biodata stays private to
  the workspace, retention, deletion rights, contact email
  support@redprana.com) with a visible "draft — not yet reviewed by
  counsel" note; `[HUMAN]` legal review before public launch. Signup form
  gains a required "I agree to the Terms & Privacy Policy" checkbox.
- **V3-5-2** Data rights, both on My Plan:
  - "Export my data": build in-memory ZIP — one JSON per table (all rows
    where `owner_user_id == owner`, dates ISO-stringified) + the files under
    `uploads/` referenced by the member's Documents — served via
    `st.download_button`. Stream from a temp file if >200MB (unlikely).
  - "Delete my account": type-DELETE-to-confirm dialog → hard-delete all
    tenant rows (reuse `delete_profile` per profile for file cleanup, then
    remaining RawMessages/AiUsage/Subscription rows, then the User) →
    clear session + token. Anonymized platform counters may remain.
    Must refuse for the last remaining Admin account.
- **V3-5-3** Hardening: login rate-limit (track failures per username in a
  small `login_attempts` table or in-process dict; lock 15 min after 8
  failures — remember Streamlit restarts reset in-process state, table
  preferred); raise `MIN_PASSWORD_LENGTH` use everywhere (app.py change-
  password form still allows 6 — fix to use the constant); server-side
  upload limits already constrained by type list — add a size check
  (`st.file_uploader` result `.size`, reject >10MB with a message) in
  Ingest and Documents; set `server.maxUploadSize` in
  `.streamlit/config.toml`. Verify: tests for lockout timing and export
  ZIP completeness (every owned row present, zero foreign rows — this is
  also a tenancy test).

### Sprint V3-6 — NRI polish, "my children", & beta launch

- **V3-6-1** The "children" concept (deferred from V3-2-3): lightweight —
  add `profiles.is_own_child Boolean default False` (+ migration). The
  member marks which profile(s) are their own son/daughter (toggle on the
  profile header card); everything else is a candidate. Pro's 3-children /
  Free-Plus 1-child limit enforces on setting the flag, via PLAN_LIMITS.
  Matching's "Find Matches for Someone" defaults its anchor to the child
  profile. Do NOT build a separate Child entity/table.
- **V3-6-2** NRI ergonomics: `users.timezone` (IANA string, default
  "Asia/Kolkata", picker on My Plan); all datetime *displays* convert
  UTC→user tz via `zoneinfo` (storage stays UTC — audit `strftime` call
  sites); phone fields get a placeholder/help accepting `+<code>` numbers
  (no strict validation — data arrives messy from chats); pricing shows USD
  when the Stripe toggle from V3-3-3 is chosen.
- **V3-6-3** Onboarding: replace the Dashboard "Getting started" checklist
  (it references LLM config — operator framing) with a member-framed
  3-step path to the wow moment: ① mark/add your child's profile →
  ② import a WhatsApp chat or paste a biodata → ③ run your first koota
  match. Each step deep-links (`st.switch_page`) and checks off from real
  data. Empty states on Profiles/Matching/Tasks point at the next step.
- **V3-6-4** `[HUMAN]` Private beta: 10–20 real families (own network +
  2–3 NRI), Free/Plus comped via the Customers plan override, weekly
  feedback loop. Exit criteria to open signup: isolation tests green in
  prod, one full billing cycle processed on both gateways, ≥5 beta users
  active in week 4.

---

## Part 3 — Business track (owner's checklist, not code)

1. **Accounts/legal:** Razorpay + Stripe accounts under RedPrana; PAN/bank;
   decide sole-prop vs. LLP/Pvt Ltd before revenue is material (Stripe India
   onboarding is easier with a registered entity). GST when threshold nears.
2. **NRI GTM (they pay 5–6× more for the same COGS — best margin segment):**
   USA/Singapore/Gulf Telugu & Tamil association WhatsApp groups, temple
   newsletters, one founding-family testimonial per geography. Message:
   "Manage your child's search across time zones — without spreadsheets."
3. **Positioning line for all marketing:** *"The private CRM for your
   child's marriage search — not another matrimony site."*
4. **Support:** a support@redprana.com alias + a WhatsApp Business number
   (this audience will not file tickets); 24h response promise during beta.
5. **Metrics to watch weekly:** signups, activation (first koota score
   within 48h), week-4 retention, AI actions/user, API cost vs. revenue
   (Admin tile from V3-2-4), Free→Plus conversion.

## Part 4 — Explicitly out of scope for V3

Communities/sharing between tenants, invitation links, mobile apps,
public profiles (never), marriage-bureau white-label (V4 candidate once
tenancy is proven), referral rewards, in-app video calls.
