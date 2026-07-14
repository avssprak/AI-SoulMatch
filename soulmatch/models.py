"""SQLAlchemy models. Kept portable between SQLite and PostgreSQL:
no dialect-specific column types."""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


PIPELINE_STAGES = [
    "New",
    "AI Extracted",
    "Validated",
    "Minimum Screening",
    "Astrology Completed",
    "Parents Contacted",
    "Interested",
    "Call Scheduled",
    "Video Meeting",
    "Family Meeting",
    "Proposal Sent",
    "Engagement",
    "Marriage",
    "Rejected",
    "Closed",
]

# Presentation-only grouping for stage dropdowns/charts — PIPELINE_STAGES
# above is the stored, ordered list of values (unchanged); this just labels
# runs of it for a shorter dropdown scan. Note the "Outcome" group's member
# named "Engagement" is a specific pipeline stage (the ceremony milestone),
# distinct from this dict's "Outreach" group label — kept as two different
# words on purpose to avoid the confusing double meaning "Engagement" would
# have as both a group label and a stage name in the same dropdown.
PIPELINE_STAGE_GROUPS: dict[str, list[str]] = {
    "Screening": ["New", "AI Extracted", "Validated", "Minimum Screening", "Astrology Completed"],
    "Outreach": ["Parents Contacted", "Interested", "Call Scheduled", "Video Meeting", "Family Meeting", "Proposal Sent"],
    "Outcome": ["Engagement", "Marriage", "Rejected", "Closed"],
}
_STAGE_TO_GROUP = {stage: group for group, stages in PIPELINE_STAGE_GROUPS.items() for stage in stages}


def stage_group_label(stage: str) -> str:
    """'Screening — New' style label for grouped stage dropdowns (see PIPELINE_STAGE_GROUPS)."""
    group = _STAGE_TO_GROUP.get(stage)
    return f"{group} — {stage}" if group else stage


TASK_STATUSES = ["Pending", "Done", "Cancelled"]

STANDARD_TASK_TITLES = [
    "Call parents",
    "Collect horoscope",
    "Upload biodata",
    "Follow up after meeting",
    "Schedule second meeting",
]

# V4-5-1: default due-date offset (days from today) for each one-click task
# template, so "Call parents" etc. can be added with a single click instead
# of also requiring the due date to be picked every time.
TASK_TEMPLATE_DUE_DAYS: dict[str, int] = {
    "Call parents": 2,
    "Collect horoscope": 5,
    "Upload biodata": 3,
    "Follow up after meeting": 7,
    "Schedule second meeting": 7,
}

# V3 SaaS model (see V3_PLAN.md Part 0): one customer-facing role. A Member
# is a parent or individual with a private workspace — every domain row they
# create carries their owner_user_id and no other Member can ever see it.
# Admin is the platform operator (support, customer list, metrics); Admin's
# own domain data is scoped exactly like a Member's. The old staff roles
# (Administrator/Volunteer/Coordinator/Viewer) are migrated in db.py.
ROLES = ["Member", "Admin"]
EDITOR_ROLES = {"Member", "Admin"}

