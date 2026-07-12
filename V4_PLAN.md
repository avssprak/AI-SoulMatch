# AI-SoulMatch — V4 Plan: The Parent Journey (guided, stepwise UX)

Created 2026-07-12. This is the **execution backlog for the V4 release** — a
UX restructure that turns the flat, tool-shaped side menu into a **guided,
stepwise journey for a parent**, based on the "Parent Personal CRM — Process
Flow" concept document (docs/, 5 stages: Prime Profile Setup → Candidate
Ingestion → Horoscope & Scoring → Review & Selection → Enrichment &
Follow-Up).

Everything in "How to work on any task" in `SPRINT_PLAN.md` (conventions,
verification via pytest + `AppTest`, Streamlit pitfalls) and **all tenancy
rules in V3_PLAN.md Part 1.5** (owned()/get_owned()/owner_id_of(), column
migrations via `_COLUMN_MIGRATIONS`) apply verbatim to every task here.
Tests in `tests/test_tenancy.py` must stay green in every task.

---

## Part 0 — Decisions locked in (do not re-litigate in tasks)

| Decision | Value |
|---|---|
| Mental model | The app is organized around **one journey**: *set up my child → add candidates → score them → shortlist → follow up*. Navigation, page names, and empty states all speak this model. |
| Language | **Parent language, not operator language.** "Ingest" → "Add Candidates". "Profiles" → "Candidates". "Matchmaking" → "Match & Compare". No "LLM", "extraction", "pipeline" in member-visible copy. |
| Prime profile | The member's child is a **first-class anchor** ("My Child"), not a checkbox buried in Profiles. All matching defaults to scoring *candidates against the child*. Existing `Profile.is_own_child` stays the storage; V4 gives it a dedicated surface. |
| Menu size | Max **6 member-visible nav items**, grouped into sections. Horoscope Check stops being a top-level page — it becomes part of Match & Compare and the profile drawer. |
| Composite score | One headline number per candidate: **weighted blend of astro score (koota %) and practical score (preference fit %)**, default 50/50, member-adjustable slider. Stored per member as a preference, not per match. |
| No new backend concepts | V4 is a UX release. Reuse Profile stages, MatchResult, Task, Activity. New columns only where a task explicitly says so. |
| Gender-neutral | The concept doc says "daughter/boys"; the product supports both directions. Copy must say "your child" / "candidates" and derive bride/groom from the child's gender. |

---

## Part 1 — Current state (read before any sprint)

V4-1 shipped on 2026-07-12: grouped `st.navigation` sections in `app.py`
(Home / Step 2 · Candidates / Step 3 · Match / Step 4 · Follow Up / More
/ Admin), page renames (Import Profiles → Add Candidates, Profiles →
Candidates, Matchmaking → Match & Compare, Tasks → Follow-Ups), all page
paths centralized as constants in `soulmatch/nav.py`, and a
`queue_next_step()`/`show_next_step()` helper (same deferred-flag pattern
as `soulmatch.ui.flash`) wired up after auto-process/manual-save on Add
Candidates, manual-add on Candidates, and save-match on Match & Compare.
Horoscope Check (`pages_/5_Astrology.py`) is no longer in the nav but the
page file and its `st.switch_page` targets still work — folding it into
Candidates/Match & Compare was V4-3 (see below; the page is now deleted).

