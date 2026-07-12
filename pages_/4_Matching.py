import json

import pandas as pd
import streamlit as st
from sqlalchemy import select

from soulmatch import auth, billing, config
from soulmatch.astrology.engine import AstrologyError, BirthDetails, build_chart, full_compatibility
from soulmatch.db import get_session
from soulmatch.extraction.llm import LLMError
from soulmatch.horoscope_ui import compute_and_save_chart
from soulmatch.matching.rules import composite_score, evaluate_match, score_band
from soulmatch.matchview import render_recommendation, render_saved_match_result
from soulmatch.models import Activity, MatchResult, Profile, User
from soulmatch.nav import TASKS_PAGE, queue_next_step, show_next_step
from soulmatch.preferences import CandidatePreferences, filter_candidates
from soulmatch.recommendation import generate_recommendation
from soulmatch.tenancy import get_owned, owned, owner_id_of
from soulmatch.timezones import to_local
from soulmatch import theme
from soulmatch.ui import flash, show_flash

def _missing_birth_detail(bride: Profile, groom: Profile) -> str:
    parts = []
    for label, p in (("bride", bride), ("groom", groom)):
        gaps = [name for name, value in (("dob", p.dob), ("time", p.birth_time), ("place", p.birth_place)) if not value]
        if gaps:
            parts.append(f"{label} missing {'/'.join(gaps)}")
    return "; ".join(parts)


