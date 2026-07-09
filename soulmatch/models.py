"""SQLAlchemy models. Kept portable between SQLite and PostgreSQL:
no dialect-specific column types."""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text
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

TASK_STATUSES = ["Pending", "Done", "Cancelled"]

STANDARD_TASK_TITLES = [
    "Call parents",
    "Collect horoscope",
    "Upload biodata",
    "Follow up after meeting",
    "Schedule second meeting",
]


class RawMessage(Base):
    __tablename__ = "raw_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(50), default="whatsapp_export")
    chat_name: Mapped[str | None] = mapped_column(String(255))
    sender: Mapped[str | None] = mapped_column(String(255))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime)
    content: Mapped[str] = mapped_column(Text)
    media_filename: Mapped[str | None] = mapped_column(String(500))
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)
    processed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    profiles: Mapped[list["Profile"]] = relationship(back_populates="source_message")


class Profile(Base):
    __tablename__ = "profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

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
    profile_id: Mapped[int | None] = mapped_column(ForeignKey("profiles.id"))
    kind: Mapped[str] = mapped_column(String(50))  # biodata / horoscope / photo / other
    filename: Mapped[str] = mapped_column(String(500))
    path: Mapped[str] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    profile: Mapped[Profile | None] = relationship(back_populates="documents")


class MatchResult(Base):
    __tablename__ = "match_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
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


class Activity(Base):
    __tablename__ = "activities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id"))
    event: Mapped[str] = mapped_column(String(255))
    detail: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    profile: Mapped[Profile] = relationship(back_populates="activities")


class Task(Base):
    """Module 11 — Tasks & Reminders (e.g. 'Call parents', 'Collect horoscope')."""

    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id"))
    title: Mapped[str] = mapped_column(String(255))
    due_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="Pending")
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)

    profile: Mapped[Profile] = relationship(back_populates="tasks")
