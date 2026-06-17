from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from typing import Any

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import Mapped, mapped_column
from uuid6 import uuid7

from app.platform.db.models.base import Base


class CourseModule(Base):
    __tablename__ = "course_modules"

    id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        primary_key=True,
        default=uuid7,
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    owner_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("app_users.id"),
        nullable=False,
    )
    timezone: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'UTC'"),
    )
    starts_on: Mapped[date | None] = mapped_column(Date)
    ends_on: Mapped[date | None] = mapped_column(Date)
    # Stage 5.5 schedule provenance (D10): creation-time config, displayed/readable
    # but never edited or regenerated. NULL = no schedule configured (legacy/ORM-direct
    # rows); the schedule-driven create path always populates all three.
    week_start_day: Mapped[str | None] = mapped_column(Text)
    session_pattern: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    quiz_day: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("true"),
    )
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