def render_match_detail(bride_id: int, groom_id: int, can_write: bool, state_prefix: str) -> None:
    """Practical + astrology + AI recommendation + save-result UI for one bride/groom
    pairing. Shared by the Single Match tab and the seeking-results drill-in so there's
    one place that does this, not two copies drifting apart. state_prefix keeps each
    caller's session_state (in-progress evaluation, AI recommendation) independent —
    evaluating a pairing in one tab doesn't clobber or get clobbered by the other."""
    eval_key = f"{state_prefix}_match_eval"
    rec_key = f"{state_prefix}_match_recommendation"

    if st.button("Evaluate Match", type="primary", key=f"{state_prefix}_evaluate_btn"):
        with get_session() as session:
            bride = get_owned(session, Profile, bride_id, owner)
            groom = get_owned(session, Profile, groom_id, owner)
            outcome = evaluate_match(bride, groom)

            koota_total = None
            astro_result = None
            astro_error = None
            if bride.dob and bride.birth_time and bride.birth_place and \
               groom.dob and groom.birth_time and groom.birth_place:
                try:
                    bride_chart = build_chart(BirthDetails(bride.dob, bride.birth_time, bride.birth_place))
                    groom_chart = build_chart(BirthDetails(groom.dob, groom.birth_time, groom.birth_place))
                    astro_result = full_compatibility(groom_chart, bride_chart)
                    koota_total = astro_result["overall_score"]
                except AstrologyError as e:
                    astro_error = str(e)

        st.session_state[eval_key] = {
            "bride_id": bride_id, "groom_id": groom_id,
            "outcome": outcome, "astro_result": astro_result,
            "koota_total": koota_total, "astro_error": astro_error,
        }
        st.session_state.pop(rec_key, None)
        st.rerun()

    eval_state = st.session_state.get(eval_key)
    if eval_state and eval_state["bride_id"] == bride_id and eval_state["groom_id"] == groom_id:
        outcome = eval_state["outcome"]
        astro_result = eval_state["astro_result"]
        koota_total = eval_state["koota_total"]

        theme.section("Practical Compatibility")
        badge = "✅ Recommended" if outcome.recommended else "❌ Not Recommended"
        st.metric("Practical Score", f"{outcome.score}%", badge)
        if not outcome.mandatory_passed:
            st.error("A mandatory criterion failed — see below.")

        rule_rows = [{"Rule": r.name, "Mandatory": r.mandatory, "Passed": r.passed, "Detail": r.detail}
                     for r in outcome.results]
        st.dataframe(pd.DataFrame(rule_rows), width='stretch', hide_index=True)
        if outcome.missing_fields:
            st.caption(f"Missing data for a full assessment: {', '.join(outcome.missing_fields)}")

        if astro_result:
            theme.section("Vedic Astrology Compatibility")
            with st.expander("Birth chart details (English / Telugu)"):
                bc1, bc2 = st.columns(2)
                for col, label, chart in ((bc1, "Bride", astro_result["bride_chart"]),
                                           (bc2, "Groom", astro_result["groom_chart"])):
                    col.markdown(f"**{label}**")
                    col.markdown(f"Nakshatra: {chart['nakshatra']} ({chart['nakshatra_te']}), pada {chart['pada']}")
                    col.markdown(f"Rashi: {chart['rashi']} ({chart['rashi_te']})")
                    col.markdown(f"Lagna: {chart['lagna']} ({chart['lagna_te']})")
            st.metric("Ashta Koota Score", f"{koota_total:.1f} / 36", astro_result["overall_verdict"])
            koota_rows = [{"Koota": name, "Score": f"{v['score']:.1f} / {v['max']}", "Detail": v["detail"]}
                          for name, v in astro_result["koota"]["kootas"].items()]
            st.dataframe(pd.DataFrame(koota_rows), width='stretch', hide_index=True)

            if astro_result["dosha_flags"]:
                st.warning("Dosha flags: " + "; ".join(astro_result["dosha_flags"]))
            else:
                st.success("No major doshas flagged.")
        elif eval_state.get("astro_error"):
            st.warning(f"Could not compute astrology: {eval_state['astro_error']}")
        else:
            st.info("Add DOB, birth time and birth place for both profiles to see astrology compatibility.")

        theme.section("AI Recommendation")
        if not billing.can_use_ai_explanations(current_user):
            st.info(billing.UPGRADE_TEASE)
        elif st.button("Generate AI Recommendation", key=f"{state_prefix}_generate_rec_btn"):
            with get_session() as session:
                bride = get_owned(session, Profile, bride_id, owner)
                groom = get_owned(session, Profile, groom_id, owner)
                practical = {
                    "score": outcome.score, "recommended": outcome.recommended,
                    "strengths": outcome.strengths(), "weaknesses": outcome.weaknesses(),
                }
                try:
                    if config.LLM_PROVIDER == "mock":
                        rec = generate_recommendation(bride, groom, practical, astro_result)
                    else:
                        billing.require_quota(session, current_user)
                        usage = {"tokens_in": 0, "tokens_out": 0}
                        rec = generate_recommendation(bride, groom, practical, astro_result, usage_out=usage)
                        billing.record_usage(session, owner, "recommend", usage["tokens_in"], usage["tokens_out"])
                        session.commit()
                except billing.QuotaExceeded as e:
                    st.warning(str(e))
                except LLMError as e:
                    st.error(str(e))
                else:
                    st.session_state[rec_key] = rec
            st.rerun()

        recommendation = st.session_state.get(rec_key)
        if recommendation:
            render_recommendation(recommendation)

        if can_write and st.button("Save this match result", type="primary", key=f"{state_prefix}_save_btn"):
            with get_session() as session2:
                mr = MatchResult(
                    owner_user_id=owner,
                    bride_id=bride_id, groom_id=groom_id,
                    practical_score=outcome.score,
                    practical_detail={"strengths": outcome.strengths(), "weaknesses": outcome.weaknesses()},
                    koota_total=koota_total,
                    koota_detail=astro_result["koota"] if astro_result else None,
                    dosha_detail={"flags": astro_result["dosha_flags"]} if astro_result else None,
                    recommendation="Recommended" if outcome.recommended else "Not Recommended",
                    notes=json.dumps(recommendation) if recommendation else None,
                    created_by_user_id=current_user["id"],
                )
                session2.add(mr)
                session2.add(Activity(profile_id=bride_id, owner_user_id=owner, event="Match evaluated",
                                       detail=f"vs groom #{groom_id}", created_by_user_id=current_user["id"]))
                session2.add(Activity(profile_id=groom_id, owner_user_id=owner, event="Match evaluated",
                                       detail=f"vs bride #{bride_id}", created_by_user_id=current_user["id"]))
                session2.commit()
            flash("Match result saved.")
            queue_next_step("Add a follow-up task →", TASKS_PAGE)
            st.rerun()


