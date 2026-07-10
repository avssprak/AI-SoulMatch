# AI-SoulMatch — UX Improvement Sprint Plan

Created 2026-07-10 from a PM/UX review of the working MVP. This is the
**execution backlog for UI/UX improvements**; strategic/infra items live in
`ROADMAP.md`. Work the sprints in order — each sprint is a coherent,
shippable slice, sized for one focused session. Task IDs (S1-1, S2-3 …) are
stable; check items off as they land.

---

## How to work on any task in this file (read first)

**Conventions of this codebase:**
- Streamlit multipage app: entry `app.py`, pages in `pages_/`, business logic
  in `soulmatch/`. Pages must call `auth.require_login()` at the top and gate
  writes behind `auth.can_edit(current_user["role"])`.
- DB: SQLAlchemy + SQLite, models in `soulmatch/models.py`, sessions via
  `get_session()` from `soulmatch/db.py`. Keep the schema portable — no
  Postgres-only column types.
- Config comes from `.env` via `soulmatch/config.py`, loaded once at process
  start. **After editing app code, the running server must be restarted**
  (kill `streamlit.exe`, restart via the command in `run_local.ps1`).

**Verification (mandatory for every task):**
1. Run the unit tests: `.venv/Scripts/python.exe -m pytest -q` — all must pass.
2. Exercise the changed page headlessly with a real temp DB using
   `streamlit.testing.v1.AppTest` (there is no browser tool on this machine;
   `curl` only fetches the JS shell and proves nothing). Pattern:

   ```python
   import sys, io, tempfile, os
   sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")  # Windows cp1252 vs emoji
   sys.path.insert(0, r"d:\RedPrana\AI-SoulMatch")
   os.environ["DATABASE_URL"] = "sqlite:///" + tempfile.mktemp(suffix=".db").replace("\\", "/")
   from soulmatch.db import init_db, get_session
   init_db()
   # ...seed rows...
   from streamlit.testing.v1 import AppTest
   at = AppTest.from_file(r"d:\RedPrana\AI-SoulMatch\pages_\X.py")
   at.session_state["user"] = {"id": 1, "username": "admin", "role": "Administrator"}
   at.run()
   assert not at.exception
   # find widgets via at.button / at.selectbox / at.dataframe, click, re-assert, then check the DB
   ```
3. Verify the *data* changed in the DB, not just that no exception was raised.

**Known pitfalls:** LLM extraction returns must be native Python types
(`date`, not ISO strings) before hitting the ORM; widget defaults must be
clamped into `number_input` min/max ranges (extracted data can be
out-of-range); give profile-dependent widgets keys that include the selected
id so switching selection refreshes their values.

