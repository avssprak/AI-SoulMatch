from datetime import date

import pandas as pd
import streamlit as st
from sqlalchemy import select

from soulmatch import auth, theme
from soulmatch.db import get_session
from soulmatch.models import TASK_STATUSES, Activity, Profile, Task, utcnow
from soulmatch.nav import TASKS_OVERDUE_PREF_KEY, open_profile_button
from soulmatch.tasks import overdue_tasks, upcoming_tasks

current_user = auth.require_login()
can_write = auth.can_edit(current_user["role"])

theme.page_header("Tasks & Reminders", "Follow-ups for every introduction — nothing slips through.")
if not can_write:
    st.caption("Your account has read-only (Viewer) access.")

with get_session() as session:
    all_pending = session.scalars(select(Task).where(Task.status == "Pending")).all()
    overdue = overdue_tasks(session)
    upcoming = upcoming_tasks(session)

c1, c2, c3 = st.columns(3)
c1.metric("Pending Tasks", len(all_pending))
c2.metric("Overdue", len(overdue))
c3.metric("Due in 7 Days", len(upcoming))

st.divider()

status_filter = st.multiselect("Status", TASK_STATUSES, default=["Pending"])
overdue_only = st.checkbox("Overdue only", value=st.session_state.pop(TASKS_OVERDUE_PREF_KEY, False))

with get_session() as session:
    query = select(Task)
    if status_filter:
        query = query.where(Task.status.in_(status_filter))
    tasks = session.scalars(query.order_by(Task.due_date.is_(None), Task.due_date)).all()

    if overdue_only:
        today = date.today()
        tasks = [t for t in tasks if t.status == "Pending" and t.due_date and t.due_date < today]

    if not tasks:
        theme.empty_state("No tasks match these filters", "Adjust the status filter above, or create tasks from a profile's detail view.", icon="✅")
    else:
        profile_ids = {t.profile_id for t in tasks}
        profiles = {p.id: p for p in session.scalars(select(Profile).where(Profile.id.in_(profile_ids))).all()}

        today = date.today()
        rows = []
        for t in tasks:
            profile = profiles.get(t.profile_id)
            overdue_flag = t.status == "Pending" and t.due_date is not None and t.due_date < today
            rows.append({
                "id": t.id,
                "Profile": f"#{t.profile_id} {profile.full_name if profile else 'Unknown'}",
                "Task": t.title,
                "Due": t.due_date.isoformat() if t.due_date else "—",
                "Status": ("⚠️ " if overdue_flag else "") + t.status,
            })
        df = pd.DataFrame(rows)
        task_event = st.dataframe(
            df.drop(columns=["id"]), width="stretch", hide_index=True,
            on_select="rerun", selection_mode="single-row", key="tasks_table",
        )
        selected_task_rows = task_event.selection.rows if task_event and task_event.selection else []
        row_selected_task_id = int(df.iloc[selected_task_rows[0]]["id"]) if selected_task_rows else None
        if row_selected_task_id is not None:
            st.caption("Row selected — jump to \"Mark task complete\" below.")
            selected_task = session.get(Task, row_selected_task_id)
            if selected_task and profiles.get(selected_task.profile_id):
                open_profile_button(selected_task.profile_id)

        pending_shown = [t for t in tasks if t.status == "Pending"]
        if can_write and pending_shown:
            theme.section("Mark task complete")
            options = [t.id for t in pending_shown]
            default_index = options.index(row_selected_task_id) if row_selected_task_id in options else 0
            task_id = st.selectbox(
                "Task", options,
                index=default_index,
                format_func=lambda tid: next(
                    f"#{t.profile_id} — {t.title} (due {t.due_date or 'no date'})"
                    for t in pending_shown if t.id == tid
                ),
                key=f"task_select_{row_selected_task_id}",
            )
            with st.container(horizontal=True):
                if st.button("Mark Done", type="primary"):
                    task = session.get(Task, task_id)
                    task.status = "Done"
                    task.completed_at = utcnow()
                    session.add(Activity(profile_id=task.profile_id, event="Task completed", detail=task.title,
                                          created_by_user_id=current_user["id"]))
                    session.commit()
                    st.rerun()
                if st.button("Cancel Task"):
                    task = session.get(Task, task_id)
                    task.status = "Cancelled"
                    session.commit()
                    st.rerun()