current_user = auth.require_login()
owner = owner_id_of(current_user)
owner_tz = current_user.get("timezone")
can_write = auth.can_edit(current_user["role"])

theme.page_header("Match & Compare", "Score bride–groom pairs on practical criteria, Vedic compatibility, and AI judgment.")
show_flash()
show_next_step()
if not can_write:
    st.caption("Your account has read-only (Viewer) access — you can evaluate matches but not save results.")

with get_session() as session:
    brides = session.scalars(owned(select(Profile).where(Profile.gender == "Bride"), Profile, owner)).all()
    grooms = session.scalars(owned(select(Profile).where(Profile.gender == "Groom"), Profile, owner)).all()
    _saved_match_count = len(session.scalars(owned(select(MatchResult), MatchResult, owner)).all())

if not brides or not grooms:
    st.info("Need at least one Bride and one Groom profile. Add some via **Add Candidates** or **Candidates**.")
    st.stop()

tab_scoreboard, tab_single, tab_all, tab_saved = st.tabs(
    ["Scoreboard", "Check a Specific Pair", "Screen All Pairs", f"Saved Matches ({_saved_match_count})"]
)

with tab_single:
    col1, col2 = st.columns(2)
    bride_id = col1.selectbox(
        "Bride", [p.id for p in brides],
        format_func=lambda pid: next(f"#{p.id} {p.full_name or 'Unnamed'}" for p in brides if p.id == pid),
    )
    groom_id = col2.selectbox(
        "Groom", [p.id for p in grooms],
        format_func=lambda pid: next(f"#{p.id} {p.full_name or 'Unnamed'}" for p in grooms if p.id == pid),
    )

    # V4-3-1b: horoscope compute/save folded in here instead of a standalone
    # page — a member shouldn't have to leave the match screen to get a chart
    # for either side of the pair.
    with get_session() as chart_session:
        chart_pending = [
            p for p in (get_owned(chart_session, Profile, bride_id, owner), get_owned(chart_session, Profile, groom_id, owner))
            if p and not p.horoscope_available
        ]
        if chart_pending:
            names = ", ".join(p.full_name or f"#{p.id}" for p in chart_pending)
            with st.expander(f"🔯 Compute horoscope — missing for {names}"):
                for p in chart_pending:
                    st.markdown(f"**{p.full_name or f'#{p.id}'}**")
                    compute_and_save_chart(chart_session, owner, current_user, p, key_prefix="matching_single")

    render_match_detail(bride_id, groom_id, can_write, "single")

