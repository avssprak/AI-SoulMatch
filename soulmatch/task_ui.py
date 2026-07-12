"""V4-5-1 — shared "quick add a task" UI: one-click templates (title +
default due date, from TASK_TEMPLATE_DUE_DAYS) plus a custom/free-form
fallback. Shared by the Follow-Ups page and the Candidates profile drawer so
there's one place that creates a Task + logs the "Task added" Activity, not
two copies drifting apart.
"""

from __future__ import annotations

from datetime import date, timedelta

import streamlit as st
from sqlalchemy.orm import Session

from .models import STANDARD_TASK_TITLES, TASK_TEMPLATE_DUE_DAYS, Activity, Task
from .ui import flash


def render_task_quick_add(
    session: Session, owner: int, current_user: dict, profile_id: int, *, key_prefix: str,
) -> None:
    """Render one-click template buttons + a custom-task expander for
    `profile_id`. Each template button creates the Task immediately (no form
    submit needed) with its default due date."""
    st.caption("Quick add a follow-up:")
    cols = st.columns(len(STANDARD_TASK_TITLES))
    for i, title in enumerate(STANDARD_TASK_TITLES):
        if cols[i].button(title, key=f"{key_prefix}_tpl_{i}_{profile_id}"):
            due = date.today() + timedelta(days=TASK_TEMPLATE_DUE_DAYS.get(title, 3))
            session.add(Task(
                profile_id=profile_id, owner_user_id=owner, title=title, due_date=due,
                created_by_user_id=current_user["id"],
            ))
            session.add(Activity(
                profile_id=profile_id, owner_user_id=owner, event="Task added", detail=title,
                created_by_user_id=current_user["id"],
            ))
            session.commit()
            flash(f"Added '{title}', due {due:%d %b}.")
            st.rerun()

    with st.expander("+ Custom task"):
        with st.form(f"{key_prefix}_custom_task_{profile_id}", clear_on_submit=True):
            title = st.text_input("Task title")
            due = st.date_input("Due date", value=None)
            if st.form_submit_button("Add task"):
                if not title.strip():
                    st.warning("Enter a task title.")
                else:
                    session.add(Task(
                        profile_id=profile_id, owner_user_id=owner, title=title.strip(), due_date=due,
                        created_by_user_id=current_user["id"],
                    ))
                    session.add(Activity(
                        profile_id=profile_id, owner_user_id=owner, event="Task added", detail=title.strip(),
                        created_by_user_id=current_user["id"],
                    ))
                    session.commit()
                    st.rerun()