PLANS = ["free", "plus", "pro"]
BILLING_INTERVALS = ["monthly", "annual"]
CURRENCIES = ["INR", "USD"]
# 'active' = paid & in good standing; 'past_due' = payment failed, in the
# V3-3-4 grace window; 'paused' = user-initiated pause (gates as free without
# losing the stored plan); 'free' = no subscription (default).
PLAN_STATUSES = ["active", "past_due", "paused", "free"]


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(100), unique=True)
    # For self-service signups username IS the email; kept as two columns so
    # the pre-V3 admin account (a bare username) keeps working.
    email: Mapped[str | None] = mapped_column(String(255))
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str | None] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(30), default="Member")
    plan: Mapped[str] = mapped_column(String(20), default="free")
    # V3-3-4 lifecycle: plan_status tracks subscription health separately from
    # `plan` itself, so a paused/past_due account can gate as free without
    # losing the tier to restore on resume/payment recovery.
    plan_status: Mapped[str] = mapped_column(String(20), default="free")
    plan_grace_until: Mapped[datetime | None] = mapped_column(DateTime)
    # V3-6-2: IANA zone name (e.g. "America/New_York") for NRI members.
    # Storage stays UTC everywhere else — this only affects display
    # (see soulmatch.timezones).
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Kolkata")
    # V4-4-1: weight (0-100) this member gives the astrology score vs the
    # practical score when blending the two into the Scoreboard's composite —
    # a member preference, not a per-match setting, since it reflects how
    # much stock this family puts in Vedic matching generally.
    astro_weight: Mapped[int] = mapped_column(Integer, default=50)
    # V5-1-1: set once the member finishes (or skips) the first-login
    # onboarding wizard. NULL routes app.py to pages_/00_Welcome.py on every
    # load. Existing accounts are backfilled lazily at that same routing
    # check (any owned profile already => treat as onboarded) rather than in
    # a migration, since "has data" is cheap to check and never wrong.
    onboarded_at: Mapped[datetime | None] = mapped_column(DateTime)
    # V5-6: email verification at signup. NULL = never proved ownership of the
    # address; the gate only applies while soulmatch.mailer.is_configured().
    # Pre-existing accounts are backfilled to "verified" when the column is
    # first added (see db._COLUMN_MIGRATIONS) — never lock out the live cohort.
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime)
    verification_code: Mapped[str | None] = mapped_column(String(16))
    verification_sent_at: Mapped[datetime | None] = mapped_column(DateTime)
    # Wrong entries against the current code (5 locks it, forcing a resend)
    # and sends inside the rolling hour anchored at verification_window_start
    # (3/hour cap on resends).
    verification_attempts: Mapped[int] = mapped_column(Integer, default=0)
    verification_sends: Mapped[int] = mapped_column(Integer, default=0)
    verification_window_start: Mapped[datetime | None] = mapped_column(DateTime)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_login: Mapped[datetime | None] = mapped_column(DateTime)
    # Bumped on logout to invalidate every outstanding persistent-login token for
    # this user (see soulmatch.auth) — a stale token embeds the epoch it was
    # minted under, and validation requires it to still match.
    session_epoch: Mapped[int] = mapped_column(Integer, default=0)


class AiUsage(Base):
    """One row per metered AI action (V3-2) — extraction, AI match
    recommendation, or NL search. Never written for the mock provider."""

    __tablename__ = "ai_usage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    action: Mapped[str] = mapped_column(String(40))  # "extract" | "recommend" | "nl_search"
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    cost_estimate_inr: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Subscription(Base):
    """One row per gateway subscription (V3-3). Created/updated only by
    webhook handlers (soulmatch/payments.py) — never written directly from
    a page, since the gateway is the source of truth for subscription state."""

    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    provider: Mapped[str] = mapped_column(String(20))  # "razorpay" | "stripe"
    provider_sub_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    plan: Mapped[str | None] = mapped_column(String(20))
    interval: Mapped[str | None] = mapped_column(String(20))  # "monthly" | "annual"
    status: Mapped[str] = mapped_column(String(20), default="created")
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class WebhookEvent(Base):
    """Idempotency guard (V3-3-2/3-3-3): one row per (provider, event_id)
    ever processed. A webhook whose (provider, event_id) is already here is
    a duplicate delivery and must be skipped, not re-applied. Uniqueness is
    scoped to the pair, not event_id alone — two different gateways could
    in principle mint the same id string."""

    __tablename__ = "webhook_events"
    __table_args__ = (UniqueConstraint("provider", "event_id", name="uq_webhook_events_provider_event_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(20))
    event_id: Mapped[str] = mapped_column(String(255), index=True)
    received_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class LoginAttempt(Base):
    """Login rate-limiting (V3-5-3): one row per attempt, success or
    failure, keyed by username (not owner_user_id — this exists before
    authentication succeeds, so there is no owner yet). A table rather than
    an in-process counter, deliberately — a Streamlit restart must not
    reset a lockout."""

    __tablename__ = "login_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(100), index=True)
    success: Mapped[bool] = mapped_column(Boolean, default=False)
    attempted_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class RawMessage(Base):
    __tablename__ = "raw_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    source: Mapped[str] = mapped_column(String(50), default="whatsapp_export")
    chat_name: Mapped[str | None] = mapped_column(String(255))
    sender: Mapped[str | None] = mapped_column(String(255))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime)
    content: Mapped[str] = mapped_column(Text)
    media_filename: Mapped[str | None] = mapped_column(String(500))
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)
    processed: Mapped[bool] = mapped_column(Boolean, default=False)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    profiles: Mapped[list["Profile"]] = relationship(back_populates="source_message")