with tab_scoreboard:
    st.caption(
        "Rank every candidate against one 'main' profile — e.g. your child's horoscope stays "
        "fixed while you browse everyone on the other side, ranked by a blended score."
    )

    # V4-4-1: astro_weight is a per-member preference (stored on User), not a
    # per-match setting — persisted immediately when the slider moves so it's
    # remembered next visit.
    astro_weight = st.slider(
        "Astrology vs practical weight", 0, 100, current_user.get("astro_weight", 50),
        key="scoreboard_astro_weight",
        help="How much the composite score below leans on Vedic compatibility vs practical fit.",
    )
    if astro_weight != current_user.get("astro_weight", 50):
        with get_session() as weight_session:
            weight_user = weight_session.get(User, current_user["id"])
            weight_user.astro_weight = astro_weight
            weight_session.commit()
        current_user["astro_weight"] = astro_weight
        st.session_state["user"]["astro_weight"] = astro_weight

    seeking_gender = st.radio("Seeking matches for a:", ["Bride", "Groom"], horizontal=True, key="seeking_gender")
    anchor_pool = brides if seeking_gender == "Bride" else grooms
    candidate_pool = grooms if seeking_gender == "Bride" else brides
    opposite_label = "Groom" if seeking_gender == "Bride" else "Bride"

    # V3-6-1: default the anchor to the member's own child profile, if
    # they've marked one matching this gender — that's almost always who
    # "the main profile" means here.
    anchor_options = [p.id for p in anchor_pool]
    child_ids = [p.id for p in anchor_pool if getattr(p, "is_own_child", False)]
    default_anchor_index = anchor_options.index(child_ids[0]) if child_ids else 0
    anchor_id = st.selectbox(
        f"Which {seeking_gender.lower()} is the main profile?",
        anchor_options,
        index=default_anchor_index,
        format_func=lambda pid: next(f"#{p.id} {p.full_name or 'Unnamed'}" for p in anchor_pool if p.id == pid),
        key="seeking_anchor_id",
    )

    with st.expander("🎯 Refine candidate preferences (optional)"):
        st.caption(
            "Only excludes a candidate when they have this field filled in and it doesn't match — "
            "an incomplete profile is never hidden just because a field is blank."
        )
        fc1, fc2, fc3 = st.columns(3)
        age_range = fc1.slider(f"{opposite_label}'s age range", 18, 100, (18, 100), key="seeking_age_range")
        height_range = fc2.slider(
            f"{opposite_label}'s height range (cm)", 100.0, 250.0, (100.0, 250.0), step=1.0,
            key="seeking_height_range",
        )
        location_pref = fc3.text_input("Location contains", key="seeking_location_pref")

        fc4, fc5, fc6 = st.columns(3)
        religion_pref = fc4.text_input("Religion contains", key="seeking_religion_pref")
        caste_pref = fc5.text_input("Caste contains", key="seeking_caste_pref")
        qualification_pref = fc6.text_input("Qualification contains", key="seeking_qualification_pref")

        fc7, fc8, fc9 = st.columns(3)
        occupation_pref = fc7.text_input("Occupation contains", key="seeking_occupation_pref")
        marital_status_pref = fc8.selectbox(
            "Marital Status", ["Any", "Never Married", "Divorced", "Widowed"], key="seeking_marital_pref"
        )
        food_pref = fc9.selectbox(
            "Food Preference", ["Any", "Vegetarian", "Non-Vegetarian", "Eggetarian"], key="seeking_food_pref"
        )
        horoscope_pref = st.selectbox("Horoscope", ["Any", "Available", "Pending"], key="seeking_horoscope_pref")

    preferences = CandidatePreferences(
        min_age=age_range[0] if age_range[0] > 18 else None,
        max_age=age_range[1] if age_range[1] < 100 else None,
        min_height_cm=height_range[0] if height_range[0] > 100.0 else None,
        max_height_cm=height_range[1] if height_range[1] < 250.0 else None,
        location_contains=location_pref or None,
        religion_contains=religion_pref or None,
        caste_contains=caste_pref or None,
        qualification_contains=qualification_pref or None,
        occupation_contains=occupation_pref or None,
        marital_status=None if marital_status_pref == "Any" else marital_status_pref,
        food_preference=None if food_pref == "Any" else food_pref,
        horoscope_available={"Any": None, "Available": True, "Pending": False}[horoscope_pref],
    )
    filtered_candidate_pool = filter_candidates(candidate_pool, preferences)

    if not candidate_pool:
        st.info(f"No {opposite_label} profiles to match against yet.")
    else:
        st.caption(f"{len(filtered_candidate_pool)} of {len(candidate_pool)} {opposite_label} profile(s) match your preferences.")

    if candidate_pool and not filtered_candidate_pool:
        st.warning("No candidates match these preferences. Try widening the ranges above.")
    elif filtered_candidate_pool and st.button(f"Find best {opposite_label} matches", type="primary"):
        rows = []
        with get_session() as session:
            anchor = get_owned(session, Profile, anchor_id, owner)
            for candidate in filtered_candidate_pool:
                cand = get_owned(session, Profile, candidate.id, owner)
                bride, groom = (anchor, cand) if seeking_gender == "Bride" else (cand, anchor)
                outcome = evaluate_match(bride, groom)

                koota_total = None
                koota_note = ""
                if bride.dob and bride.birth_time and bride.birth_place and \
                   groom.dob and groom.birth_time and groom.birth_place:
                    try:
                        bride_chart = build_chart(BirthDetails(bride.dob, bride.birth_time, bride.birth_place))
                        groom_chart = build_chart(BirthDetails(groom.dob, groom.birth_time, groom.birth_place))
                        koota_total = full_compatibility(groom_chart, bride_chart)["overall_score"]
                    except AstrologyError as e:
                        koota_note = f"astrology error: {e}"
                else:
                    koota_note = _missing_birth_detail(bride, groom)

                rows.append({
                    "Candidate ID": candidate.id,
                    "Candidate": f"#{candidate.id} {candidate.full_name or 'Unnamed'}",
                    "Practical Score": outcome.score,
                    "Mandatory OK": outcome.mandatory_passed,
                    "Recommended": outcome.recommended,
                    "Koota Score": koota_total,
                    "Koota Note": koota_note,
                })
        st.session_state["seeking_results"] = {
            "anchor_id": anchor_id, "seeking_gender": seeking_gender, "rows": rows,
            "preferences": preferences,
        }
        st.rerun()

    results = st.session_state.get("seeking_results")
    if results and results["anchor_id"] == anchor_id and results["seeking_gender"] == seeking_gender \
            and results["preferences"] == preferences:
        # Composite/Band are recomputed from the cached Practical/Koota scores
        # on every render (not baked into the cache) so moving the weight
        # slider re-ranks instantly without needing "Find best matches" again.
        df = pd.DataFrame(results["rows"])
        df["Composite"] = [
            composite_score(r["Practical Score"], r["Koota Score"], astro_weight) for _, r in df.iterrows()
        ]
        df["Band"] = df["Composite"].map(score_band)
        df = df.sort_values(
            ["Composite", "Practical Score", "Koota Score"], ascending=False, na_position="last"
        ).reset_index(drop=True)
        df_display = df.drop(columns=["Candidate ID"])[
            ["Band", "Candidate", "Composite", "Practical Score", "Koota Score",
             "Mandatory OK", "Recommended", "Koota Note"]
        ].copy()
        df_display["Composite"] = df_display["Composite"].map(lambda v: f"{v:.1f}" if pd.notna(v) else "—")
        df_display["Koota Score"] = df_display["Koota Score"].map(lambda v: f"{v:.1f}" if pd.notna(v) else "—")
        seeking_event = st.dataframe(
            df_display, width='stretch', hide_index=True,
            on_select="rerun", selection_mode="multi-row", key="seeking_results_table",
        )
        st.caption(
            "Click a row to see the full match detail — koota breakdown, AI recommendation, save — below. "
            "Ctrl/shift-click 2–3 rows to compare them side by side instead."
        )

        selected_rows = seeking_event.selection.rows if seeking_event and seeking_event.selection else []
        if len(selected_rows) == 1:
            candidate_id = int(df.iloc[selected_rows[0]]["Candidate ID"])
            if seeking_gender == "Bride":
                detail_bride_id, detail_groom_id = anchor_id, candidate_id
            else:
                detail_bride_id, detail_groom_id = candidate_id, anchor_id
            st.divider()
            theme.section(f"Match detail: Bride #{detail_bride_id} × Groom #{detail_groom_id}")

            # V4-4-3: shortlist/reject reuse the existing pipeline stage field —
            # "shortlisted" isn't a new parallel status, it's the "Interested"
            # stage already in PIPELINE_STAGES; "reject" archives via "Rejected"
            # the same way every other page does, so the funnel stays one model.
            if can_write:
                sc1, sc2 = st.columns(2)
                if sc1.button("⭐ Shortlist this candidate", key="scoreboard_shortlist"):
                    with get_session() as stage_session:
                        cand = get_owned(stage_session, Profile, candidate_id, owner)
                        cand.stage = "Interested"
                        stage_session.add(Activity(
                            profile_id=candidate_id, owner_user_id=owner, event="Shortlisted",
                            detail=f"vs #{anchor_id} from Scoreboard", created_by_user_id=current_user["id"],
                        ))
                        stage_session.commit()
                    flash(f"#{candidate_id} shortlisted (moved to Interested).")
                    st.rerun()
                if sc2.button("🗄️ Reject", key="scoreboard_reject"):
                    with get_session() as stage_session:
                        cand = get_owned(stage_session, Profile, candidate_id, owner)
                        cand.stage = "Rejected"
                        stage_session.add(Activity(
                            profile_id=candidate_id, owner_user_id=owner, event="Rejected",
                            detail=f"vs #{anchor_id} from Scoreboard", created_by_user_id=current_user["id"],
                        ))
                        stage_session.commit()
                    flash(f"#{candidate_id} archived as Rejected.")
                    st.rerun()

            render_match_detail(detail_bride_id, detail_groom_id, can_write, "seeking")
        elif 2 <= len(selected_rows) <= 3:
            candidate_ids = [int(df.iloc[i]["Candidate ID"]) for i in selected_rows]
            with get_session() as session:
                cand_profiles = {
                    p.id: p for p in session.scalars(
                        owned(select(Profile).where(Profile.id.in_(candidate_ids)), Profile, owner)
                    ).all()
                }
            col_labels = {cid: f"#{cid} {cand_profiles[cid].full_name or 'Unnamed'}" for cid in candidate_ids
                          if cid in cand_profiles}
            compare_fields = [
                ("Age", "age"), ("Height (cm)", "height_cm"), ("Location", "current_location"),
                ("Religion", "religion"), ("Caste", "caste"), ("Qualification", "qualification"),
                ("Occupation", "occupation"), ("Food Preference", "food_preference"),
            ]
            # Every cell is coerced to str — mixed numeric/"—" columns otherwise fail
            # pyarrow's dataframe serialization (st.dataframe requires uniform column types).
            compare_rows = []
            for label, attr in compare_fields:
                row = {"Field": label}
                for cid, col_label in col_labels.items():
                    value = getattr(cand_profiles.get(cid), attr, None)
                    row[col_label] = str(value) if value not in (None, "") else "—"
                compare_rows.append(row)
            for score_label, score_col in (
                ("Composite", "Composite"), ("Practical Score", "Practical Score"), ("Koota Score", "Koota Score"),
            ):
                row = {"Field": score_label}
                for cid, col_label in col_labels.items():
                    match_row = df[df["Candidate ID"] == cid]
                    value = match_row.iloc[0][score_col] if not match_row.empty else None
                    row[col_label] = str(value) if pd.notna(value) else "—"
                compare_rows.append(row)
            st.divider()
            theme.section("Compare candidates")
            st.dataframe(pd.DataFrame(compare_rows), width="stretch", hide_index=True)
        elif len(selected_rows) > 3:
            st.info("Select up to 3 candidates to compare side by side (currently more than 3 selected).")

