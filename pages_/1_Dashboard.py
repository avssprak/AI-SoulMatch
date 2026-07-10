import pandas as pd
import plotly.express as px
import streamlit as st
from sqlalchemy import select

from soulmatch import auth
from soulmatch.db import get_session
from soulmatch.insights import stale_cases
from soulmatch.models import PIPELINE_STAGES, Activity, MatchResult, Profile
from soulmatch.tasks import overdue_tasks, pending_tasks

auth.require_login()
st.title("📊 Executive Dashboard")

with get_session() as session:
    profiles = session.scalars(select(Profile)).all()
    matches = session.scalars(select(MatchResult)).all()
    recent_activity = session.scalars(
        select(Activity).order_by(Activity.created_at.desc()).limit(15)
    ).all()
    pending_task_count = len(pending_tasks(session))
    overdue_task_count = len(overdue_tasks(session))
    stale_case_count = len(stale_cases(session))

    profile_ids = {a.profile_id for a in recent_activity}
    activity_profile_names = {
        p.id: p.full_name
        for p in session.scalars(select(Profile).where(Profile.id.in_(profile_ids))).all()
    }

total = len(profiles)
brides = sum(1 for p in profiles if p.gender == "Bride")
grooms = sum(1 for p in profiles if p.gender == "Groom")
pending_horoscope_count = sum(1 for p in profiles if not p.horoscope_available)
active_cases = sum(1 for p in profiles if p.stage not in ("Marriage", "Rejected", "Closed"))
marriages = sum(1 for p in profiles if p.stage == "Marriage")

row1 = st.columns(4)
row1[0].metric("Active Cases", active_cases)
row1[0].caption("→ Profiles: filter by Stage")
row1[1].metric("Pending Horoscope", pending_horoscope_count)
row1[1].caption("→ Astrology: compute & save a chart")
row1[2].metric("Overdue Tasks", overdue_task_count)
row1[2].caption("→ Tasks: Overdue only")
row1[3].metric("Stale Cases", stale_case_count)
row1[3].caption("→ Search & Insights: Quick Insights")

row2 = st.columns(4)
row2[0].metric("Total Profiles", total)
row2[1].metric("Brides", brides)
row2[2].metric("Grooms", grooms)
row2[3].metric("Marriages", marriages)
st.caption(f"Pending Tasks: {pending_task_count}")

st.divider()

col1, col2 = st.columns(2)

with col1:
    st.subheader("Case Status Distribution")
    if profiles:
        stage_counts = pd.Series([p.stage for p in profiles]).value_counts().reindex(
            PIPELINE_STAGES, fill_value=0
        ).reset_index()
        stage_counts.columns = ["stage", "count"]
        fig = px.bar(stage_counts, x="stage", y="count")
        fig.update_xaxes(categoryorder="array", categoryarray=PIPELINE_STAGES)
        st.plotly_chart(fig, width='stretch')
    else:
        st.info("No profiles yet — go to **Import Messages** to add some.")

with col2:
    st.subheader("Match Compatibility Scores")
    if matches:
        df = pd.DataFrame([{"koota_total": m.koota_total or 0} for m in matches])
        fig = px.histogram(df, x="koota_total", nbins=12, range_x=[0, 36])
        st.plotly_chart(fig, width='stretch')
    else:
        st.info("No matches computed yet — go to **Matching**.")

st.divider()
st.subheader("Recent Activity")
if recent_activity:
    for a in recent_activity:
        name = activity_profile_names.get(a.profile_id) or "Unnamed"
        st.markdown(
            f"**{a.created_at:%d %b, %H:%M}** — {a.event} · {name} (#{a.profile_id})"
            + (f": {a.detail}" if a.detail else "")
        )
else:
    st.caption("No activity recorded yet.")
