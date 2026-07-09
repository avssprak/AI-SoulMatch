from datetime import date, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from soulmatch.models import Base, Profile, Task
from soulmatch.tasks import overdue_tasks, pending_tasks, upcoming_tasks


def _memory_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _seed_profile(session: Session) -> int:
    p = Profile(full_name="Test Person", gender="Bride")
    session.add(p)
    session.commit()
    return p.id


def test_pending_tasks_excludes_done_and_cancelled():
    session = _memory_session()
    pid = _seed_profile(session)
    session.add_all([
        Task(profile_id=pid, title="Call parents", status="Pending"),
        Task(profile_id=pid, title="Collect horoscope", status="Done"),
        Task(profile_id=pid, title="Upload biodata", status="Cancelled"),
    ])
    session.commit()

    pending = pending_tasks(session)
    assert len(pending) == 1
    assert pending[0].title == "Call parents"


def test_pending_tasks_scoped_to_profile():
    session = _memory_session()
    pid1 = _seed_profile(session)
    pid2 = _seed_profile(session)
    session.add_all([
        Task(profile_id=pid1, title="Task A", status="Pending"),
        Task(profile_id=pid2, title="Task B", status="Pending"),
    ])
    session.commit()

    assert len(pending_tasks(session, profile_id=pid1)) == 1
    assert pending_tasks(session, profile_id=pid1)[0].title == "Task A"


def test_overdue_tasks():
    session = _memory_session()
    pid = _seed_profile(session)
    today = date(2026, 7, 9)
    session.add_all([
        Task(profile_id=pid, title="Past due", status="Pending", due_date=today - timedelta(days=2)),
        Task(profile_id=pid, title="Due today", status="Pending", due_date=today),
        Task(profile_id=pid, title="Future", status="Pending", due_date=today + timedelta(days=5)),
        Task(profile_id=pid, title="No date", status="Pending"),
        Task(profile_id=pid, title="Was overdue but done", status="Done", due_date=today - timedelta(days=10)),
    ])
    session.commit()

    overdue = overdue_tasks(session, today=today)
    assert [t.title for t in overdue] == ["Past due"]


def test_upcoming_tasks_window():
    session = _memory_session()
    pid = _seed_profile(session)
    today = date(2026, 7, 9)
    session.add_all([
        Task(profile_id=pid, title="Today", status="Pending", due_date=today),
        Task(profile_id=pid, title="In 3 days", status="Pending", due_date=today + timedelta(days=3)),
        Task(profile_id=pid, title="In 7 days", status="Pending", due_date=today + timedelta(days=7)),
        Task(profile_id=pid, title="In 10 days", status="Pending", due_date=today + timedelta(days=10)),
        Task(profile_id=pid, title="Overdue", status="Pending", due_date=today - timedelta(days=1)),
    ])
    session.commit()

    upcoming = upcoming_tasks(session, days=7, today=today)
    titles = {t.title for t in upcoming}
    assert titles == {"Today", "In 3 days", "In 7 days"}


def test_task_completion_lifecycle():
    session = _memory_session()
    pid = _seed_profile(session)
    task = Task(profile_id=pid, title="Call parents", status="Pending")
    session.add(task)
    session.commit()

    assert task.completed_at is None
    task.status = "Done"
    from soulmatch.models import utcnow
    task.completed_at = utcnow()
    session.commit()

    reloaded = session.get(Task, task.id)
    assert reloaded.status == "Done"
    assert reloaded.completed_at is not None
    assert reloaded not in pending_tasks(session)