with tab_all:
    combo_count = len(brides) * len(grooms)
    st.caption(f"{len(brides)} bride(s) × {len(grooms)} groom(s) = {combo_count} combinations")
    ALL_PAIRS_WARN_THRESHOLD = 500
    run_all = st.button("Run practical screening on all combinations")
    if run_all and combo_count > ALL_PAIRS_WARN_THRESHOLD:
        st.session_state["_confirm_screen_all"] = True
        run_all = False
    if st.session_state.get("_confirm_screen_all"):
        st.warning(
            f"{combo_count} combinations is a lot to screen at once and may take a while — proceed anyway?"
        )
        with st.container(horizontal=True):
            if st.button("Yes, screen all", key="confirm_screen_all_btn", type="primary"):
                st.session_state.pop("_confirm_screen_all")
                run_all = True
            if st.button("Cancel", key="cancel_screen_all_btn"):
                st.session_state.pop("_confirm_screen_all")
    if run_all:
        rows = []
        with get_session() as session:
            for bride in brides:
                for groom in grooms:
                    outcome = evaluate_match(bride, groom)
                    rows.append({
                        "Bride": f"#{bride.id} {bride.full_name or ''}",
                        "Groom": f"#{groom.id} {groom.full_name or ''}",
                        "Score": outcome.score,
                        "Mandatory OK": outcome.mandatory_passed,
                        "Recommended": outcome.recommended,
                    })
        df = pd.DataFrame(rows).sort_values("Score", ascending=False)
        st.dataframe(df, width='stretch', hide_index=True)

