from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import Mapped, mapped_column
from uuid6 import uuid7

from app.platform.db.models.base import Base


class GradeBoundary(Base):
    __tablename__ = "grade_boundaries"
    __table_args__ = (
        UniqueConstraint("scheme_id", "letter_grade", name="uq_grade_boundaries_scheme_letter"),
        UniqueConstraint("scheme_id", "sort_order", name="uq_grade_boundaries_scheme_order"),
        CheckConstraint("lower_bound >= 0 AND lower_bound <= 100", name="ck_grade_boundaries_lower"),
        Index("ix_grade_boundaries_scheme_lower", "scheme_id", "lower_bound"),
    )

    id: Mapped[UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True, default=uuid7)
    scheme_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("course_grade_schemes.id", ondelete="CASCADE"),
        nullable=False,
    )
    letter_grade: Mapped[str] = mapped_column(Text, nullable=False)
    lower_bound: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
