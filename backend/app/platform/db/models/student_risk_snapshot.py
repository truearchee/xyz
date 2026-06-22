from __future__ import annotations

from datetime import datetime
from uuid import UUID

from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import Mapped, mapped_column
from uuid6 import uuid7

from app.platform.db.models.base import Base


class StudentRiskSnapshot(Base):
    """Deterministic Stage 11 risk history.

    UI reads compute current risk live; these rows are the scheduled/manual run history and proactive
    layer input. They carry reproducibility fields so a past tier can be audited after thresholds change.
    """

    __tablename__ = "student_risk_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "agent_run_id",
            "student_id",
            "module_id",
            name="uq_student_risk_snapshots_run_student_module",
        ),
        CheckConstraint(
            "risk_tier IN ('on_track', 'watch', 'needs_support')",
            name="ck_student_risk_snapshots_risk_tier",
        ),
        Index(
            "ix_student_risk_snapshots_student_module_computed",
            "student_id",
            "module_id",
            "computed_at",
        ),
        Index("ix_student_risk_snapshots_module_tier", "module_id", "risk_tier"),
    )

    id: Mapped[UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True, default=uuid7)
    agent_run_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("agent_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
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
    risk_tier: Mapped[str] = mapped_column(Text, nullable=False)
    risk_reasons: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
    )
    algorithm_version: Mapped[str] = mapped_column(Text, nullable=False)
    input_hash: Mapped[str] = mapped_column(Text, nullable=False)
    source_cutoff_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