with tab_saved:
    with get_session() as session:
        saved_matches = session.scalars(
            owned(select(MatchResult), MatchResult, owner).order_by(MatchResult.created_at.desc())
        ).all()
        involved_ids = {m.bride_id for m in saved_matches} | {m.groom_id for m in saved_matches}
        profiles_by_id = {
            p.id: p for p in session.scalars(owned(select(Profile).where(Profile.id.in_(involved_ids)), Profile, owner)).all()
        } if involved_ids else {}
        actor_ids = {m.created_by_user_id for m in saved_matches if m.created_by_user_id}
        actor_names = {
            u.id: (u.full_name or u.username)
            for u in session.scalars(select(User).where(User.id.in_(actor_ids))).all()
        } if actor_ids else {}

    if not saved_matches:
        st.info(
            "No saved match results yet — evaluate a pair in the tabs above and click "
            "\"Save this match result\" to keep it here for later."
        )
    else:
        def _profile_label(pid: int) -> str:
            p = profiles_by_id.get(pid)
            return f"#{pid} {p.full_name or 'Unnamed'}" if p else f"#{pid} (deleted)"

        rows = [{
            "id": m.id,
            "Bride": _profile_label(m.bride_id),
            "Groom": _profile_label(m.groom_id),
            "Practical %": m.practical_score,
            "Koota": f"{m.koota_total:.1f}" if m.koota_total is not None else "—",
            "Recommendation": m.recommendation or "—",
            "Saved": to_local(m.created_at, owner_tz).strftime("%d %b %Y"),
            "By": actor_names.get(m.created_by_user_id, "—"),
        } for m in saved_matches]
        st.caption(f"{len(rows)} saved match result(s)")
        saved_df = pd.DataFrame(rows)
        saved_event = st.dataframe(
            saved_df.drop(columns=["id"]), width="stretch", hide_index=True,
            on_select="rerun", selection_mode="single-row", key="saved_matches_table",
        )
        st.caption("Click a row to see the full saved detail — practical breakdown, koota, AI recommendation.")

        selected_saved_rows = saved_event.selection.rows if saved_event and saved_event.selection else []
        if selected_saved_rows:
            mr_id = int(saved_df.iloc[selected_saved_rows[0]]["id"])
            with get_session() as session:
                mr = get_owned(session, MatchResult, mr_id, owner)
                bride = get_owned(session, Profile, mr.bride_id, owner) if mr else None
                groom = get_owned(session, Profile, mr.groom_id, owner) if mr else None
            if mr:
                st.divider()
                render_saved_match_result(mr, bride, groom, tz_name=owner_tz)

                if can_write:
                    confirm_key = f"confirm_delete_match_{mr.id}"
                    if confirm_key in st.session_state:
                        st.error("Really delete this saved match result? This cannot be undone.")
                        with st.container(horizontal=True):
                            if st.button("Yes, delete", key=f"confirm_delete_match_btn_{mr.id}", type="primary"):
                                with get_session() as del_session:
                                    target = get_owned(del_session, MatchResult, mr.id, owner)
                                    if target:
                                        del_session.delete(target)
                                        del_session.commit()
                                del st.session_state[confirm_key]
                                flash("Deleted saved match result.")
                                st.rerun()
                            if st.button("Cancel", key=f"cancel_delete_match_{mr.id}"):
                                del st.session_state[confirm_key]
                                st.rerun()
                    elif st.button("🗑️ Delete this saved match", key=f"delete_match_{mr.id}"):
                        st.session_state[confirm_key] = True
                        st.rerun()
