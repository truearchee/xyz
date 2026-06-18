from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Numeric, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import Mapped, mapped_column
from uuid6 import uuid7

from app.platform.db.models.base import Base


class StudentGradeRecord(Base):
    __tablename__ = "student_grade_records"
    __table_args__ = (
        UniqueConstraint(
            "student_id",
            "grade_component_id",
            name="uq_student_grade_records_student_component",
        ),
        CheckConstraint(
            "percentage_score >= 0 AND percentage_score <= 100",
            name="ck_student_grade_records_percentage",
        ),
        CheckConstraint(
            "source IN ('seed', 'e2e', 'import')",
            name="ck_student_grade_records_source",
        ),
        Index("ix_student_grade_records_student_component", "student_id", "grade_component_id"),
    )

    id: Mapped[UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True, default=uuid7)
    student_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("app_users.id", ondelete="CASCADE"),
        nullable=False,
    )
    grade_component_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("grade_components.id", ondelete="CASCADE"),
        nullable=False,
    )
    percentage_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    graded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    source: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'seed'"))
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
