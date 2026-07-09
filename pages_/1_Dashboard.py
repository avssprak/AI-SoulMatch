import pandas as pd
import plotly.express as px
import streamlit as st
from sqlalchemy import select

from soulmatch.db import get_session
from soulmatch.models import Activity, MatchResult, Profile

st.title("📊 Executive Dashboard")

with get_session() as session:
    profiles = session.scalars(select(Profile)).all()
    matches = session.scalars(select(MatchResult)).all()
    recent_activity = session.scalars(
        select(Activity).order_by(Activity.created_at.desc()).limit(15)
    ).all()

total = len(profiles)
brides = sum(1 for p in profiles if p.gender == "Bride")
grooms = sum(1 for p in profiles if p.gender == "Groom")
pending_horoscope = sum(1 for p in profiles if not p.horoscope_available)
active_cases = sum(1 for p in profiles if p.stage not in ("Marriage", "Rejected", "Closed"))
marriages = sum(1 for p in profiles if p.stage == "Marriage")

c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("Total Profiles", total)
c2.metric("Brides", brides)
c3.metric("Grooms", grooms)
c4.metric("Active Cases", active_cases)
c5.metric("Pending Horoscope", pending_horoscope)
c6.metric("Marriages", marriages)

st.divider()

col1, col2 = st.columns(2)

with col1:
    st.subheader("Pipeline Stage Distribution")
    if profiles:
        stage_counts = pd.Series([p.stage for p in profiles]).value_counts().reset_index()
        stage_counts.columns = ["stage", "count"]
        fig = px.bar(stage_counts, x="stage", y="count")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No profiles yet — go to **Ingest WhatsApp** to add some.")

with col2:
    st.subheader("Match Compatibility Scores")
    if matches:
        df = pd.DataFrame([{"koota_total": m.koota_total or 0} for m in matches])
        fig = px.histogram(df, x="koota_total", nbins=12, range_x=[0, 36])
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No matches computed yet — go to **Matching**.")

st.divider()
st.subheader("Recent Activity")
if recent_activity:
    for a in recent_activity:
        st.markdown(f"**{a.created_at:%d %b, %H:%M}** — {a.event}" + (f": {a.detail}" if a.detail else ""))
else:
    st.caption("No activity recorded yet.")
