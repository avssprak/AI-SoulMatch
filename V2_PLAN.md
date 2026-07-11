# AI-SoulMatch — V2 Product Review & Execution Plan

Created 2026-07-11 from a Product Owner / UX Strategist review of the app as
shipped after UX Sprints 1–5 (`SPRINT_PLAN.md`). This is the **execution
backlog for the V2 release**. Everything in "How to work on any task"
in `SPRINT_PLAN.md` (conventions, verification via pytest + `AppTest`,
Streamlit pitfalls) applies verbatim to every task here — read that section
first, it is mandatory.

---

## Part 1 — Product Owner verdict

The MVP is functionally complete and mechanically solid (Sprints 1–5 fixed
feedback, dedupe, navigation-within-page, audit trail). What it is **not** is
a product someone trusts at first sight or navigates without training. The
gaps are no longer "buttons don't work" — they are:

1. **It looks like a default Streamlit demo.** Default theme, emoji page
   icons, "Executive Dashboard" jargon, raw dataframes everywhere, no photos
   anywhere. A matrimonial tool whose profiles have no faces and no visual
   hierarchy reads as untrustworthy to the exact audience (parents,
   volunteers) it serves.

2. **The profile page is a wall, not a page.** One endless scroll: filter
   row → table → stage mover → 15-field edit form → documents → tasks →
   activity → delete. A volunteer answering a parent's phone call ("tell me
   about profile X") has to scroll past an *edit form* to see documents. The
   most common action (look at a profile) is optimized for the rarest one
   (edit every field).

3. **Pages are dead-ends to each other.** Search says "Open **Profiles**
   and select this ID". Dashboard KPIs say "→ Tasks: Overdue only" as *text*.
   Insights tables show IDs you must memorize. Within-page navigation was
   fixed in Sprint 2; **cross-page** navigation was never built.

4. **Saved match results are write-only.** "Save this match result" stores a
   `MatchResult` + AI recommendation JSON… which no screen ever shows again
   (only a koota histogram and a top-5 insight table). The single most
   valuable artifact the app produces — "we evaluated this pair, here's the
   full reasoning" — cannot be retrieved, reviewed, or shared.

5. **Nothing is parent-facing.** The end deliverable of the whole workflow is
   a conversation with a family. There is no printable/shareable profile
   summary, no side-by-side comparison of shortlisted candidates, no photo
   display. Volunteers will screenshot dataframes.