class Profile(Base):
    __tablename__ = "profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Tenant boundary — every read path must filter on this (see soulmatch.tenancy).
    owner_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    # V3-6-1: marks this as the member's own son/daughter rather than a
    # candidate. Deliberately a flag on Profile, not a separate Child
    # entity — a member's own profile IS a Profile row like any other,
    # just one they've tagged. Capped per plan (billing.can_mark_own_child).
    is_own_child: Mapped[bool] = mapped_column(Boolean, default=False)

    # Personal
    full_name: Mapped[str | None] = mapped_column(String(255))
    gender: Mapped[str | None] = mapped_column(String(20))  # "Bride" | "Groom"
    age: Mapped[int | None] = mapped_column(Integer)
    dob: Mapped[date | None] = mapped_column(Date)
    birth_time: Mapped[str | None] = mapped_column(String(20))  # "HH:MM" local
    birth_place: Mapped[str | None] = mapped_column(String(255))

    # Family
    father_name: Mapped[str | None] = mapped_column(String(255))
    mother_name: Mapped[str | None] = mapped_column(String(255))
    siblings: Mapped[str | None] = mapped_column(Text)
    family_details: Mapped[str | None] = mapped_column(Text)

    # Contact
    phone: Mapped[str | None] = mapped_column(String(50))
    whatsapp: Mapped[str | None] = mapped_column(String(50))
    email: Mapped[str | None] = mapped_column(String(255))

    # Religion
    religion: Mapped[str | None] = mapped_column(String(100))
    caste: Mapped[str | None] = mapped_column(String(100))
    sub_caste: Mapped[str | None] = mapped_column(String(100))
    gothram: Mapped[str | None] = mapped_column(String(100))

    # Astrology
    nakshatra: Mapped[str | None] = mapped_column(String(50))
    rashi: Mapped[str | None] = mapped_column(String(50))
    lagna: Mapped[str | None] = mapped_column(String(50))
    horoscope_available: Mapped[bool | None] = mapped_column(Boolean)
    manglik: Mapped[str | None] = mapped_column(String(20))  # Yes / No / Partial / Unknown
    doshas: Mapped[str | None] = mapped_column(Text)

    # Education / career
    qualification: Mapped[str | None] = mapped_column(String(255))
    university: Mapped[str | None] = mapped_column(String(255))
    occupation: Mapped[str | None] = mapped_column(String(255))
    company: Mapped[str | None] = mapped_column(String(255))
    salary: Mapped[str | None] = mapped_column(String(100))

    # Location
    current_location: Mapped[str | None] = mapped_column(String(255))
    native_place: Mapped[str | None] = mapped_column(String(255))
    country: Mapped[str | None] = mapped_column(String(100))

    # Physical / lifestyle
    height_cm: Mapped[float | None] = mapped_column(Float)
    weight_kg: Mapped[float | None] = mapped_column(Float)
    food_preference: Mapped[str | None] = mapped_column(String(50))
    marital_status: Mapped[str | None] = mapped_column(String(50))

    expectations: Mapped[dict | None] = mapped_column(JSON)
    extra: Mapped[dict | None] = mapped_column(JSON)
    notes: Mapped[str | None] = mapped_column(Text)

    stage: Mapped[str] = mapped_column(String(50), default="New")
    source_message_id: Mapped[int | None] = mapped_column(ForeignKey("raw_messages.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    source_message: Mapped[RawMessage | None] = relationship(back_populates="profiles")
    documents: Mapped[list["Document"]] = relationship(back_populates="profile")
    activities: Mapped[list["Activity"]] = relationship(back_populates="profile")
    tasks: Mapped[list["Task"]] = relationship(back_populates="profile")


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    profile_id: Mapped[int | None] = mapped_column(ForeignKey("profiles.id"))
    kind: Mapped[str] = mapped_column(String(50))  # biodata / horoscope / photo / other
    filename: Mapped[str] = mapped_column(String(500))
    path: Mapped[str] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))

    profile: Mapped[Profile | None] = relationship(back_populates="documents")


class MatchResult(Base):
    __tablename__ = "match_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    bride_id: Mapped[int] = mapped_column(ForeignKey("profiles.id"))
    groom_id: Mapped[int] = mapped_column(ForeignKey("profiles.id"))
    practical_score: Mapped[float | None] = mapped_column(Float)
    practical_detail: Mapped[dict | None] = mapped_column(JSON)
    koota_total: Mapped[float | None] = mapped_column(Float)
    koota_detail: Mapped[dict | None] = mapped_column(JSON)
    dosha_detail: Mapped[dict | None] = mapped_column(JSON)
    recommendation: Mapped[str | None] = mapped_column(String(50))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))


class Activity(Base):
    __tablename__ = "activities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id"))
    event: Mapped[str] = mapped_column(String(255))
    detail: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))

    profile: Mapped[Profile] = relationship(back_populates="activities")


class Task(Base):
    """Module 11 — Tasks & Reminders (e.g. 'Call parents', 'Collect horoscope')."""

    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id"))
    title: Mapped[str] = mapped_column(String(255))
    due_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="Pending")
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))

    profile: Mapped[Profile] = relationship(back_populates="tasks")
