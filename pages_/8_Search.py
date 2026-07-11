import pandas as pd
import streamlit as st

from soulmatch import auth, config, theme
from soulmatch.db import get_session
from soulmatch.extraction.llm import LLMError
from soulmatch.insights import incomplete_profiles, pending_horoscope, stale_cases, top_astrology_matches
from soulmatch.nav import open_profile_button
from soulmatch.search import apply_filters, describe_filters, parse_query

auth.require_login()
theme.page_header("Search & Insights", "Ask questions in plain language and get instant answers across your whole database.")

tab_search, tab_insights = st.tabs(["Natural Language Search", "Quick Insights"])

with tab_search:
    st.caption(f"AI service: **{config.LLM_PROVIDER}**. Examples: "
               "\"Show Brahmin girls in Bangalore\", \"software engineers below 30\", "
               "\"grooms with pending horoscope\".")
    if config.LLM_PROVIDER == "mock":
        st.warning(
            "⚠️ Offline extraction mode — search still works via a simpler keyword matcher, but "
            "understands fewer phrasings than a real AI service. Add a GEMINI_API_KEY or "
            "ANTHROPIC_API_KEY in .env and restart the app for better results."
        )
    query_text = st.text_input("Search", placeholder="Describe who you're looking for...")
    if st.button("Search", type="primary") and query_text.strip():
        with get_session() as session:
            try:
                filters = parse_query(session, query_text)
            except LLMError as e:
                st.error(str(e))
                filters = None
            if filters is not None:
                results = apply_filters(session, filters)
                st.session_state["search_results"] = {
                    "query": query_text,
                    "filters_desc": describe_filters(filters),
                    "rows": [{
                        "ID": p.id, "Name": p.full_name, "Gender": p.gender, "Age": p.age,
                        "Religion": p.religion, "Caste": p.caste, "Location": p.current_location,
                        "Qualification": p.qualification, "Occupation": p.occupation,
                        "Stage": p.stage, "Horoscope": "Yes" if p.horoscope_available else "No",
                    } for p in results],
                }
        st.rerun()

    search_state = st.session_state.get("search_results")
    if search_state and search_state["query"] == query_text:
        st.caption(f"Parsed as: {search_state['filters_desc']}")
        rows = search_state["rows"]
        st.write(f"**{len(rows)} result(s)**")
        if rows:
            results_df = pd.DataFrame(rows)
            st.download_button(
                "⬇️ Export as CSV", results_df.to_csv(index=False).encode("utf-8-sig"),
                file_name="search_results.csv", mime="text/csv", key="export_search_csv",
            )
            search_event = st.dataframe(
                results_df, width="stretch", hide_index=True,
                on_select="rerun", selection_mode="single-row", key="search_results_table",
            )
            st.caption("Click a row for a quick summary.")

            selected_search_rows = (
                search_event.selection.rows if search_event and search_event.selection else []
            )
            if selected_search_rows:
                picked = results_df.iloc[selected_search_rows[0]]
                with st.container(border=True):
                    st.markdown(f"**#{picked['ID']} {picked['Name'] or 'Unnamed'}** — {picked['Gender']}")
                    c1, c2, c3 = st.columns(3)
                    c1.markdown(f"**Age:** {picked['Age'] or '—'}")
                    c2.markdown(f"**Location:** {picked['Location'] or '—'}")
                    c3.markdown(f"**Stage:** {picked['Stage']}")
                    c1, c2, c3 = st.columns(3)
                    c1.markdown(f"**Religion:** {picked['Religion'] or '—'}")
                    c2.markdown(f"**Caste:** {picked['Caste'] or '—'}")
                    c3.markdown(f"**Horoscope:** {picked['Horoscope']}")
                    open_profile_button(int(picked["ID"]), label="Open profile to edit, view documents, or manage tasks")

with tab_insights:
    with get_session() as session:
        col1, col2 = st.columns(2)

        def _open_profile_picker(profiles_list, key: str) -> None:
            """Compact selectbox + Open button under an Insights list — these
            tables aren't selectable dataframes, so this is the deep-link
            entry point for them instead."""
            if not profiles_list:
                return
            pc1, pc2 = st.columns([3, 1])
            pid = pc1.selectbox(
                "Open a profile", [p.id for p in profiles_list],
                format_func=lambda i: next(f"#{p.id} {p.full_name or 'Unnamed'}" for p in profiles_list if p.id == i),
                key=key, label_visibility="collapsed",
            )
            with pc2:
                open_profile_button(pid, label="Open", key=f"{key}_btn")

        with col1:
            theme.section("Pending Horoscope")
            pending = pending_horoscope(session)
            st.caption(f"{len(pending)} profile(s)")
            if pending:
                st.dataframe(pd.DataFrame([{"ID": p.id, "Name": p.full_name, "Gender": p.gender}
                                            for p in pending]), width="stretch", hide_index=True)
                _open_profile_picker(pending, "open_pending_horoscope")

            theme.section("Incomplete Profiles")
            incomplete = incomplete_profiles(session)
            st.caption(f"{len(incomplete)} profile(s) missing key fields")
            if incomplete:
                st.dataframe(pd.DataFrame([{
                    "ID": r.profile.id, "Name": r.profile.full_name,
                    "Missing": ", ".join(r.missing_fields),
                } for r in incomplete[:20]]), width="stretch", hide_index=True)
                _open_profile_picker([r.profile for r in incomplete[:20]], "open_incomplete")

        with col2:
            theme.section("Top Astrology Matches")
            top_matches = top_astrology_matches(session)
            if top_matches:
                st.dataframe(pd.DataFrame([{
                    "Bride #": m.bride_id, "Groom #": m.groom_id,
                    "Koota Score": f"{m.koota_total:.1f}/36", "Recommendation": m.recommendation,
                } for m in top_matches]), width="stretch", hide_index=True)
            else:
                st.caption("No astrology matches computed yet.")

            theme.section("Stale Cases")
            stale = stale_cases(session)
            st.caption(f"{len(stale)} active profile(s) with no activity in 14+ days")
            if stale:
                st.dataframe(pd.DataFrame([{"ID": p.id, "Name": p.full_name, "Stage": p.stage}
                                            for p in stale]), width="stretch", hide_index=True)
                _open_profile_picker(stale, "open_stale")

        st.divider()
        theme.section("Best Match Finder")
        st.caption(
            "Moved — use **Matchmaking → Find Matches for Someone** for this. "
            "That version also includes astrology koota scores and lets you drill into "
            "full match detail (AI recommendation, save result) for any candidate."
        )