**Pitfalls found in Sprints 2-4 — read before touching a selectable
dataframe or a button-gated results block:**
- **A button-click block that isn't the true source of truth will vanish on
  its own child's rerun.** If you compute results only inside
  `if st.button("X"):` and then add a *nested* button inside that block whose
  own click triggers `st.rerun()`, the outer button's truthiness resets on
  that rerun and the whole block — nested button included — disappears. Hit
  this twice (Search results in S2-2, Astrology's "Save to profile" in S3-3).
  Fix: persist the computed results in `st.session_state` and render from
  there unconditionally, the same pattern `match_eval`/`seeking_results`
  already used before Sprint 2.
- **A selectable dataframe's own selection state goes stale after a delete
  that shrinks the table**, causing `rows[i]` to raise `IndexError` on the
  next render (found in S3-5, but it also affects S2-1's original single-row
  selection — anything that deletes/merges profiles while `profiles_table`'s
  selection is set). Any handler that removes rows from a table with
  `on_select`/`key` must reset that key's selection before rerunning.
- **You cannot reassign `st.session_state[key]` for a widget that has already
  been instantiated earlier in the *same* run** — Streamlit raises
  `StreamlitAPIException`. A delete/merge handler runs *after* the table
  widget renders, so it can't clear the table's selection directly. Pattern:
  set a plain flag (e.g. `st.session_state["_clear_profiles_selection"] =
  True`), call `st.rerun()`, and consume the flag at the very top of the
  script — before the widget is instantiated for the new run — to actually
  reset it. See `pages_/3_Profiles.py` for the reference implementation.
- **`AppTest` does not carry a manually-injected dataframe selection across
  separate `.click()`/`.run()` cycles the way a real browser's on-screen
  selection persists.** `at.session_state[table_key] = {"selection": {"rows":
  [...]}}` only takes effect for the very next `.run()` — set it again before
  every subsequent interaction you want it to still apply to, or the
  selection silently reads back as empty (not an exception — the test will
  just show the "nothing selected" branch, which can look like a false pass
  if you don't assert on the *positive* branch's content).

---

## Sprint 1 — Trust & feedback (the "did that work?" sprint) — ✅ DONE 2026-07-10

Everything here fixes moments where the app does the right thing but the
user can't tell.

### S1-1 · Flash messages that survive `st.rerun()`
- [x] **Problem:** Nearly every action does `st.success(...)` then immediately
      `st.rerun()`, which erases the message before the user sees it. Affects
      all pages.
- [x] **Build:** Added `soulmatch/ui.py` with `flash()`/`show_flash()` exactly
      as specified. Wired `show_flash()` into `pages_/2_Ingest.py`,
      `3_Profiles.py`, `7_Users.py` (the pages with success-then-rerun pairs).
      Converted every such pair to `flash(...)`. `4_Matching.py`, `5_Astrology.py`,
      `6_Tasks.py`, `1_Dashboard.py`, `8_Search.py` had no success-then-rerun
      pairs to fix, so they were left untouched (no `show_flash()` needed —
      add it if a future task introduces one there).
- [x] **Where:** `pages_/2_Ingest.py`, `3_Profiles.py`, `7_Users.py`.
- [x] **Accept:** verified — message shows on the run right after the action,
      gone on the run after that.
- [x] **Verify:** AppTest on Ingest bulk-autoprocess and Users create/deactivate
      — flash appears once, cleared on the following run. All 68 pytest tests
      still pass.

### S1-2 · Import dedupe at the source (root cause of duplicate messages)
- [x] **Problem:** Re-uploading the same WhatsApp export re-imports every
      message; the uploader stays primed so a double-click double-imports.
      This is where the duplicate mess actually comes from.
- [x] **Build:** Import button now builds an `(sender, content)` set from
      existing `RawMessage` rows via one query, skips anything already present
      (and updates the set as it inserts, so within-batch dupes in the same
      export are also caught), reports via flash: "Imported N. Skipped M
      already in database."
- [x] **Also:** same guard applied to "Add as raw message" manual form.
- [x] **Accept:** verified — re-adding identical content is a no-op with a
      warning instead of a duplicate row.
- [x] **Verify:** AppTest — duplicate manual-entry attempt confirmed row count
      unchanged + warning shown.

### S1-3 · Unprocessed-count caption matches the visible list
- [x] **Problem:** Caption says "4 unprocessed message(s)" while the
      likely-profile filter hides some — numbers don't match what's shown.
- [x] **Build:** Top caption now says "{total} unprocessed message(s) total.";
      a second caption appears only when the shown count differs, e.g.
      "Showing 3 of 4 — profile-like filter on."
- [x] **Accept:** verified via AppTest — caption count matches DB count.

### S1-4 · Loud warning when provider is `mock`
- [x] **Problem:** `Provider: mock` is a muted caption; users don't realize
      extraction will be near-empty (this exact confusion happened).
- [x] **Build:** Added to both `pages_/2_Ingest.py` and `pages_/8_Search.py`.
      Search's wording was adjusted from the plan's draft text since the mock
      search parser is a real (if simpler) keyword matcher, not a near-empty
      fallback like Ingest's mock extractor — says "understands fewer
      phrasings" rather than implying it's broken.
- [x] **Accept:** verified — warning present with `LLM_PROVIDER=mock`.
- [x] **Verify:** AppTest confirmed warning text present on both pages under
      mock provider.

### S1-5 · Progress feedback during bulk auto-process
- [x] **Problem:** "⚡ Auto-process all N" makes N sequential LLM calls with no
      feedback — looks frozen.
- [x] **Build:** Used `st.progress(i/len(shown), text=f"Processing {i} of {N}
      — extracting…")` updated per message, cleared via `.empty()` after the
      loop. Summary counts moved to `flash()`.
- [x] **Accept:** verified.
- [x] **Verify:** AppTest with seeded messages on mock provider — no exception,
      correct profile counts created.

### S1-6 · Koota "None" explained in ranked match results
- [x] **Problem:** "Find Matches For One Profile" shows `Koota Score: None`
      with no reason; users don't know what data to fix.
- [x] **Build:** `Koota Score` column now sorts on the real numeric/NaN value
      then is formatted to `"—"` for display after sorting; a new `Koota Note`
      column names exactly which side is missing which of dob/time/place
      (e.g. "bride missing dob/time/place; groom missing dob/time/place"), or
      shows the astrology error message if the chart computation itself failed.
- [x] **Accept:** verified via AppTest — no bare "None" in the rendered table.

---

## Sprint 2 — Navigation (the "tables are doors" sprint)

## Sprint 2 — Navigation (the "tables are doors" sprint) — ✅ DONE 2026-07-10

### S2-1 · Click a table row to open the profile
- [x] **Problem:** All lists are read-only dataframes; acting on row #8 means
      memorizing "8" and re-finding it in a dropdown.
- [x] **Build:** `pages_/3_Profiles.py` profile table now uses
      `st.dataframe(..., on_select="rerun", selection_mode="single-row",
      key="profiles_table")`. The "View / edit a profile" selectbox stays as
      fallback/secondary, keyed on the table's current selection
      (`key=f"profile_select_{row_selected_id}"`) so a table click always
      refreshes it, while a manual dropdown pick still sticks across unrelated
      reruns (e.g. clicking "Save").
- [x] **Accept:** verified.
- [x] **Verify:** `AppTest` can't simulate a real click, but it CAN drive
      programmatic dataframe selection — set
      `at.session_state["profiles_table"] = {"selection": {"rows": [i]}}`
      before `.run()` (this is Streamlit's own documented mechanism for
      programmatic selection, not a workaround) — used this for real
      assertions in S2-1/S2-2/S2-3 instead of only checking no-exception.

### S2-2 · Same row-click pattern on Tasks and Search results
- [x] **Build:** `pages_/6_Tasks.py`: task table is selectable; picking a row
      re-keys the "Mark task complete" selectbox to that task (same pattern as
      S2-1). `pages_/8_Search.py`: search results table is selectable; picking
      a row shows a compact card (name/gender/age/location/stage/religion/
      caste/horoscope) with a hint to open Profiles for editing.
- [x] **Accept:** verified — no workflow requires remembering a numeric ID.
- [x] **Bug caught during verification, fixed:** the Search page originally
      computed results only inside the transient `if st.button("Search"):`
      block, never persisted. Since a row click fires its own
      `on_select="rerun"`, the button's "clicked" truthiness is gone on that
      rerun, the whole `if` block (including the results table) would have
      been skipped, making the table vanish the instant a row was clicked. Now
      results are stored in `st.session_state["search_results"]` (same
      pattern as Matching's `match_eval`/`seeking_results`) and rendered from
      there regardless of the button's transient state. Caught by an `AppTest`
      that ran a genuine second `.run()` after the simulated row click,
      exactly the failure a no-exception-only check would have missed.

### S2-3 · Fix the matching dead-end: act on a ranked result
- [x] **Problem:** The seeking tab ranks candidates then tells the user to go
      manually rebuild the pairing in Single Match.
- [x] **Build:** Extracted the practical + astrology + AI-recommendation +
      save-result block into `render_match_detail(bride_id, groom_id,
      can_write, state_prefix)` in `pages_/4_Matching.py`, called from both
      the Single Match tab and inline under a row click in the seeking-results
      table. `state_prefix` ("single" / "seeking") keeps each caller's
      session_state independent, so evaluating a pairing in one tab can't
      clobber the other's in-progress evaluation or AI recommendation.
- [x] **Accept:** verified — one click from the ranked table reaches full
      detail and "Save this match result" with no re-picking.
- [x] **Verify:** `AppTest` — seeded 1 bride + 2 grooms, ran seeking, simulated
      selecting row 0 via `session_state["seeking_results_table"]`, confirmed
      the "Match detail: Bride #1 × Groom #2" subheader appeared, then
      exercised Evaluate + Save independently in both tabs — two distinct
      `MatchResult` rows were created, confirming no state collision.

### S2-4 · Name search on the Profiles page
- [x] **Build:** Added a "Name contains" filter alongside gender/stage/
      religion/location in `pages_/3_Profiles.py` (client-side substring
      match on `full_name`, same pattern as the existing filters).
- [x] **Accept:** verified via `AppTest` — filtering by "sivaram" narrowed a
      3-profile table to 1.

### S2-5 · Consolidate the two "find matches for one person" features
- [x] **Problem:** Matching → "Find Matches For One Profile" and Search &
      Insights → "Best Match Finder" do the same job with different outputs.
- [x] **Build:** Replaced the Search page's "Best Match Finder" section with a
      pointer to the Matching page. `best_matches_for` is still imported by
      `tests/test_insights.py`, so the helper itself was left in
      `soulmatch/insights.py` per the plan's own caveat — only its now-orphaned
      UI and the then-unused `select`/`Profile` imports on the Search page
      were removed.
- [x] **Accept:** verified — one canonical flow, no duplicated UI.

### S2-6 · Persistent login across browser refresh — DECISION: pivoted from the recommended option
- [x] **Problem:** Auth lives in `st.session_state`, so a refresh logs the
      user out.
- [x] **Decision override, with reason:** the plan's recommended option (b),
      `streamlit-cookies-controller`, turned out to be a single-maintainer
      v0.0.4 package that reads/writes cookies through a JS browser component
      (iframe) — unverifiable on this machine (no browser tool, and `AppTest`
      runs headless with no JS execution). Shipping it would mean handing off
      something never actually confirmed to work. Built **option (a)** instead
      (signed token in `st.query_params`) — fully verifiable headlessly since
      query params are plain Python state, no new dependency, only cost is the
      token sitting in the URL bar (acceptable for a LAN-only tool).
- [x] **Build:** `soulmatch/auth.py` — `mint_session_token`/
      `validate_session_token` (HMAC-SHA256 over `{uid, pw fingerprint, session
      epoch, exp}`, 7-day TTL). `soulmatch/config.py` — `SECRET_KEY` (from
      `.env`, falls back to a process-lifetime random key with a note that
      restarts then log everyone out). `app.py` — restores the session from
      `?token=` before showing the login form; mints a token on login; clears
      the query param on logout; re-mints immediately on password change so
      the *current* session survives its own password change.
- [x] **Extra hardening found during verification, not in the original plan:**
      the first pass only cleared the token from the current browser's URL on
      logout — a stale copy (bookmark, browser history) still restored the
      session until natural expiry, failing the plan's own "logout ...
      invalidate[s] it" acceptance criterion. Added `User.session_epoch`
      (bumped by `auth.logout_everywhere`, embedded in the token, checked on
      validation) — a small migration-safe schema addition
      (`soulmatch/db.py`'s new `_apply_column_migrations`, an `ALTER TABLE ...
      ADD COLUMN` run at `init_db()` for columns added to the model after a
      table already existed in deployed DBs) since existing SQLite databases
      don't get new columns from `create_all()` alone.
- [x] **Accept:** verified — login survives a simulated refresh; logout
      invalidates every outstanding token immediately (including a stale one);
      password change invalidates the old token while keeping the current
      session alive via re-mint.
- [x] **Verify:** 7 new pytest cases in `tests/test_auth.py` (roundtrip,
      tampered signature, malformed token, expiry, password-change
      invalidation, deactivation invalidation, logout-everywhere invalidation)
      plus an end-to-end `AppTest` script driving `app.py` itself through
      login → simulated-refresh-restore → logout → stale-token-rejected →
      password-change-invalidates.

---

## Sprint 3 — Ingest page restructure & extraction polish — ✅ DONE 2026-07-10

### S3-1 · Split Ingest into tabs
- [x] **Problem:** One page stacks manual entry, upload, the review queue,
      dedupe tools, and reprocess history into a single long scroll.
- [x] **Build:** Reorganized `pages_/2_Ingest.py` into exactly
      `st.tabs(["📥 Import", "📋 Review queue", "🗂️ History"])` as specified —
      pure reshuffle, all widget keys stable, no behavior changes.
- [x] **Accept:** verified — all flows work identically inside their tab.
- [x] **Verify:** rebuilt the AppTest coverage (import/dedupe, mock warning,
      relabeled buttons, extract→start-over, archive, bulk auto-process,
      history reload) against a real DB — all pass, no exceptions.

### S3-2 · Clarify the three negative actions on a message
- [x] **Problem:** "Mark as not a profile / skip", "Discard extraction", and
      "🗑️ Delete" blur together.
- [x] **Build:** Renamed exactly as specified — "Not a profile → archive",
      "Start over", "🗑️ Delete permanently" — each with a one-line `help=`
      tooltip stating its consequence. Applied consistently in both the
      Review queue and History tabs.
- [x] **Accept:** verified — each button states its consequence.

### S3-3 · Save computed chart back to the profile (Astrology)
- [x] **Problem:** Computing a chart for a selected profile doesn't persist
      nakshatra/rashi/lagna — fields stay empty, work is repeated.
- [x] **Build:** "Save to profile #N" writes `nakshatra`/`rashi`/`lagna` +
      `horoscope_available=True`, logs `Activity(event="Astrology computed")`.
      Fill-only by default; an "Overwrite existing values" checkbox appears
      only when at least one of the three is already set.
- [x] **Bug caught during verification, fixed:** the original "Compute Chart"
      button computed and rendered results only inside its own transient
      `if st.button(...)` block — same class of bug as S2-2's Search page fix.
      A nested "Save to profile" button would have vanished the instant it was
      clicked, since the outer button's truthiness resets on that rerun.
      Persisted the computed chart in `st.session_state["astro_chart"]`
      (invalidated if dob/time/place are edited afterward) before adding Save.
- [x] **Accept:** verified — Profiles page reflects the saved values; activity
      timeline records it.
- [x] **Verify:** `AppTest` — computed + saved (fields filled, activity
      logged); re-saved unchanged (idempotent, "already up to date"); manually
      corrupted a field and confirmed the no-overwrite default left it alone;
      checked "Overwrite" and confirmed it then corrected.

### S3-4 · Merge-review UX for existing near-duplicate profiles
- [x] **Problem:** Message-level merge exists at extraction time, but sparse
      junk profiles that *already* got saved can only be deleted one-by-one;
      there's no profile-level merge.
- [x] **Build:** New "🔍 Find Duplicate Profiles" tab on `pages_/3_Profiles.py`.
      `soulmatch/duplicates.py` gained `find_all_duplicate_pairs(session)`
      (pairwise scan reusing `find_duplicate_candidates`, dedupes A-B/B-A into
      one reported pair) and `merge_profiles(session, keep, remove)` (fills
      keep's gaps from remove via the now-shared `merge_into_profile` — moved
      here from `pages_/2_Ingest.py`'s local `_merge_into_profile`, which now
      imports it — re-points remove's documents/tasks/activities/match-results
      onto keep, deletes remove, logs a "Profiles Merged" activity). The UI
      lets the reviewer pick either merge direction ("Merge #B into #A (keep
      #A)" / vice versa) rather than assuming one side is canonical.
- [x] **Accept:** verified — two near-duplicate profiles merge from the UI; no
      orphaned child rows.
- [x] **Verify:** 6 new pytest cases in `tests/test_duplicates.py` (pair
      finding + dedup, gap-fill without overwrite, expectations-dict merge,
      full merge_profiles moving every child-row type + deleting the
      duplicate) plus an `AppTest` driving the actual page.

### S3-5 · Bulk select & delete on Profiles
- [x] **Build:** Profiles table selection mode changed to `"multi-row"`
      (single-click still behaves like before for the one-profile detail
      view; ctrl/shift-click extends to several). New `soulmatch/profiles.py`
      holds `delete_profile(session, profile)`, extracted from the per-profile
      delete block so the single-delete and new bulk-delete paths share one
      implementation. Bulk delete only appears once 2+ rows are selected and
      goes through the same confirm-step pattern used elsewhere.
- [x] **Accept:** verified — cleaning up several junk profiles is one
      selection + one confirm.
- [x] **Bug caught during verification, fixed — affects S2-1 too, not just
      this task:** after any delete (single, bulk, or a merge from S3-4) that
      shrinks the profiles table, the dataframe's *own* selection state in
      `session_state["profiles_table"]` still held row indices from before
      the shrink. On the rerun that follows, indexing `rows[i]` for a
      since-deleted index crashed with `IndexError`. Also learned mid-fix:
      you cannot reassign a widget's `session_state[key]` after that widget
      has already been instantiated in the same run — the delete/merge
      handlers run *after* the table renders. Fixed with a deferred-reset
      flag (`_clear_profiles_selection`) consumed at the top of the script,
      before the table widget exists for the next run — applied to all three
      delete/merge paths (single delete, bulk delete, both merge directions),
      since all three shrink the same table.
- [x] **Verify:** 2 new pytest cases in `tests/test_profiles.py` for the
      helper (child-row + on-disk file cleanup asserted, unrelated profile
      left untouched) plus an `AppTest` driving the real crash scenario
      end-to-end (select 2 of 3 profiles, bulk-delete, confirm) — reproduced
      the `IndexError` before the fix, clean after.

---

## Sprint 4 — Dashboard, stages, and daily-driver polish — ✅ DONE 2026-07-10

### S4-1 · Dashboard: fewer, action-oriented KPIs with drill-through
- [x] **Build:** `pages_/1_Dashboard.py` now shows two rows of 4: row 1 is
      Active Cases / Pending Horoscope / Overdue Tasks / Stale Cases (the last
      one newly computed via `soulmatch.insights.stale_cases`, not previously
      shown on this page at all), each with a one-line caption pointing to
      where to act on it; row 2 demotes Total/Brides/Grooms/Marriages.
      Pending Tasks (not one of the 8 slots) kept as a small caption instead
      of dropped entirely.
- [x] **Accept:** verified — 4-per-row fits without overflow; every row-1
      metric has a destination hint.

### S4-2 · Recent Activity links to profiles
- [x] **Build:** Activity lines now join `Activity.profile_id` → `Profile`
      and show "· Name (#id)" between the event and the detail suffix.
- [x] **Accept:** verified — no bare numeric id without a name.

### S4-3 · Quick stage-change without the full edit form
- [x] **Build:** Standalone `st.selectbox` (grouped labels, see S4-4) +
      "Move" button above the edit form in `pages_/3_Profiles.py`, disabled
      when the picked stage matches the current one. Updates only `stage` and
      logs the existing "Stage changed to X" activity — same Activity event
      string the full edit form already used, so the timeline reads
      identically regardless of which control was used.
- [x] **Accept:** verified — 2-click stage change from the top of the detail
      view.
- [x] **Verify:** `AppTest` — Move disabled with no change selected, enabled
      and functional once a different stage is picked; DB `stage` and a new
      Activity row both confirmed.

### S4-4 · Group the 15 pipeline stages visually
- [x] **Build:** `PIPELINE_STAGES` values unchanged (no migration). Added
      `PIPELINE_STAGE_GROUPS` + `stage_group_label()` to `soulmatch/models.py`
      (3 pytest cases), applied via `format_func` everywhere a stage selectbox
      appears — Profiles' stage filter, its edit-form stage picker, and the
      new S4-3 quick-change selectbox all share the one helper. Dashboard's
      stage bar chart now reindexes/orders by `PIPELINE_STAGES` order via
      `fig.update_xaxes(categoryorder="array", categoryarray=PIPELINE_STAGES)`
      instead of by count.
- [x] **Deviation from the plan's exact wording, noted on purpose:** the
      plan's own draft named the middle group "Engagement (Parents
      Contacted…Proposal Sent)" — but stage #12 in `PIPELINE_STAGES` is
      *itself* literally named "Engagement" and belongs to the *third* group
      alongside Marriage/Rejected/Closed. Using "Engagement" as both a group
      label and a stage name inside a different group would have shipped a
      confusing dropdown. Renamed the middle group's label to **"Outreach"**;
      the actual stage membership is exactly what the plan specified.
- [x] **Accept:** verified — grouped label appears in the filter dropdown.

### S4-5 · CSV export of profile list & search results
- [x] **Build:** `st.download_button` added on `pages_/3_Profiles.py`
      (filtered table) and `pages_/8_Search.py` (results), both encoding via
      `.to_csv(index=False).encode("utf-8-sig")` from the same dataframe
      already built for on-screen display. Closes the ROADMAP §2 export item.
- [x] **Accept:** verified — both buttons render; separately confirmed the
      exact CSV construction round-trips through `pandas.read_csv` with
      correct columns and the UTF-8-sig BOM Excel needs (AppTest can't read a
      download button's file payload directly, so this piece was checked at
      the construction level rather than end-to-end through the widget).

---

## Sprint 5 — Language, mobile & strategic — ✅ DONE 2026-07-10 (S5-3 explicitly skipped, user confirmed Telugu UI not needed)

### S5-1 · Plain-language terminology pass
- [x] Renamed nav label in `app.py`: "Ingest WhatsApp" → "Import Messages".
      Replaced every user-facing "Provider" → "AI service", "Pipeline
      Stage"/"Pipeline Stage Distribution" → "Status"/"Case Status
      Distribution", "Ingest"/"ingest" → "Import Messages"/"import" across
      `pages_/1_Dashboard.py`, `2_Ingest.py`, `3_Profiles.py`, `4_Matching.py`,
      `8_Search.py`. Code/module names (`soulmatch.ingest`, `LLM_PROVIDER`,
      `PIPELINE_STAGES`) deliberately left unchanged — UI strings only, exactly
      as scoped. Left the stored `Activity.event` strings like "Stage changed
      to X" alone (data, not a live label — renaming would make old and new
      timeline entries read inconsistently).
- [x] **Accept:** verified — smoke-tested every page loads with no exception
      after the rename; spot-checked no leftover "Provider:"/"Pipeline"/
      "Ingest WhatsApp" strings remained (`grep` came back empty).

### S5-2 · Mobile pass — scoped down from the original wording, see below
- [x] **What shipped:** Streamlit 1.59's own guidance (bundled reference
      docs) recommends `st.container(horizontal=True)` over `st.columns` for
      button-group rows specifically, because it actually wraps on a narrow
      viewport where `st.columns` never does (no media queries either way,
      but this one control is documented as responsive). Converted every
      *genuine button-pair/group* row across `pages_/2_Ingest.py`,
      `3_Profiles.py`, `6_Tasks.py` to it: all delete/merge confirm
      ("Yes, delete permanently" / "Cancel") pairs, Extract/Archive/Delete,
      Save/Start-over, Reload/Delete, bulk-delete confirm, manual-create
      Create/Cancel, both merge-direction buttons, Mark Done/Cancel Task.
- [x] **Deliberately left unconverted, with reason:** rows that mix a text
      label with buttons at a specific width ratio (Documents list: name +
      Download + Delete; per-task row: title + Done + Cancel) — these aren't
      button *groups*, they're label-plus-action rows with intentional
      proportions, outside `st.container(horizontal=True)`'s documented
      button-group use case. Comparison/grid layouts (bride/groom chart
      columns, duplicate-pair side-by-side cards, Dashboard's 4-metric KPI
      rows, the two-chart row) — these are "fixed grids", which Streamlit's
      own guidance says to keep as `st.columns`. Multi-field data-entry rows
      (Profiles edit form's Full Name/Gender/Age etc., the manual-add-profile
      form) — the plan's original wording asked to reduce these from 3 to 1-2
      columns, but I did **not** do this: there's no responsive alternative
      for form-field rows in this Streamlit version (only the button-group
      container is documented as responsive), so "fixing" this would mean
      permanently flattening every form to 1-2 columns, degrading desktop
      layout, on a guess I have no way to confirm helps — no browser tool and
      no phone on this machine. Left as-is rather than changing something I
      can't verify either direction.
- [x] **Accept (for what shipped):** verified via `AppTest` that every
      converted button row still functions identically (same DB effects, same
      flash messages) after the container swap.
- [x] **Bug caught during verification, fixed:** one of the merge-direction
      conversions left `st.rerun()` outdented one level, escaping its `if
      st.button(...)` block — it would have re-triggered on *every* render of
      that expander, not just on click. Caught by asserting a plain rerun (no
      button click) left the DB unchanged, immediately after the edit; not
      caught by pytest (no UI) or a shallow "does it look right" read.
- [ ] **Still needs a human with a phone:** the acceptance criterion "usable
      one-handed on a phone; no horizontal scroll on forms" for the
      multi-field forms above genuinely requires visual verification on an
      actual device over the LAN URL — this was not done and I want that
      explicit, not silently implied by the other checkmarks in this sprint.

### S5-3 · Bilingual (Telugu) UI groundwork — SKIPPED
- User explicitly confirmed Telugu UI is not needed for now. No discovery
  work done; revisit only if asked later.

### S5-4 · Audit trail: record who did it
- [x] Added `created_by_user_id` (nullable FK → `users.id`) to Activity,
      Document, Task, MatchResult in `soulmatch/models.py`; added the 4
      column-migration entries to `soulmatch/db.py`'s existing
      `_COLUMN_MIGRATIONS` list (the pattern this task itself proposed,
      already in place since Sprint 2's `session_epoch`). Threaded
      `current_user["id"]` through every creation site across
      `pages_/2_Ingest.py`, `3_Profiles.py`, `4_Matching.py`, `5_Astrology.py`,
      `6_Tasks.py`, plus `soulmatch/documents.py`'s `save_document()` and
      `soulmatch/duplicates.py`'s `merge_profiles()` (both gained an optional
      `created_by_user_id` parameter). `pages_/5_Astrology.py` previously
      called `auth.require_login()` without capturing the return value —
      needed fixing to get at `current_user["id"]`.
- [x] Activity Timeline on `pages_/3_Profiles.py` now shows "by <name>" —
      resolves `full_name` (falls back to `username`) for every distinct
      actor in the displayed activities via one extra query, not per-row.
- [x] **Accept:** verified — stage change, task add/complete, document
      upload, manual/AI/merge profile creation, and profile-to-profile merge
      all recorded the correct acting user's id; a legacy row with no actor
      (simulating pre-migration data) rendered cleanly with no "by" clause
      and no error.
- [x] **Verify:** `AppTest` driving real flows end-to-end as a specific
      non-admin user (not just the default admin), asserting the DB row's
      `created_by_user_id` and the rendered timeline text.

---

## New feature (added mid-Sprint-5, not in the original plan): Matching candidate preference filters

User asked, while continuing Sprint 5: on the Matching page's "Find Matches
For One Profile" tab, add the preference filters a parent/coordinator would
actually screen candidates by — age range, height range, location, religion,
caste, qualification, occupation, marital status, food preference, horoscope
availability — beyond just picking the anchor profile.

- **Build:** New `soulmatch/preferences.py` — `CandidatePreferences`
  dataclass + `matches_preferences()`/`filter_candidates()`. Policy (stated
  in the module docstring): a filter only *excludes* a candidate when that
  field is present on the profile and fails the check — a blank field is
  never treated as a mismatch, since incomplete profiles are the norm in
  this app, not the exception. Wired into `pages_/4_Matching.py`'s seeking
  tab behind a "🎯 Refine candidate preferences (optional)" expander; the
  candidate count updates live as filters change, and the applied
  preferences are stored alongside `seeking_results` so stale results don't
  linger after the filters change without re-running the search.
- **Verify:** 11 new pytest cases in `tests/test_preferences.py` (each
  filter individually, missing-data non-exclusion for every filter type,
  combined-filter AND logic) plus an `AppTest` seeding 1 bride + 3 grooms of
  varying age/location and confirming an age-range filter correctly narrows
  3 candidates to 1 and the results table reflects only the filtered set.

---

## Suggested order of execution

| Sprint | Theme | Rough size |
|---|---|---|
| 1 | Feedback & trust (flash, import dedupe, mock warning, progress) | 1 session |
| 2 | Navigation (row-click, matching drill-in, name search, sticky login) | 1–2 sessions |
| 3 | Ingest restructure, profile merge, bulk delete, astro save-back | 1–2 sessions |
| 4 | Dashboard, stage UX, CSV export | 1 session |
| 5 | Terminology, mobile, i18n scoping, audit trail | as scheduled |

Within a sprint, tasks are ordered by dependency (S1-1's flash helper is used
by later S1 tasks; S2-1's selectable table is reused by S3-5). Don't start a
task by refactoring beyond its stated scope — several tasks deliberately
extract shared helpers (`render_match_detail`, `delete_profile`,
`_merge_into_profile` → `soulmatch/duplicates.py`) and that is the only
refactoring intended.
