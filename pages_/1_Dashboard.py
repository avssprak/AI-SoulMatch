import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from sqlalchemy import select

from soulmatch import auth, config, theme
from soulmatch.db import get_session
from soulmatch.insights import stale_cases
from soulmatch.models import PIPELINE_STAGE_GROUPS, Activity, MatchResult, Profile, RawMessage
from soulmatch.nav import SEARCH_PAGE, TASKS_OVERDUE_PREF_KEY, TASKS_PAGE, open_profile_button
from soulmatch.tasks import overdue_tasks, pending_tasks

auth.require_login()
theme.page_header("Dashboard", "Your entire practice at a glance — pipeline, follow-ups, and match activity.")

with get_session() as session:
    profiles = session.scalars(select(Profile)).all()
    matches = session.scalars(select(MatchResult)).all()
    recent_activity = session.scalars(
        select(Activity).order_by(Activity.created_at.desc()).limit(15)
    ).all()
    pending_task_count = len(pending_tasks(session))
    overdue_task_count = len(overdue_tasks(session))
    stale_case_count = len(stale_cases(session))
    unprocessed_count = len(session.scalars(select(RawMessage).where(RawMessage.processed.is_(False))).all())

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

# "Today" digest — deterministic database counts, not an LLM call (same
# reasoning as soulmatch.insights: these questions don't need natural-
# language interpretation to answer correctly, so this is free and instant).
theme.section("Today", "What needs your attention this morning.")
today_items = []
if overdue_task_count:
    today_items.append((f"⚠️ {overdue_task_count} overdue task(s)", "dash_today_tasks", TASKS_PAGE))
if unprocessed_count:
    today_items.append((f"📥 {unprocessed_count} imported message(s) waiting to be processed",
                         "dash_today_ingest", "pages_/2_Ingest.py"))
if pending_horoscope_count:
    today_items.append((f"🔯 {pending_horoscope_count} profile(s) missing a horoscope",
                         "dash_today_astro", "pages_/5_Astrology.py"))
if stale_case_count:
    today_items.append((f"💤 {stale_case_count} stale case(s) — no activity in 14+ days",
                         "dash_today_stale", SEARCH_PAGE))

if today_items:
    for label, key, target in today_items:
        tc1, tc2 = st.columns([5, 1])
        tc1.markdown(f"- {label}")
        if tc2.button("Go →", key=key):
            if target == TASKS_PAGE:
                st.session_state[TASKS_OVERDUE_PREF_KEY] = True
            st.switch_page(target)
else:
    theme.empty_state("All caught up", "Nothing urgent today — enjoy the calm.", icon="🌿")

st.divider()

row1 = st.columns(4)
row1[0].metric("Active Cases", active_cases)
if row1[0].button("Open Profiles →", key="dash_open_profiles"):
    st.switch_page("pages_/3_Profiles.py")
row1[1].metric("Pending Horoscope", pending_horoscope_count)
if row1[1].button("Compute & save a chart →", key="dash_open_astro"):
    st.switch_page("pages_/5_Astrology.py")
row1[2].metric("Overdue Tasks", overdue_task_count)
if row1[2].button("Open overdue tasks →", key="dash_overdue_tasks"):
    st.session_state[TASKS_OVERDUE_PREF_KEY] = True
    st.switch_page(TASKS_PAGE)
row1[3].metric("Stale Cases", stale_case_count)
if row1[3].button("See Quick Insights →", key="dash_open_insights"):
    st.switch_page(SEARCH_PAGE)

row2 = st.columns(4)
row2[0].metric("Total Profiles", total)
row2[1].metric("Brides", brides)
row2[2].metric("Grooms", grooms)
row2[3].metric("Marriages", marriages)
st.caption(f"Pending Tasks: {pending_task_count}")

st.divider()

if total < 3:
    theme.section("Getting started", "A few profiles help the charts below mean something — here's the usual first path.")
    ai_configured = config.LLM_PROVIDER != "mock"
    checklist = [
        (ai_configured, "Connect a real AI service (currently offline/mock)" if not ai_configured
         else "AI service connected", "pages_/2_Ingest.py" if not ai_configured else None),
        (total > 0, "Import a WhatsApp export or document and extract a profile", "pages_/2_Ingest.py"),
        (any(p.horoscope_available for p in profiles), "Compute a horoscope chart for a profile", "pages_/5_Astrology.py"),
        (len(matches) > 0, "Run your first match", "pages_/4_Matching.py"),
    ]
    for i, (done, label, target) in enumerate(checklist):
        c1, c2 = st.columns([5, 2])
        c1.markdown(("✅ " if done else "⬜ ") + label)
        if not done and target and c2.button("Go →", key=f"onboarding_go_{i}"):
            st.switch_page(target)
