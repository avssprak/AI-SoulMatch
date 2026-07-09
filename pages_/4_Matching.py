import pandas as pd
import streamlit as st
from sqlalchemy import select

from soulmatch.astrology.engine import AstrologyError, BirthDetails, build_chart, full_compatibility
from soulmatch.db import get_session
from soulmatch.matching.rules import evaluate_match
from soulmatch.models import Activity, MatchResult, Profile

st.title("💘 Matching Engine")

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

            st.subheader("Practical Compatibility")
            badge = "✅ Recommended" if outcome.recommended else "❌ Not Recommended"
            st.metric("Practical Score", f"{outcome.score}%", badge)
            if not outcome.mandatory_passed:
                st.error("A mandatory criterion failed — see below.")

            rule_rows = [{"Rule": r.name, "Mandatory": r.mandatory, "Passed": r.passed, "Detail": r.detail}
                         for r in outcome.results]
            st.dataframe(pd.DataFrame(rule_rows), use_container_width=True, hide_index=True)
            if outcome.missing_fields:
                st.caption(f"Missing data for a full assessment: {', '.join(outcome.missing_fields)}")

            koota_total = None
            astro_result = None
            if bride.dob and bride.birth_time and bride.birth_place and \
               groom.dob and groom.birth_time and groom.birth_place:
                try:
                    bride_chart = build_chart(BirthDetails(bride.dob, bride.birth_time, bride.birth_place))
                    groom_chart = build_chart(BirthDetails(groom.dob, groom.birth_time, groom.birth_place))
                    astro_result = full_compatibility(groom_chart, bride_chart)
                    koota_total = astro_result["overall_score"]

                    st.subheader("Vedic Astrology Compatibility")
                    st.metric("Ashta Koota Score", f"{koota_total:.1f} / 36", astro_result["overall_verdict"])
                    koota_rows = [{"Koota": name, "Score": f"{v['score']:.1f} / {v['max']}", "Detail": v["detail"]}
                                  for name, v in astro_result["koota"]["kootas"].items()]
                    st.dataframe(pd.DataFrame(koota_rows), use_container_width=True, hide_index=True)

                    if astro_result["dosha_flags"]:
                        st.warning("Dosha flags: " + "; ".join(astro_result["dosha_flags"]))
                    else:
                        st.success("No major doshas flagged.")
                except AstrologyError as e:
                    st.warning(f"Could not compute astrology: {e}")
            else:
                st.info("Add DOB, birth time and birth place for both profiles to see astrology compatibility.")

            with st.expander("AI Recommendation Summary"):
                lines = []
                if outcome.recommended:
                    lines.append(f"Practical fit looks strong ({outcome.score}%).")
                else:
                    lines.append(f"Practical fit is weak ({outcome.score}%) — review flagged criteria.")
                if outcome.strengths():
                    lines.append("**Strengths:** " + "; ".join(outcome.strengths()[:5]))
                if outcome.weaknesses():
                    lines.append("**Concerns:** " + "; ".join(outcome.weaknesses()[:5]))
                if koota_total is not None:
                    lines.append(f"Astrology: {koota_total:.1f}/36 ({astro_result['overall_verdict']}).")
                    if astro_result["dosha_flags"]:
                        lines.append("Doshas to discuss with families: " + "; ".join(astro_result["dosha_flags"]))
                if outcome.missing_fields:
                    lines.append(f"Missing information: {', '.join(outcome.missing_fields)}.")
                st.markdown("\n\n".join(lines))

            if st.button("Save this match result"):
                with get_session() as session2:
                    mr = MatchResult(
                        bride_id=bride_id, groom_id=groom_id,
                        practical_score=outcome.score,
                        practical_detail={"strengths": outcome.strengths(), "weaknesses": outcome.weaknesses()},
                        koota_total=koota_total,
                        koota_detail=astro_result["koota"] if astro_result else None,
                        dosha_detail={"flags": astro_result["dosha_flags"]} if astro_result else None,
                        recommendation="Recommended" if outcome.recommended else "Not Recommended",
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
        st.dataframe(df, use_container_width=True, hide_index=True)
