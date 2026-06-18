from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Numeric, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import Mapped, mapped_column
from uuid6 import uuid7

from app.platform.db.models.base import Base


class StudentTopicMasterySnapshot(Base):
    __tablename__ = "student_topic_mastery_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "student_id",
            "module_id",
            "module_section_id",
            name="uq_student_topic_mastery_student_module_section",
        ),
        CheckConstraint(
            "mastery_percentage >= 0 AND mastery_percentage <= 100",
            name="ck_student_topic_mastery_percentage",
        ),
        CheckConstraint(
            "status_label IN ('strong', 'on_track', 'needs_attention')",
            name="ck_student_topic_mastery_status_label",
        ),
        Index("ix_student_topic_mastery_student_module", "student_id", "module_id"),
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
    module_section_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("module_sections.id", ondelete="CASCADE"),
        nullable=False,
    )
    mastery_percentage: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    status_label: Mapped[str] = mapped_column(Text, nullable=False)
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
