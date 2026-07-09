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
from soulmatch.recommendation import generate_recommendation

current_user = auth.require_login()
can_write = auth.can_edit(current_user["role"])

st.title("💘 Matching Engine")
if not can_write:
    st.caption("Your account has read-only (Viewer) access — you can evaluate matches but not save results.")

with get_session() as session:
    brides = session.scalars(select(Profile).where(Profile.gender == "Bride")).all()
    grooms = session.scalars(select(Profile).where(Profile.gender == "Groom")).all()

if not brides or not grooms:
    st.info("Need at least one Bride and one Groom profile. Add some via **Ingest** or **Profiles**.")
    st.stop()

tab_single, tab_all = st.tabs(["Single Match", "Run All Combinations"])

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

    if st.button("Evaluate Match", type="primary"):
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

        st.session_state["match_eval"] = {
            "bride_id": bride_id, "groom_id": groom_id,
            "outcome": outcome, "astro_result": astro_result,
            "koota_total": koota_total, "astro_error": astro_error,
        }
        st.session_state.pop("match_recommendation", None)
        st.rerun()

    eval_state = st.session_state.get("match_eval")
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
        if st.button("Generate AI Recommendation"):
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
                    st.session_state["match_recommendation"] = rec
            st.rerun()

        recommendation = st.session_state.get("match_recommendation")
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
            st.caption(f"Generated via {recommendation.get('_provider', 'unknown')} provider")

        if can_write and st.button("Save this match result", type="primary"):
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
                )
                session2.add(mr)
                session2.add(Activity(profile_id=bride_id, event="Match evaluated",
                                       detail=f"vs groom #{groom_id}"))
                session2.add(Activity(profile_id=groom_id, event="Match evaluated",
                                       detail=f"vs bride #{bride_id}"))
                session2.commit()
            st.success("Match result saved.")

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
