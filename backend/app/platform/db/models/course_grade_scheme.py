from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, Numeric, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import Mapped, mapped_column
from uuid6 import uuid7

from app.platform.db.models.base import Base


class CourseGradeScheme(Base):
    __tablename__ = "course_grade_schemes"
    __table_args__ = (
        UniqueConstraint("module_id", name="uq_course_grade_schemes_module"),
        CheckConstraint(
            "on_track_max >= 0 AND on_track_max <= 100",
            name="ck_course_grade_schemes_on_track_max",
        ),
        CheckConstraint(
            "at_risk_max >= on_track_max AND at_risk_max <= 100",
            name="ck_course_grade_schemes_at_risk_max",
        ),
        CheckConstraint("benchmark_min_cohort >= 2", name="ck_course_grade_schemes_benchmark_min"),
    )

    id: Mapped[UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True, default=uuid7)
    module_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("course_modules.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    on_track_max: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        server_default=text("70.00"),
    )
    at_risk_max: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        server_default=text("85.00"),
    )
    benchmark_min_cohort: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("5"),
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