V4-2 shipped on 2026-07-12: new `pages_/0_My_Child.py` — a 3-step wizard
(details → birth details → confirm, session_state-driven like the existing
`pending_manual_profile` pattern in `pages_/3_Profiles.py`) when no
`is_own_child` profile exists, else an anchor card (progress meter,
match-ready flag, inline edit, inline "Compute & save chart" reusing the
`pages_/5_Astrology.py` build_chart/chart_summary logic, and a guarded
"Change child" unmark flow). Wired into `app.py` nav as its own "Step 1 · My
Child" section (`MY_CHILD_PAGE` constant in `soulmatch/nav.py`). New
`theme.journey_stepper(steps)` renders the 4-step progress strip (My Child →
Candidates → Match → Follow Up); it's now **always visible** on the
Dashboard (replaced the old `total < 3`-gated onboarding checklist), with a
single CTA button for whichever step is first-not-done. The Dashboard
header personalizes to the child's name when one is set ("Priya's search at
a glance…"). `pages_/3_Profiles.py`'s own `is_own_child` checkbox toggle is
untouched — both surfaces write the same flag. Verified via `AppTest`:
rendered the wizard's empty state, seeded a child profile directly and
re-rendered both the anchor card and the personalized/ticked-off Dashboard —
no exceptions, stepper HTML confirmed showing "My Child" as done and
"Candidates" as current. (Driving the wizard's multi-step forms via
`AppTest.button[i].click()` hit a harness quirk — duplicate widget keys
across reruns of the `if step == N` branches confuse positional indexing —
worked around by targeting buttons by key substring; not an app bug.)

V4-3 shipped on 2026-07-12: the standalone Horoscope Check page
(`pages_/5_Astrology.py`) is **deleted** — `ASTRO_PAGE` is gone from
`soulmatch/nav.py`, and the compute/save-chart logic that used to live
there is now `soulmatch.horoscope_ui.compute_and_save_chart(session, owner,
current_user, profile, *, key_prefix)`, a shared helper (not copy-pasted —
`pages_/0_My_Child.py`'s V4-2 inline version was refactored to call it too).
It's wired into: `pages_/3_Profiles.py` Overview tab (an expander, shown
whenever `not profile.horoscope_available or not is_match_ready(profile)`)
and `pages_/4_Matching.py`'s "Check a Specific Pair" tab (an expander above
`render_match_detail`, listing whichever of the selected bride/groom still
lack a saved chart). Any new caller that needs this UI should use the
shared helper, not reimplement it. Dashboard's "Compute & save a chart →"
button and its "Today" missing-horoscope item now route to Candidates
(`PROFILES_PAGE`) instead of the deleted page.

- `pages_/1_Dashboard.py`'s onboarding path is now the always-visible
  journey stepper from V4-2, not a `total < 3`-gated checklist.
- `pages_/4_Matching.py` tab "Find Matches for Someone" already anchors to
  the `is_own_child` profile and has practical preference filters — this is
  the seed of the Scoreboard.
- `pages_/3_Profiles.py` profile detail drawer has tabs Overview / Docs /
  Tasks / Matches / History.
- `soulmatch/nav.py` has cross-page helpers (`open_profile_button`,
  page-path constants, `queue_next_step`/`show_next_step`). Extend it;
  don't duplicate.
- `soulmatch/theme.py` owns brand CSS, `page_header`, `section`,
  `empty_state`, `journey_stepper`.
- `soulmatch/horoscope_ui.py` owns the compute/save-chart UI — see V4-3
  note above. Use it for any future "add a horoscope inline" surface.

