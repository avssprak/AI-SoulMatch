import json

import pandas as pd
import streamlit as st
from sqlalchemy import select

from soulmatch import auth
from soulmatch.astrology.engine import AstrologyError, BirthDetails, build_chart, full_compatibility
from soulmatch.db import get_session
from soulmatch.extraction.llm import LLMError
from soulmatch.matching.rules import evaluate_match
from soulmatch.models import Activity, MatchResult, Profile
from soulmatch.preferences import CandidatePreferences, filter_candidates
from soulmatch.recommendation import generate_recommendation
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
            bride = session.get(Profile, bride_id)
            groom = session.get(Profile, groom_id)
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

        st.subheader("Practical Compatibility")
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
            st.subheader("Vedic Astrology Compatibility")
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

        st.subheader("AI Recommendation")
        if st.button("Generate AI Recommendation", key=f"{state_prefix}_generate_rec_btn"):
            with get_session() as session:
                bride = session.get(Profile, bride_id)
                groom = session.get(Profile, groom_id)
                practical = {
                    "score": outcome.score, "recommended": outcome.recommended,
                    "strengths": outcome.strengths(), "weaknesses": outcome.weaknesses(),
                }
                try:
                    rec = generate_recommendation(bride, groom, practical, astro_result)
                except LLMError as e:
                    st.error(str(e))
                else:
                    st.session_state[rec_key] = rec
            st.rerun()

        recommendation = st.session_state.get(rec_key)
        if recommendation:
            final = recommendation.get("final_recommendation") or "Unknown"
            if final == "Recommended":
                st.success(f"**{final}** — {recommendation.get('summary', '')}")
            elif final == "Not Recommended":
                st.error(f"**{final}** — {recommendation.get('summary', '')}")
            else:
                st.warning(f"**{final}** — {recommendation.get('summary', '')}")

            rc1, rc2 = st.columns(2)
            with rc1:
                st.markdown("**Strengths**")
                for s in recommendation.get("strengths") or []:
                    st.markdown(f"- {s}")
                st.markdown("**Questions for Families**")
                for q in recommendation.get("questions_for_families") or []:
                    st.markdown(f"- {q}")
            with rc2:
                st.markdown("**Concerns**")
                for c in recommendation.get("concerns") or []:
                    st.markdown(f"- {c}")
                if recommendation.get("risk_indicators"):
                    st.markdown("**Risk Indicators**")
                    for r in recommendation["risk_indicators"]:
                        st.markdown(f"- ⚠️ {r}")

            st.markdown(f"**Family compatibility:** {recommendation.get('family_compatibility', '')}")
            st.markdown(f"**Lifestyle compatibility:** {recommendation.get('lifestyle_compatibility', '')}")
            st.markdown(f"**Career compatibility:** {recommendation.get('career_compatibility', '')}")
            st.caption(f"Generated via {recommendation.get('_provider', 'unknown')} AI service")

        if can_write and st.button("Save this match result", type="primary", key=f"{state_prefix}_save_btn"):
            with get_session() as session2:
                mr = MatchResult(
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
                session2.add(Activity(profile_id=bride_id, event="Match evaluated",
                                       detail=f"vs groom #{groom_id}", created_by_user_id=current_user["id"]))
                session2.add(Activity(profile_id=groom_id, event="Match evaluated",
                                       detail=f"vs bride #{bride_id}", created_by_user_id=current_user["id"]))
                session2.commit()
            flash("Match result saved.")
            st.rerun()


current_user = auth.require_login()
can_write = auth.can_edit(current_user["role"])

st.title("💘 Matching Engine")
show_flash()
if not can_write:
    st.caption("Your account has read-only (Viewer) access — you can evaluate matches but not save results.")

with get_session() as session:
    brides = session.scalars(select(Profile).where(Profile.gender == "Bride")).all()
    grooms = session.scalars(select(Profile).where(Profile.gender == "Groom")).all()

if not brides or not grooms:
    st.info("Need at least one Bride and one Groom profile. Add some via **Import Messages** or **Profiles**.")
    st.stop()

tab_single, tab_seeking, tab_all = st.tabs(["Single Match", "Find Matches For One Profile", "Run All Combinations"])

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
    render_match_detail(bride_id, groom_id, can_write, "single")

with tab_seeking:
    st.caption(
        "For when one side is the 'main' profile — e.g. a Bride's family wants to keep her "
        "horoscope fixed and browse every Groom against it, ranked by compatibility."
    )
    seeking_gender = st.radio("Seeking matches for a:", ["Bride", "Groom"], horizontal=True, key="seeking_gender")
    anchor_pool = brides if seeking_gender == "Bride" else grooms
    candidate_pool = grooms if seeking_gender == "Bride" else brides
    opposite_label = "Groom" if seeking_gender == "Bride" else "Bride"

    anchor_id = st.selectbox(
        f"Which {seeking_gender.lower()} is the main profile?",
        [p.id for p in anchor_pool],
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
            anchor = session.get(Profile, anchor_id)
            for candidate in filtered_candidate_pool:
                cand = session.get(Profile, candidate.id)
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
        df = pd.DataFrame(results["rows"]).sort_values(
            ["Practical Score", "Koota Score"], ascending=False, na_position="last"
        ).reset_index(drop=True)
        df_display = df.drop(columns=["Candidate ID"]).copy()
        df_display["Koota Score"] = df_display["Koota Score"].map(lambda v: f"{v:.1f}" if pd.notna(v) else "—")
        seeking_event = st.dataframe(
            df_display, width='stretch', hide_index=True,
            on_select="rerun", selection_mode="single-row", key="seeking_results_table",
        )
        st.caption("Click a row to see the full match detail — koota breakdown, AI recommendation, save — below.")

        selected_rows = seeking_event.selection.rows if seeking_event and seeking_event.selection else []
        if selected_rows:
            candidate_id = int(df.iloc[selected_rows[0]]["Candidate ID"])
            if seeking_gender == "Bride":
                detail_bride_id, detail_groom_id = anchor_id, candidate_id
            else:
                detail_bride_id, detail_groom_id = candidate_id, anchor_id
            st.divider()
            st.subheader(f"Match detail: Bride #{detail_bride_id} × Groom #{detail_groom_id}")
            render_match_detail(detail_bride_id, detail_groom_id, can_write, "seeking")

with tab_all:
    st.caption(f"{len(brides)} bride(s) × {len(grooms)} groom(s) = {len(brides) * len(grooms)} combinations")
    if st.button("Run practical screening on all combinations"):
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
