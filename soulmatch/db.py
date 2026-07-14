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
    # V3 multi-tenancy (see V3_PLAN.md Sprint V3-1)
    ("users", "email", "VARCHAR(255)"),
    ("users", "plan", "VARCHAR(20) DEFAULT 'free'"),
    ("raw_messages", "owner_user_id", "INTEGER"),
    ("profiles", "owner_user_id", "INTEGER"),
    ("documents", "owner_user_id", "INTEGER"),
    ("match_results", "owner_user_id", "INTEGER"),
    ("activities", "owner_user_id", "INTEGER"),
    ("tasks", "owner_user_id", "INTEGER"),
    # V3-3 billing lifecycle (see V3_PLAN.md Sprint V3-3)
    ("users", "plan_status", "VARCHAR(20) DEFAULT 'free'"),
    ("users", "plan_grace_until", "DATETIME"),
    # V3-6 NRI polish & "my children" (see V3_PLAN.md Sprint V3-6)
    ("profiles", "is_own_child", "BOOLEAN DEFAULT 0"),
    ("users", "timezone", "VARCHAR(64) DEFAULT 'Asia/Kolkata'"),
    # V4-4-1 composite Scoreboard weight (see V4_PLAN.md Sprint V4-4)
    ("users", "astro_weight", "INTEGER DEFAULT 50"),
    # V5-1-1 first-login onboarding wizard (see V5_PLAN.md Sprint V5-1)
    ("users", "onboarded_at", "DATETIME"),
    # V5-6 email verification at signup (see V5_PLAN.md Sprint V5-6)
    ("users", "email_verified_at", "DATETIME"),
    ("users", "verification_code", "VARCHAR(16)"),
    ("users", "verification_sent_at", "DATETIME"),
    ("users", "verification_attempts", "INTEGER DEFAULT 0"),
    ("users", "verification_sends", "INTEGER DEFAULT 0"),
    ("users", "verification_window_start", "DATETIME"),
]

# Run once, immediately after the named column is first ADDed — i.e. only on
# databases that predate the column. Fresh DBs (create_all) never run these.
_COLUMN_BACKFILLS = {
    # V5-6: accounts that existed before verification shipped are trusted
    # as-is — the gate must never lock out the live cohort.
    ("users", "email_verified_at"): "UPDATE users SET email_verified_at = CURRENT_TIMESTAMP",
}

_TENANT_TABLES = ["raw_messages", "profiles", "documents", "match_results", "activities", "tasks"]


def _apply_tenancy_migration() -> None:
    """One-time V3 data migration, safe to run every startup.

    Role collapse: Administrator -> Admin; Volunteer/Coordinator/Viewer ->
    Member. Ownership backfill: every pre-V3 row belonged to the shared staff
    workspace, so ALL of it goes to the operator (Admin) account — not to
    created_by_user_id — because splitting a formerly shared pool by creator
    would scatter one coherent dataset across newly-privatized accounts and
    orphan cross-references (e.g. a match result whose bride now lives in
    another tenant). Demoted staff users start with an empty workspace.
    """
    with engine.begin() as conn:
        conn.execute(text("UPDATE users SET role='Admin' WHERE role='Administrator'"))
        conn.execute(text(
            "UPDATE users SET role='Member' WHERE role IN ('Volunteer','Coordinator','Viewer')"
        ))
        conn.execute(text("UPDATE users SET plan='free' WHERE plan IS NULL"))
        admin_id = conn.execute(text(
            "SELECT id FROM users WHERE role='Admin' ORDER BY id LIMIT 1"
        )).scalar()
        if admin_id is None:
            return  # empty DB — bootstrap admin not created yet; nothing to backfill
        for table in _TENANT_TABLES:
            conn.execute(
                text(f"UPDATE {table} SET owner_user_id = :admin WHERE owner_user_id IS NULL"),  # noqa: S608 — table names from fixed list
                {"admin": admin_id},
            )


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
                backfill = _COLUMN_BACKFILLS.get((table, column))
                if backfill:
                    conn.execute(text(backfill))


def init_db() -> None:
    Base.metadata.create_all(engine)
    _apply_column_migrations()
    _apply_tenancy_migration()


def get_session() -> Session:
    return SessionLocal()
