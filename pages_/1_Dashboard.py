import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from sqlalchemy import select

from soulmatch import auth, theme
from soulmatch.db import get_session
from soulmatch.insights import stale_cases, stale_shortlisted
from soulmatch.models import PIPELINE_STAGE_GROUPS, Activity, MatchResult, Profile, RawMessage, Task
from soulmatch.nav import (
    GUIDE_PAGE, INGEST_PAGE, MATCHING_PAGE, MY_CHILD_PAGE, PROFILES_PAGE, SEARCH_PAGE,
    TASKS_OVERDUE_PREF_KEY, TASKS_PAGE, open_profile_button,
)
from soulmatch.tasks import overdue_tasks, pending_tasks
from soulmatch.tenancy import owned, owner_id_of
from soulmatch.timezones import to_local

user = auth.require_login()
owner = owner_id_of(user)

with get_session() as session:
    profiles = session.scalars(owned(select(Profile), Profile, owner)).all()
    matches = session.scalars(owned(select(MatchResult), MatchResult, owner)).all()
    recent_activity = session.scalars(
        owned(select(Activity), Activity, owner).order_by(Activity.created_at.desc()).limit(15)
    ).all()
    pending_task_count = len(pending_tasks(session, owner))
    overdue_task_count = len(overdue_tasks(session, owner))
    stale_case_count = len(stale_cases(session, owner))
    stale_shortlist_count = len(stale_shortlisted(session, owner))
    unprocessed_count = len(session.scalars(
        owned(select(RawMessage).where(RawMessage.processed.is_(False)), RawMessage, owner)
    ).all())
    any_task_exists = session.scalar(owned(select(Task.id), Task, owner).limit(1)) is not None

    profile_ids = {a.profile_id for a in recent_activity}
    activity_profile_names = {
        p.id: p.full_name
        for p in session.scalars(owned(select(Profile).where(Profile.id.in_(profile_ids)), Profile, owner)).all()
    }

child = next((p for p in profiles if getattr(p, "is_own_child", False)), None)
theme.page_header(
    "Dashboard",
    f"{child.full_name}'s search at a glance — proposals in play, follow-ups, and match activity."
    if child and child.full_name else
    "Your child's search at a glance — proposals in play, follow-ups, and match activity.",
)

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
                         "dash_today_ingest", INGEST_PAGE))
if pending_horoscope_count:
    today_items.append((f"🔯 {pending_horoscope_count} candidate(s) missing a horoscope",
                         "dash_today_astro", PROFILES_PAGE))
if stale_shortlist_count:
    today_items.append((
        f"⭐ {stale_shortlist_count} shortlisted candidate(s) waiting on you — no follow-up in 7+ days",
        "dash_today_shortlist_stale", PROFILES_PAGE,
    ))
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
if row1[0].button("Open Candidates →", key="dash_open_profiles"):
    st.switch_page(PROFILES_PAGE)
row1[1].metric("Pending Horoscope", pending_horoscope_count)
if row1[1].button("Compute & save a chart →", key="dash_open_astro"):
    st.switch_page(PROFILES_PAGE)
row1[2].metric("Overdue Tasks", overdue_task_count)
if row1[2].button("Open overdue tasks →", key="dash_overdue_tasks"):
    st.session_state[TASKS_OVERDUE_PREF_KEY] = True
    st.switch_page(TASKS_PAGE)
row1[3].metric("Stale Cases", stale_case_count)
if row1[3].button("See Quick Insights →", key="dash_open_insights"):
    st.switch_page(SEARCH_PAGE)

row2 = st.columns(4)
row2[0].metric("Total Candidates", total)
row2[1].metric("Brides", brides)
row2[2].metric("Grooms", grooms)
row2[3].metric("Marriages", marriages)
st.caption(f"Pending Tasks: {pending_task_count}")

st.divider()

# V4-2-2/V4-2-3: always-visible 4-step journey strip — replaces the old
# `total < 3` gated checklist (V3-6-3). Every step checks off from real data,
# not a session flag, so it stays honest even if a member deletes everything
# back down to zero.
has_child = child is not None
candidate_count = total - (1 if has_child else 0)
has_match = len(matches) > 0
journey_steps = [
    (has_child, "My Child", MY_CHILD_PAGE, "Set up your child's prime profile"),
    (candidate_count > 0, "Candidates", INGEST_PAGE, "Add a candidate — a WhatsApp chat or a pasted biodata"),
    (has_match, "Match", MATCHING_PAGE, "Run your first horoscope match"),
    (any_task_exists, "Follow Up", TASKS_PAGE, "Add a follow-up task for a candidate you're pursuing"),
]
theme.section("Your journey")
theme.journey_stepper([(done, label) for done, label, _, _ in journey_steps])
current_step = next(((label, target, cta) for done, label, target, cta in journey_steps if not done), None)
if current_step:
    label, target, cta = current_step
    sc1, sc2 = st.columns([5, 2])
    sc1.markdown(f"**Next: {label}** — {cta}")
    if sc2.button("Go →", key="journey_current_step_go"):
        st.switch_page(target)
else:
    st.caption("🎉 You've completed every step of the journey — keep going below.")

if current_step:
    if st.button("📖 New here? Read how it works →", key="dash_guide_link", type="tertiary"):
        st.switch_page(GUIDE_PAGE)

st.divider()

if total >= 3:
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
        theme.section("Profiles Added Over Time", "Weekly intake — how many new biodatas are coming in?")
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
            theme.empty_state("No matches computed yet", "Run your first match under Match & Compare.", icon="💘")

st.divider()
theme.section("Recent Activity")
if recent_activity:
    for a in recent_activity:
        name = activity_profile_names.get(a.profile_id) or "Unnamed"
        ac1, ac2 = st.columns([6, 1])
        ac1.markdown(
            f"**{to_local(a.created_at, user.get('timezone')):%d %b, %H:%M}** — {a.event} · {name} (#{a.profile_id})"
            + (f": {a.detail}" if a.detail else "")
        )
        open_profile_button(a.profile_id, label="Open", key=f"dash_open_{a.id}")
else:
    theme.empty_state("No activity recorded yet", "Imports, matches, and task updates will appear here.", icon="🕊️")
