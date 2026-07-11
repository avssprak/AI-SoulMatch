"""Engine/session factory. Call init_db() once at app startup."""

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from . import config
from .models import Base

config.ensure_dirs()

engine = create_engine(config.DATABASE_URL, future=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

# (table, column, DDL type) added to models.py after the table already existed
# in deployed databases — Base.metadata.create_all() only creates missing
# tables, not missing columns on existing ones, so these need an explicit
# ALTER TABLE. Safe to run every startup: skipped once the column exists.
_COLUMN_MIGRATIONS = [
    ("users", "session_epoch", "INTEGER DEFAULT 0"),
    ("activities", "created_by_user_id", "INTEGER"),
    ("documents", "created_by_user_id", "INTEGER"),
    ("tasks", "created_by_user_id", "INTEGER"),
    ("match_results", "created_by_user_id", "INTEGER"),
    ("raw_messages", "error", "TEXT"),
]


def _apply_column_migrations() -> None:
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    for table, column, ddl_type in _COLUMN_MIGRATIONS:
        if table not in existing_tables:
            continue  # fresh DB — create_all() above already includes it
        existing_columns = {c["name"] for c in inspector.get_columns(table)}
        if column not in existing_columns:
            with engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}"))


def init_db() -> None:
    Base.metadata.create_all(engine)
    _apply_column_migrations()


def get_session() -> Session:
    return SessionLocal()
