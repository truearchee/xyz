from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from typing import Any

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, Numeric, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import Mapped, mapped_column
from uuid6 import uuid7

from app.platform.db.models.base import Base


class StudentProgressSnapshot(Base):
    __tablename__ = "student_progress_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "student_id",
            "module_id",
            "week_number",
            name="uq_student_progress_snapshots_student_module_week",
        ),
        CheckConstraint("week_number > 0", name="ck_student_progress_snapshots_week"),
        CheckConstraint(
            "standing_points >= 0 AND standing_points <= 100",
            name="ck_student_progress_snapshots_standing",
        ),
        Index(
            "ix_student_progress_snapshots_student_module",
            "student_id",
            "module_id",
            "week_number",
        ),
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
    week_number: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    standing_points: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    source_metrics: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