6. **Data quality is left to luck.** Birth time is a free-text "HH:MM" box
   (the #1 input the astrology engine depends on). Birth place is validated
   only at chart-compute time, pages later. No required-field marking, no
   completeness indicator pushing profiles toward match-readiness.

### Pain-point → recommendation map, prioritized by Impact × Effort

| # | Recommendation | Impact | Effort | Priority |
|---|---|---|---|---|
| R1 | Visual identity: theme, stage badges, de-jargoned labels, consistent page headers | High | Low | **Critical** |
| R2 | Cross-page deep-linking: open any profile from anywhere; Dashboard KPIs become real links | High | Low | **Critical** |
| R3 | Profile detail redesign: header card w/ photo, tabbed sections, read-first edit-second | High | Med | **Critical** |
| R4 | Saved Matches surface: browse/review/delete match results + stored AI recommendation | High | Med | **High** |
| R5 | Data-quality inputs: `st.time_input` for birth time, live birth-place validation, completeness meter | High | Low | **High** |
| R6 | Printable profile summary (parent-facing biodata view) | High | Med | **High** |
| R7 | Candidate compare: 2–3 shortlisted profiles side-by-side | Med | Med | **Medium** |
| R8 | First-run onboarding checklist on Dashboard | Med | Low | **Medium** |
| R9 | Ingest streamlining: one uploader, tab count badges, opt-in auto-process on import | Med | Med | **Medium** |
| R10 | Matching page language & guardrails (tab names, all-combinations cap) | Med | Low | **Medium** |
| R11 | Accessibility pass: no emoji-only signals, required-field marks, empty-state consistency | Med | Low | **Medium** |
| R12 | AI: unified search bar on Profiles page; morning digest panel | Med | Med | **Low (V2.1)** |

Why this order: R1+R2 are cheap and transform first impressions and flow;
R3–R6 fix the core daily journey (look up → judge → share); the rest polish.

---

## Part 2 — Detailed recommendations

### R1 · Visual identity (Critical)
- **Problem:** default Streamlit look; stage shown as raw string in 15
  variants; "Executive Dashboard", "Matching Engine", "Astrology Explorer"
  are system-speak; icons are random emoji.
- **Why it matters:** volunteers judge trustworthiness visually before
  functionally; parents seeing a screen over a shoulder even more so. Also
  the cheapest possible win.
- **Solution:** custom theme via `.streamlit/config.toml`; a shared
  `stage_badge()` helper rendering colored `st.badge`/markdown pills (one
  color per stage *group* from `PIPELINE_STAGE_GROUPS`, not 15 colors);
  rename titles to plain language; consistent `st.header` + one-line caption
  pattern on every page.
- **Value:** perceived quality jump for ~a day of work.

### R2 · Cross-page deep-linking (Critical)
- **Problem:** Search result card says "Open Profiles and select this ID";
  Dashboard KPI captions are instructions ("→ Tasks: Overdue only"); Insights
  tables end at an ID.
- **Why:** every hand-off between pages currently costs the user memory and
  3–5 clicks; this is the single biggest remaining workflow bottleneck.
- **Solution:** a tiny `soulmatch/nav.py`: `open_profile(pid)` sets
  `st.session_state["open_profile_id"]` and `st.switch_page(profiles_page)`;
  Profiles page consumes that key at the top (same deferred-flag pattern as
  `_clear_profiles_selection`). Every list of profiles (Search results,
  Insights tables, Tasks rows, Dashboard recent activity, duplicate pairs)
  gets an "Open profile" button. Dashboard KPI captions become
  `st.page_link`s / buttons that also pre-fill the destination filter
  (e.g. Tasks with `overdue_only` pre-checked via a session key).
- **Value:** the app starts feeling like one product instead of eight scripts.

### R3 · Profile detail redesign (Critical)
- **Problem:** read and edit are the same giant form; documents/tasks/
  timeline stack below it; no photo, no at-a-glance summary.
- **Solution:** detail area becomes: **header card** (photo thumbnail from the
  newest `photo` Document, name, age·gender, stage badge, location, phone,
  completeness meter) → **tabs**: `Overview` (read-only facts + notes +
  ✏️ Edit expander containing the current form) · `Documents` (with image
  thumbnails via `st.image`) · `Tasks` · `Matches` (see R4) · `History`.
- **Value:** the most frequent action (look) becomes instant; editing stays
  one click away; parents can be shown the screen directly.

### R4 · Saved Matches surface (High)
- **Problem:** `MatchResult` rows + stored AI recommendation JSON are
  unviewable after saving.
- **Solution:** (a) Matching page gains a **Saved Matches** tab: table of
  results (bride, groom, practical %, koota, recommendation, date, by whom),
  row-click renders the full stored detail incl. parsed recommendation JSON,
  with delete. (b) Profile detail `Matches` tab lists that person's saved
  matches with the same drill-in.
- **Value:** the app's core output becomes an asset you can retrieve in the
  meeting where it matters, instead of re-running the evaluation.

### R5 · Data-quality inputs (High)
- **Problem:** birth time = free text; birth place typo discovered only at
  chart time; nothing marks a profile match-ready.
- **Solution:** `st.time_input` (stores same "HH:MM" string — no migration);
  on-save birth-place check against `geo_lookup` with inline warning;
  `profile_completeness(profile)` helper → % + missing-field chips on the R3
  header; "Match-ready" (has dob+time+place) shown as a badge and as a new
  Profiles filter.
- **Value:** directly raises the share of pairs that can get a koota score —
  the app's differentiating feature.

### R6 · Printable profile summary (High)
- **Problem:** nothing to hand a family.
- **Solution:** "📄 Print summary" on the profile header → a clean print-CSS
  HTML view (name, photo, key facts, astrology summary if computed — no
  internal fields like stage/notes/IDs) rendered via `st.html` in a dialog,
  plus a "Download as HTML" button. (Full PDF generation deferred; browser
  print-to-PDF covers the need with zero new dependencies.)

### R7 · Candidate compare (Medium)
Side-by-side of 2–3 candidates vs the anchor in the seeking tab (multi-select
rows → compare table: field rows, candidate columns, differences highlighted).

### R8 · Onboarding checklist (Medium)
When `< 3` profiles exist, Dashboard shows a "Getting started" checklist
(add AI key ✓/✗ from config, import messages, extract first profile, compute
first chart, run first match) with page links — replaces charts-of-nothing.

### R9 · Ingest streamlining (Medium)
One uploader accepting `.txt/.zip/.pdf` that routes by parse result (try
WhatsApp export first, fall back to `parse_document`); tab labels show counts
("Review queue (12)"); a "Process new messages now" opt-in checkbox on import
that chains straight into the existing bulk auto-process.

### R10 · Matching language & guardrails (Medium)
Tab renames: "Check a Specific Pair" / "Find Matches for Someone" / "Screen
All Pairs"; the last one warns and requires confirmation above 500
combinations; empty-state text explains what each tab is *for* in parent
terms.

### R11 · Accessibility & consistency pass (Medium)
Every ⚠️/✅/❌-only signal gains a word; required fields marked `*`
consistently (only Full Name + Gender actually required — say so); all
empty-states follow one pattern ("what this is · why it's empty · button to
fix"); check color contrast of the R1 theme in both light/dark.

### R12 · AI additions (V2.1 — after the above ships)
Unified search bar on Profiles (free text → existing `parse_query` → fills
the structured filters, visible + editable); Dashboard "Today" digest panel
(deterministic: overdue tasks, stale cases, new unprocessed messages — reuse
`insights.py`, no LLM cost).

---

## Part 3 — V2 Sprint plan (execution order for Sonnet)

Follow `SPRINT_PLAN.md` → "How to work on any task" for conventions,
pitfalls, and the mandatory pytest + `AppTest` verification pattern. All
schema additions go through `_COLUMN_MIGRATIONS` in `soulmatch/db.py`.
UI-string renames only — never rename code identifiers, stored enum values,
or `Activity.event` strings.

### Sprint V2-1 — Identity & flow (R1 + R2 + R10 + R8) — ✅ DONE 2026-07-11
1. [x] **V2-1a Theme.** `.streamlit/config.toml` with a warm rose primary
   (`#B03A5B`), light background, readable font.
2. [x] **V2-1b Stage badges.** `soulmatch.ui.stage_badge(stage)` — color
   keyed by `stage_group_label()` group (Screening=blue, Outreach=violet,
   Outcome=green/red/gray by specific stage). Used on the Profiles detail
   header.
3. [x] **V2-1c Plain-language titles.** "Executive Dashboard"→"Dashboard",
   "Matching Engine"→"Matchmaking", "Astrology Explorer"→"Horoscope Check",
   "Ingest WhatsApp"/"Import Messages"→"Import Profiles" in both `app.py` nav
   and each page's `st.title`, plus every cross-reference string.
4. [x] **V2-1d Deep links.** New `soulmatch/nav.py`:
   `request_open_profile`/`consume_open_profile_request`/`open_profile_button`
   (button + `st.switch_page`, same deferred-flag pattern as
   `_clear_profiles_selection`). Wired into: Profiles (consumes the queued id
   at top-of-script, before the detail selectbox is instantiated), Search
   result card, all three single-profile Insights lists (pending horoscope /
   incomplete / stale — a compact selectbox+button under each, since these
   are plain dataframes, not selectable ones), Tasks' selected-row detail,
   Dashboard Recent Activity lines.
   **Known AppTest limitation, not a product bug:** `st.switch_page` (and
   `st.page_link`, which was tried first and abandoned for this reason)
   require the multipage-app registry that only exists when Streamlit runs
   through `app.py`'s `st.navigation(...)` call. `AppTest.from_file()` loads
   a page script standalone, so clicking a switch-page button raises
   `StreamlitAPIException` in tests even though it works correctly under
   `streamlit run app.py`. Verified structurally instead: confirmed
   `request_open_profile`'s session-state write happens (and is captured)
   before the `switch_page` call raises, and separately verified
   `consume_open_profile_request` + the Profiles page's handling of a
   pre-seeded key produces the correct detail view. A human should still
   click these buttons once in a real browser to confirm the navigation
   itself (not just the state plumbing either side of it).
5. [x] **V2-1e Dashboard KPI links.** Row-1 metrics gained click-to-navigate
   buttons (`st.switch_page`, not `page_link`, for the same testability
   reason as V2-1d). Overdue Tasks pre-sets
   `st.session_state["tasks_overdue_pref"]`, consumed by Tasks' checkbox
   default via `st.session_state.pop(...)`.
6. [x] **V2-1f Matching guardrails.** Tabs renamed "Check a Specific Pair" /
   "Find Matches for Someone" / "Screen All Pairs"; the last requires an
   explicit "Yes, screen all" confirmation above 500 combinations.
7. [x] **V2-1g Onboarding.** Dashboard: when `total profiles < 3`, the two
   charts are replaced by a Getting Started checklist (AI service connected?
   import→extract→chart→match) with per-item "Go →" buttons; ≥3 profiles
   shows the charts as before.
- [x] **Verify:** full pytest suite (95 passed, 1 pre-existing unrelated
  failure in `test_extractor.py` confirmed via `git stash` to predate this
  sprint). `AppTest` smoke run across Dashboard/Profiles/Search/Tasks/
  Matching — no exceptions, onboarding checklist renders on an empty DB,
  deep-link-into-Profiles renders the correct profile, Matching tabs show
  the new labels.

### Sprint V2-2 — Profile detail redesign (R3 + R5) — ✅ DONE 2026-07-11
1. [x] **V2-2a Completeness helper.** `soulmatch/profiles.py`:
   `profile_completeness(p) -> (percent, missing: list[str])` over 14 core
   fields; `is_match_ready(p)` = dob+birth_time+birth_place. 4 new pytest
   cases in `tests/test_profiles.py`.
2. [x] **V2-2b Header card.** Bordered container: photo (newest Document
   `kind=="photo"` via `read_document`→`st.image`, placeholder caption if
   none), name/gender/age/location/phone, stage badge, completeness progress
   bar (`st.progress` with a "X% complete — missing a, b, c" text), a
   "✅ Match-ready" / "⚠️ Not match-ready" caption, and the quick stage mover
   (relocated, unchanged behavior) below it for editors.
3. [x] **V2-2c Detail tabs.** `st.tabs(["Overview", "Documents", "Tasks",
   "Matches", "History"])`. Overview = the read-only fact grid (now shown to
   *everyone*, not just Viewers) + Notes + an "✏️ Edit profile" expander
   (editors only) containing the original edit form, now with the V2-2d
   birth-time/place changes and a "* required" caption. Documents tab shows a
   60px thumbnail for `.jpg/.jpeg/.png` filenames ahead of the existing
   name/download/delete row. Matches tab is a stub pointing at Matchmaking
   until V2-3b lands. Activity Timeline + its log-activity form + the delete
   confirmation flow moved into History, unchanged otherwise. All original
   widget keys kept stable.
4. [x] **V2-2d Birth time & place inputs.** Edit form's birth-time text box
   replaced with `st.time_input(step=300)`, via a new
   `_parse_birth_time("HH:MM") -> time | None` helper and
   `.strftime("%H:%M")` on save (round-trip verified, e.g. "07:05"). On save,
   if `birth_place` is set and `geo_lookup(birth_place)` returns `None`, the
   profile still saves but a second flash warning names the field and
   explains why ("astrology charts need an exact/nearby city name").
   (Astrology page and manual-add form left as free text — out of this
   sprint's scope; both are lower-traffic entry points than the main edit
   form.)
5. [x] **V2-2e Match-ready filter.** Profiles filter row gained a "Birth
   details: All / Match-ready / Missing" radio, using `is_match_ready()`.
- [x] **Verify:** full pytest suite (99 passed, same 1 pre-existing unrelated
  failure). `AppTest` — detail tabs render with correct labels; completeness/
  match-ready captions present; Edit-profile expander present for
  Administrator, absent for Viewer; time-input round-trips to "07:05" in the
  DB; photo thumbnail renders in both the header and Documents tab (2 images
  found for one uploaded photo doc); bogus birth-place still saves but shows
  the named warning.

### Sprint V2-3 — Matches as an asset (R4 + R6 + R7) — ✅ DONE 2026-07-11
0. [x] **Pre-work.** New `soulmatch/matchview.py` — `render_recommendation
   (rec)` (extracted verbatim from `render_match_detail`'s inline block,
   which now just calls it) and `render_saved_match_result(mr, bride, groom)`
   (renders a persisted `MatchResult`'s practical/koota/dosha/recommendation
   from stored data only, no re-evaluation or LLM call). Both pages below
   import from here — the only way to share UI-rendering logic between two
   independent Streamlit page scripts in this app.
1. [x] **V2-3a Saved Matches tab** on Matching (now 4 tabs, "Saved Matches"
   last): `MatchResult` newest-first with Bride/Groom/Practical %/Koota/
   Recommendation/Saved-date/By columns (resolves profile + actor names in
   two batched queries, not per-row), single-row-selectable, row-click
   renders full stored detail via `render_saved_match_result`, then a
   write-gated delete with the standard confirm/cancel pattern.
2. [x] **V2-3b Profile Matches tab** (fills the V2-2c stub): matches where
   the open profile is bride or groom, a selectbox (not a second dataframe —
   fewer rows per profile, reads better) labelled with the other side's name
   and score, drill-in via the same shared renderer.
3. [x] **V2-3c Print summary.** `soulmatch/summary.py`:
   `profile_summary_html(profile, photo_bytes, chart) -> str` — self-
   contained HTML, inline CSS, print-friendly (`@media print`), embeds photo
   as base64 data URI if present, pulls chart from the profile's own
   `nakshatra`/`rashi`/`lagna` columns if set; excludes stage/notes/phone/
   internal IDs entirely (verified by `tests/test_summary.py`, 4 cases).
   Header card's "📄 Print / download summary" button opens an `st.dialog`
   with `st.html(...)` + a `st.download_button` (`{name}_summary.html`).
4. [x] **V2-3d Compare candidates.** Seeking-results table is now
   `selection_mode="multi-row"`: 1 row = the existing drill-in (unchanged),
   2–3 rows = a comparison table (age/height/location/religion/caste/
   qualification/occupation/food + practical & koota score, one column per
   candidate), >3 = an info message asking to narrow the selection.
   **Bug caught during verification, fixed:** the first pass built compare
   cells as `getattr(...) or "—"` (mixed int/str in the same column) and
   `st.dataframe` crashed with `pyarrow.lib.ArrowInvalid` trying to convert
   the column to Arrow — pyarrow requires a uniform column type. Every cell
   is now coerced to `str(...)` (or `"—"` for missing) before building the
   `DataFrame`.
- [x] **Verify:** full pytest suite (103 passed, same 1 pre-existing
  unrelated failure). `AppTest` — saved a `MatchResult` directly, opened it
  from both Matching's Saved Matches tab and the owning profile's Matches
  tab (both rendered Practical/Astrology/AI Recommendation sections
  correctly); delete flow confirmed removed row from the DB; print-summary
  dialog button clicks with no exception; 2-row seeking selection renders
  the "Compare candidates" table with both candidate names as columns.
  **Known AppTest limitation, not a product bug (same class as V2-1's
  `switch_page` note):** programmatic dataframe-selection state
  (`session_state["...table"]`) does not persist across separate
  `.click()/.run()` cycles in `AppTest` — confirmed exactly the pitfall
  `SPRINT_PLAN.md` already documented from Sprint 3; the saved-match delete
  flow only verified cleanly once the test re-seeded the table selection
  before each subsequent `.run()`, which a real browser's on-screen
  selection does not require.

### Sprint V2-4 — Ingest & polish (R9 + R11) — ✅ DONE 2026-07-11
1. [x] **V2-4a One uploader.** Single `st.file_uploader(type=["txt","zip",
   "pdf"])` replaces the two separate uploaders. Non-`.pdf` files try
   `parse_export` first (the primary use case); if that finds zero messages,
   `.txt` (not `.zip` — `parse_document` can't read zip binary, so a bogus
   zip correctly errors instead of silently garbling through the fallback)
   falls back to `parse_document`; `.pdf` always goes straight to
   `parse_document`. A "Parsed as a WhatsApp export" / "Parsed as a
   document" success message states which path was used. Manual-paste
   expander unchanged.
2. [x] **V2-4b Tab badges.** Ingest: "📋 Review queue (N)" / "🗂️ History (N)"
   with live unprocessed/processed counts. Matching: "Saved Matches (N)".
3. [x] **V2-4c Auto-process on import.** A "Extract profiles immediately
   after import" checkbox (default off) appears once a file is parsed;
   when checked, the import button inserts the raw messages, then runs the
   *same* extraction loop Review queue's manual "Auto-process" button uses —
   both now call one shared `_auto_process_raw_messages(message_ids,
   current_user)` in `pages_/2_Ingest.py` instead of two copies of the loop
   (the duplication this task would otherwise have doubled).
4. [x] **V2-4d Accessibility pass.** Audited for bare emoji-only signals —
   none found (earlier sprints already paired every ⚠️/✅/❌ with words). Added
   the "* required — everything else can be filled in later" caption to the
   manual-add-profile form (the edit-profile form already had it from
   V2-2c). Empty-states across the app were already following a consistent
   what/why/next-action pattern from Sprints 1–4; no further changes needed.
- [x] **Verify:** full pytest suite (103 passed, same 1 pre-existing
  unrelated failure). `AppTest` — uploaded a real WhatsApp-export `.txt`
  through the merged uploader (parsed correctly, tab badges showed live
  counts), checked "auto-process" and confirmed 2 profiles were created in
  one import; uploaded a plain non-export `.txt` and confirmed it fell
  through to the document-block path; uploaded a bogus `.zip` and confirmed
  it surfaced a parse error instead of silently mangling through
  `parse_document`.

### Sprint V2-5 (V2.1, AI convenience, R12) — ✅ DONE 2026-07-11
1. [x] **Unified NL search on Profiles.** A "🔎 Search in plain English
   (optional)" expander above the structured filter row on `pages_/
   3_Profiles.py`. Calls the existing `soulmatch.search.parse_query` (same
   LLM-or-mock parser the Search & Insights page already used) and prefills
   the structured widgets — gender/religion/location/stage now have stable
   keys (`pf_gender`, `pf_religion`, `pf_location`, `pf_stage`) so a deferred-
   flag prefill (`_nl_prefill`, consumed at the very top of `tab_search`,
   same pattern as the profile deep-link and selection-clear flags
   elsewhere on this page) can set them before the widgets are instantiated.
   Fields with no dedicated widget on this page (age range, caste,
   qualification/occupation substrings, food preference, marital status,
   horoscope availability) are applied directly to the result list and
   surfaced via a "Also applied directly: ..." caption with a Clear button —
   visible, not silent, even without a matching UI control.
   **Bug caught during verification, fixed:** the first pass didn't map
   `caste` anywhere (no Profiles filter widget for it, and it was left out
   of the "extra filters" list too) — a query like "Brahmin brides" silently
   dropped the caste term entirely. Added `caste` to the extra-filters list
   and its direct-apply branch; verified narrowing 2 profiles (different
   castes, same city) to 1.
2. [x] **Dashboard "Today" digest.** A deterministic (no LLM call) panel
   under the title, above the KPI rows: overdue tasks, unprocessed imported
   messages, pending horoscopes, and stale cases — each only shown if
   nonzero, each with a "Go →" button that navigates to where it's actioned
   (Overdue Tasks pre-sets the same `TASKS_OVERDUE_PREF_KEY` the KPI row
   button already used). "Nothing urgent today — all caught up." when the
   list is empty. Reuses `soulmatch.insights.stale_cases` plus counts
   already computed for the KPI row; only new query is an unprocessed-
   `RawMessage` count.
- [x] **Verify:** full pytest suite (103 passed, same 1 pre-existing
  unrelated failure). `AppTest` — Today panel renders with correct items for
  seeded overdue task + unprocessed message; NL search box present, applying
  a query prefilled `pf_gender`/`pf_location` correctly and narrowed results
  to the matching profile; caste-specific query (after the fix) correctly
  narrowed 2 candidates to 1 with the extra-filter caption shown.

This closes out the full V2 plan (V2-1 through V2-5) — all sprints shipped,
verified, and checked off.

### Dependencies & sequence summary
- V2-1 has no dependencies; do first (all quick wins).
- V2-2c must precede V2-3b (tab exists); V2-3a's `render_recommendation`
  extraction must precede V2-3b.
- V2-2b photo lookup is reused by V2-3c (base64 embed).
- No new Python dependencies anywhere in V2-1…4. No destructive migrations;
  only additive helpers — **no schema changes at all** in this plan.
- Each sprint is one focused session, shippable independently.
