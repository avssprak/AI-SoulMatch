from datetime import date

import pandas as pd
import streamlit as st
from sqlalchemy import select

from soulmatch import auth
from soulmatch.db import get_session
from soulmatch.models import TASK_STATUSES, Activity, Profile, Task, utcnow
from soulmatch.tasks import overdue_tasks, upcoming_tasks

current_user = auth.require_login()
can_write = auth.can_edit(current_user["role"])

st.title("✅ Tasks & Reminders")
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
overdue_only = st.checkbox("Overdue only", value=False)

with get_session() as session:
    query = select(Task)
    if status_filter:
        query = query.where(Task.status.in_(status_filter))
    tasks = session.scalars(query.order_by(Task.due_date.is_(None), Task.due_date)).all()

    if overdue_only:
        today = date.today()
        tasks = [t for t in tasks if t.status == "Pending" and t.due_date and t.due_date < today]

    if not tasks:
        st.info("No tasks match these filters.")
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
        df = pd.DataFrame(rows).drop(columns=["id"])
        st.dataframe(df, width="stretch", hide_index=True)

        pending_shown = [t for t in tasks if t.status == "Pending"]
        if can_write and pending_shown:
            st.subheader("Mark task complete")
            task_id = st.selectbox(
                "Task", [t.id for t in pending_shown],
                format_func=lambda tid: next(
                    f"#{t.profile_id} — {t.title} (due {t.due_date or 'no date'})"
                    for t in pending_shown if t.id == tid
                ),
            )
            col1, col2 = st.columns(2)
            if col1.button("Mark Done", type="primary"):
                task = session.get(Task, task_id)
                task.status = "Done"
                task.completed_at = utcnow()
                session.add(Activity(profile_id=task.profile_id, event="Task completed", detail=task.title))
                session.commit()
                st.rerun()
            if col2.button("Cancel Task"):
                task = session.get(Task, task_id)
                task.status = "Cancelled"
                session.commit()
                st.rerun()
