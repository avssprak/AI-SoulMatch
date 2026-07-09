import pandas as pd
import streamlit as st
from sqlalchemy import select

from soulmatch import auth, config
from soulmatch.db import get_session
from soulmatch.extraction.llm import LLMError
from soulmatch.insights import (
    best_matches_for,
    incomplete_profiles,
    pending_horoscope,
    stale_cases,
    top_astrology_matches,
)
from soulmatch.models import Profile
from soulmatch.search import apply_filters, describe_filters, parse_query

auth.require_login()
st.title("🔍 Search & Insights")

tab_search, tab_insights = st.tabs(["Natural Language Search", "Quick Insights"])

with tab_search:
    st.caption(f"Provider: **{config.LLM_PROVIDER}**. Examples: "
               "\"Show Brahmin girls in Bangalore\", \"software engineers below 30\", "
               "\"grooms with pending horoscope\".")
    query_text = st.text_input("Search", placeholder="Describe who you're looking for...")
    if st.button("Search", type="primary") and query_text.strip():
        with get_session() as session:
            try:
                filters = parse_query(session, query_text)
            except LLMError as e:
                st.error(str(e))
                filters = None
            if filters is not None:
                st.caption(f"Parsed as: {describe_filters(filters)}")
                results = apply_filters(session, filters)
                st.write(f"**{len(results)} result(s)**")
                if results:
                    rows = [{
                        "ID": p.id, "Name": p.full_name, "Gender": p.gender, "Age": p.age,
                        "Religion": p.religion, "Caste": p.caste, "Location": p.current_location,
                        "Qualification": p.qualification, "Occupation": p.occupation,
                        "Stage": p.stage, "Horoscope": "Yes" if p.horoscope_available else "No",
                    } for p in results]
                    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

with tab_insights:
    with get_session() as session:
        col1, col2 = st.columns(2)

        with col1:
            st.subheader("Pending Horoscope")
            pending = pending_horoscope(session)
            st.caption(f"{len(pending)} profile(s)")
            if pending:
                st.dataframe(pd.DataFrame([{"ID": p.id, "Name": p.full_name, "Gender": p.gender}
                                            for p in pending]), width="stretch", hide_index=True)

            st.subheader("Incomplete Profiles")
            incomplete = incomplete_profiles(session)
            st.caption(f"{len(incomplete)} profile(s) missing key fields")
            if incomplete:
                st.dataframe(pd.DataFrame([{
                    "ID": r.profile.id, "Name": r.profile.full_name,
                    "Missing": ", ".join(r.missing_fields),
                } for r in incomplete[:20]]), width="stretch", hide_index=True)

        with col2:
            st.subheader("Top Astrology Matches")
            top_matches = top_astrology_matches(session)
            if top_matches:
                st.dataframe(pd.DataFrame([{
                    "Bride #": m.bride_id, "Groom #": m.groom_id,
                    "Koota Score": f"{m.koota_total:.1f}/36", "Recommendation": m.recommendation,
                } for m in top_matches]), width="stretch", hide_index=True)
            else:
                st.caption("No astrology matches computed yet.")

            st.subheader("Stale Cases")
            stale = stale_cases(session)
            st.caption(f"{len(stale)} active profile(s) with no activity in 14+ days")
            if stale:
                st.dataframe(pd.DataFrame([{"ID": p.id, "Name": p.full_name, "Stage": p.stage}
                                            for p in stale]), width="stretch", hide_index=True)

        st.divider()
        st.subheader("Best Match Finder")
        all_profiles = session.scalars(select(Profile)).all()
        if all_profiles:
            subject_id = st.selectbox(
                "Find best matches for", [p.id for p in all_profiles],
                format_func=lambda pid: next(
                    f"#{p.id} {p.full_name or 'Unnamed'} ({p.gender})" for p in all_profiles if p.id == pid
                ),
            )
            if st.button("Find best matches"):
                matches = best_matches_for(session, subject_id)
                if not matches:
                    st.info("No opposite-gender profiles to compare against.")
                else:
                    st.dataframe(pd.DataFrame([{
                        "Candidate #": c.id, "Name": c.full_name, "Score": f"{outcome.score}%",
                        "Mandatory OK": outcome.mandatory_passed, "Recommended": outcome.recommended,
                    } for c, outcome in matches]), width="stretch", hide_index=True)
        else:
            st.info("No profiles yet.")
