from __future__ import annotations

from datetime import datetime
from uuid import UUID

from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import Mapped, mapped_column
from uuid6 import uuid7

from app.platform.db.models.base import Base


class StudentAvailability(Base):
    __tablename__ = "student_availability"
    __table_args__ = (
        UniqueConstraint("student_id", "module_id", name="uq_student_availability_student_module"),
        CheckConstraint(
            "preferred_window IN ('morning', 'afternoon', 'evening', 'no_preference')",
            name="ck_student_availability_preferred_window",
        ),
        CheckConstraint(
            "max_study_minutes_per_day > 0",
            name="ck_student_availability_max_minutes_positive",
        ),
        CheckConstraint("availability_version > 0", name="ck_student_availability_version_positive"),
        Index("ix_student_availability_module_student", "module_id", "student_id"),
    )

    id: Mapped[UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True, default=uuid7)
    student_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("app_users.id", ondelete="CASCADE"),
        nullable=False,
    )
    module_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("course_modules.id", ondelete="CASCADE"),
        nullable=False,
    )
    study_days: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    preferred_window: Mapped[str] = mapped_column(Text, nullable=False)
    max_study_minutes_per_day: Mapped[int] = mapped_column(Integer, nullable=False)
    availability_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