else:
    col1, col2 = st.columns(2)

    with col1:
        theme.section("Pipeline Funnel", "Where cases sit: screening → outreach → outcome.")
        stage_counts = pd.Series([p.stage for p in profiles]).value_counts()
        group_rows = []
        for group, stages in PIPELINE_STAGE_GROUPS.items():
            per_stage = [(s, int(stage_counts.get(s, 0))) for s in stages]
            group_rows.append({
                "group": group,
                "count": sum(n for _, n in per_stage),
                "detail": "<br>".join(f"{s}: {n}" for s, n in per_stage if n),
            })
        fig = go.Figure(go.Funnel(
            y=[r["group"] for r in group_rows],
            x=[r["count"] for r in group_rows],
            marker=dict(color=theme.CHART_SEQUENCE[:len(group_rows)]),
            customdata=[r["detail"] or "—" for r in group_rows],
            hovertemplate="<b>%{y}</b>: %{x} case(s)<br><br>%{customdata}<extra></extra>",
            textinfo="value",
            connector=dict(line=dict(color=theme.LINE, width=1)),
        ))
        st.plotly_chart(theme.brand_chart(fig), width='stretch')

    with col2:
        theme.section("Age Distribution — Brides vs Grooms", "Do the two pools overlap where it matters?")
        age_rows = [{"age": p.age, "Gender": p.gender} for p in profiles if p.age]
        if age_rows:
            df = pd.DataFrame(age_rows)
            fig = px.histogram(
                df, x="age", color="Gender", barmode="overlay", opacity=0.72,
                color_discrete_map={"Bride": theme.BRIDE_COLOR, "Groom": theme.GROOM_COLOR},
            )
            fig.update_traces(marker_line_width=0, marker_cornerradius=4)
            fig.update_layout(legend=dict(orientation="h", y=1.08, x=0, title=None))
            st.plotly_chart(theme.brand_chart(fig), width='stretch')
            missing_age = total - len(age_rows)
            if missing_age:
                st.caption(f"{missing_age} profile(s) without an age are not shown.")
        else:
            theme.empty_state("No ages recorded yet", "Ages appear on profiles after extraction or editing.", icon="🎂")

    col3, col4 = st.columns(2)

    with col3:
        theme.section("Profiles Added Over Time", "Weekly intake — is the practice growing?")
        created = pd.DataFrame({"created": [p.created_at for p in profiles]})
        weekly = created.set_index("created").resample("W").size().rename("added").reset_index()
        fig = px.area(weekly, x="created", y="added")
        fig.update_traces(line=dict(width=2), fillcolor="rgba(122,30,63,0.15)")
        fig.update_layout(xaxis_title=None, yaxis_title="profiles / week")
        st.plotly_chart(theme.brand_chart(fig), width='stretch')

    with col4:
        theme.section("Match Compatibility Scores")
        if matches:
            df = pd.DataFrame([{"koota_total": m.koota_total or 0} for m in matches])
            fig = px.histogram(df, x="koota_total", nbins=12, range_x=[0, 36])
            fig.update_traces(marker_line_width=0, marker_cornerradius=4)
            st.plotly_chart(theme.brand_chart(fig), width='stretch')
        else:
            theme.empty_state("No matches computed yet", "Run your first match under Matchmaking.", icon="💘")

st.divider()
theme.section("Recent Activity")
if recent_activity:
    for a in recent_activity:
        name = activity_profile_names.get(a.profile_id) or "Unnamed"
        ac1, ac2 = st.columns([6, 1])
        ac1.markdown(
            f"**{a.created_at:%d %b, %H:%M}** — {a.event} · {name} (#{a.profile_id})"
            + (f": {a.detail}" if a.detail else "")
        )
        open_profile_button(a.profile_id, label="Open", key=f"dash_open_{a.id}")
else:
    theme.empty_state("No activity recorded yet", "Imports, matches, and task updates will appear here.", icon="🕊️")