V4-4 shipped on 2026-07-12: `evaluate_match()`'s `outcome.score` already was
a 0-100 practical fit percentage (no rules.py rework was needed, unlike the
plan's original assumption). Added `soulmatch.matching.rules.composite_score(
practical_score, koota_total, astro_weight)` (falls back to whichever single
score exists; None only if both are missing) and `score_band(score)` (🟢≥70 /
🟡≥40 / 🔴 else) — both unit-tested in `tests/test_matching_rules.py`. New
`User.astro_weight` column (0-100 default 50, `_COLUMN_MIGRATIONS` entry),
synced into `session_state["user"]` in `app.py` alongside plan/timezone.
`pages_/4_Matching.py`'s old "Find Matches for Someone" tab **is** the
Scoreboard now — reused rather than duplicated (it already anchored to the
child and had the ranked/compare/preference-filter machinery the plan
wanted) — renamed to "Scoreboard" and moved first via `st.tabs()` ordering
(tab content position follows `st.tabs()` label order, not where the `with
tab_x:` block sits in the script, so no code needed to physically move).
Added: an `astro_weight` slider that persists to the DB immediately on
change; Composite/Band columns recomputed **from the cached Practical/Koota
scores on every render** (not baked into the "Find best matches" cache), so
dragging the slider re-ranks instantly without re-running the search;
Shortlist (→ stage `"Interested"`) and Reject (→ stage `"Rejected"`) buttons
next to a single selected row, both logging an Activity — no new status
field, per the plan's explicit instruction. Compare view (2-3 selected
rows) gained a Composite row. Verified via `AppTest`: found-best-matches
produced correct composite numbers by hand-check, moving the weight slider
live re-ranked without re-clicking search and persisted to the DB, and
Shortlist/Reject both flipped the candidate's stage correctly. Note for
next session: **dataframe row-selection state injected via
`at.session_state["seeking_results_table"] = {...}` before `.run()` does
not survive a second, unrelated `.run()` call** — it must be re-injected
immediately before every `.run()` that depends on it (confirmed by testing;
not an app bug, a harness quirk with `on_select="rerun"` dataframes).

V4-5 shipped on 2026-07-12: `models.TASK_TEMPLATE_DUE_DAYS` maps each
`STANDARD_TASK_TITLES` entry to a default due-date offset (kept the
existing 5-title vocabulary rather than inventing a second one, since it
was already used in the profile drawer and this just adds one-click
buttons + defaults on top). New `soulmatch/task_ui.py` (`render_task_
quick_add`) is the shared one-click-template + custom-task UI, used on
Follow-Ups (with a profile picker, since that page isn't scoped to one
candidate — it didn't have *any* task-creation UI before this) and in the
Candidates drawer. `pages_/3_Profiles.py`'s profile drawer tabs are now
Overview / Documents / **Follow-up** / Matches (Tasks and History merged
into one tab — open tasks section, quick-add, an inline note box, and a
single timeline interleaving tasks + activities newest-first, sorted by
`completed_at or created_at` for tasks and `created_at` for activities).
"Delete this profile" moved from the old History tab to Overview (a
profile-lifecycle action, not a follow-up one). New
`soulmatch.insights.stale_shortlisted()` (stage `"Interested"`, no pending
Task, no Activity in `days`, default 7) surfaces on the Dashboard "Today"
digest ahead of the general `stale_cases` nudge, since it's narrower and
more actionable. Verified via `AppTest`: clicked a template button on
Follow-Ups and confirmed the Task row + correct due date in the DB;
selected a candidate with that task and confirmed the merged Follow-up tab
showed it under "Open follow-ups" *and* in the Timeline; backdated two
"Interested"-stage profiles and confirmed the Dashboard nudge text and
count appeared correctly. Unit tests added for `stale_shortlisted` in
`tests/test_insights.py`.

---

## Sprint V4-1 — Journey navigation & renames

Goal: the side menu itself teaches the flow.

1. **V4-1-1 Grouped navigation.** In `app.py`, switch `st.navigation(pages)`
   to the dict form with sections, member view:
   - **Home**: Dashboard
   - **Step 1 · My Child**: My Child (new page, stub in this sprint — see
     V4-2; until V4-2 lands it can render the existing child-profile view)
   - **Step 2 · Candidates**: Add Candidates (was Import Profiles),
     Candidates (was Profiles)
   - **Step 3 · Match**: Match & Compare (was Matchmaking)
   - **Step 4 · Follow Up**: Follow-Ups (was Tasks)
   - **More**: Search & Insights, My Plan (+ Customers for Admin under
     **Admin**)
   Remove Horoscope Check from nav (page file stays until V4-3 folds it in;
   keep `pages_/5_Astrology.py` reachable via `st.switch_page` links so
   nothing 404s mid-release).
2. **V4-1-2 Copy sweep.** Rename titles/headers/captions/buttons across
   pages to parent language (grep for "Ingest", "Import Profiles",
   "Matchmaking", "Profiles" in member-visible strings). Update every
   `st.switch_page`/nav constant; centralize page paths in `soulmatch/nav.py`
   so future renames are one-line.
3. **V4-1-3 Cross-page "next step" footers.** After a successful action,
   show one primary next-step button: after import/review on Add Candidates →
   "Review candidates →"; after saving a candidate → "Score against
   <child name> →" (deep-link into Match & Compare with the pair
   preselected via session_state); after saving a match → "Add a follow-up
   task →". Small helper in `nav.py`, reused on all three pages.

Verify: AppTest smoke that all nav pages render for a Member and Admin;
no stale `st.switch_page` targets.

## Sprint V4-2 — "My Child" prime-profile page + journey stepper

1. **V4-2-1 New page `pages_/0_My_Child.py`.** If no `is_own_child` profile:
   a 3-step wizard (details → birth details/horoscope → confirm), creating a
   normal owned Profile with `is_own_child=True`. If one exists: show it as
   the anchor card (photo, key facts, horoscope status, "everything below is
   scored against this profile"), with edit inline and a guarded
   "change child" flow (Pro allows up to 3 children per V3 limits — respect
   `soulmatch/billing.py` plan limits).
2. **V4-2-2 Journey stepper component** in `theme.py`: a horizontal 4-step
   indicator (My Child → Candidates → Match → Follow up), each step derived
   from real data (child exists / candidate_count > 0 / any MatchResult /
   any Task), rendered at the top of the Dashboard **always** (replace the
   `total < 3` checklist gate — completed steps collapse to ticks, the
   current step shows a one-line call-to-action button).
3. **V4-2-3 Dashboard reframe.** Keep the "Today" digest first; then the
   stepper; metrics/charts only after. Anchor copy to the child by name
   ("Priya's search at a glance") when a child exists.

## Sprint V4-3 — Fold Horoscope Check into the journey

1. **V4-3-1** Move the single-chart compute/validate UI from
   `pages_/5_Astrology.py` into (a) the profile drawer in Candidates
   (Overview tab: "Compute horoscope" inline when missing) and (b) an
   expander inside Match & Compare when a selected profile lacks a chart.
2. **V4-3-2** Delete `pages_/5_Astrology.py` and every link to it
   (Dashboard "Today" item routes to Candidates filtered to
   missing-horoscope instead).

## Sprint V4-4 — Scoreboard & shortlist (Review & Selection)

1. **V4-4-1 Composite score.** New member preference `astro_weight`
   (0–100, default 50) — column on `users` via `_COLUMN_MIGRATIONS`.
   Composite = `astro_weight% × koota% + (100−astro_weight)% × practical%`
   where practical% comes from the existing preference-fit rules in
   `soulmatch/matching/rules.py` (extend to return a 0–100 fit score, not
   just include/exclude).
2. **V4-4-2 Scoreboard tab** as the *first/default* tab of Match & Compare:
   anchored to the child, one ranked table of all candidates with Astro /
   Practical / Composite columns, red-amber-green threshold chips, weight
   slider above, and row actions: Open, Save match, Shortlist.
3. **V4-4-3 Shortlist & compare.** "Shortlist" = existing stage transition
   (map to the current pipeline stages; do not invent a parallel status
   field). Side-by-side compare of 2–3 selected candidates (fields +
   scores). Rejected profiles are archived (stage), never deleted.

## Sprint V4-5 — Follow-up hub (Enrichment & Follow-Up)

1. **V4-5-1 Task templates.** On Follow-Ups and in the profile drawer:
   one-click templates "Call family", "Share bio-data", "Schedule meeting",
   each pre-filling title + default due date; keep free-form tasks.
2. **V4-5-2 Per-candidate engagement view.** In the profile drawer, merge
   Tasks + History tabs into one "Follow-up" timeline (tasks, activities,
   stage changes interleaved, newest first) with an inline note box.
3. **V4-5-3 Stage nudges.** Shortlisted candidates with no open task and no
   activity in 7+ days surface in the Dashboard "Today" digest ("3
   shortlisted families waiting on you").

---

Each sprint = one commit, tests green, verified with `AppTest` + a manual
run (`run_local.ps1`). Ship V4-1 and V4-2 first — they deliver most of the
"what do I do next?" fix on their own.
