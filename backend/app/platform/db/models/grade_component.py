from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import Mapped, mapped_column
from uuid6 import uuid7

from app.platform.db.models.base import Base


class GradeComponent(Base):
    __tablename__ = "grade_components"
    __table_args__ = (
        UniqueConstraint("scheme_id", "sort_order", name="uq_grade_components_scheme_order"),
        CheckConstraint("weight > 0 AND weight <= 1", name="ck_grade_components_weight"),
        CheckConstraint(
            "component_kind IN ('quiz', 'assignment', 'exam', 'lab', 'coursework')",
            name="ck_grade_components_kind",
        ),
        Index("ix_grade_components_scheme", "scheme_id"),
    )

    id: Mapped[UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True, default=uuid7)
    scheme_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("course_grade_schemes.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    weight: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)
    component_kind: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'coursework'"),
    )
    module_section_id: Mapped[UUID | None] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("module_sections.id", ondelete="SET NULL"),
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
