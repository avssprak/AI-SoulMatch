"""Module 11 — Tasks & Reminders: query helpers over the Task model.

There's no push/email/WhatsApp delivery in this MVP — "reminders" surface as
an overdue/upcoming task board (Tasks page) and Dashboard counters, which a
volunteer checks. See models.Task, TASK_STATUSES, STANDARD_TASK_TITLES.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Task
from .tenancy import owned


def pending_tasks(session: Session, owner_id: int, *, profile_id: int | None = None) -> list[Task]:
    query = owned(select(Task).where(Task.status == "Pending"), Task, owner_id)
    if profile_id is not None:
        query = query.where(Task.profile_id == profile_id)
    return list(session.scalars(query.order_by(Task.due_date.is_(None), Task.due_date)).all())


def overdue_tasks(session: Session, owner_id: int, *, today: date | None = None) -> list[Task]:
    today = today or date.today()
    tasks = pending_tasks(session, owner_id)
    return [t for t in tasks if t.due_date is not None and t.due_date < today]


def upcoming_tasks(session: Session, owner_id: int, *, days: int = 7, today: date | None = None) -> list[Task]:
    """Pending tasks due within the next `days` days (inclusive), not already overdue."""
    today = today or date.today()
    from datetime import timedelta

    horizon = today + timedelta(days=days)
    tasks = pending_tasks(session, owner_id)
    return [t for t in tasks if t.due_date is not None and today <= t.due_date <= horizon]
