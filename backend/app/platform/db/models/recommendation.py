from __future__ import annotations

from datetime import datetime
from uuid import UUID

from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import Mapped, mapped_column
from uuid6 import uuid7

from app.platform.db.models.base import Base


class Recommendation(Base):
    """Stage 11.2 deterministic recommendation state and AI-copy cache.

    Creation is tied to a 11.1 risk snapshot. Visibility is checked live on read so a cleared current
    risk reason stops showing immediately while the row still preserves audience state and AI provenance.
    """

    __tablename__ = "recommendations"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'closed')", name="ck_recommendations_status"),
        CheckConstraint(
            "close_reason IS NULL OR close_reason IN ('cleared', 'superseded')",
            name="ck_recommendations_close_reason",
        ),
        CheckConstraint(
            "lecturer_state IN ('new', 'acted', 'dismissed')",
            name="ck_recommendations_lecturer_state",
        ),
        CheckConstraint(
            "student_state IN ('new', 'shown', 'dismissed')",
            name="ck_recommendations_student_state",
        ),
        CheckConstraint(
            "ai_status IN ('not_requested', 'queued', 'succeeded', 'failed', 'template_fallback')",
            name="ck_recommendations_ai_status",
        ),
        Index(
            "uq_recommendations_active_student_reason_target",
            "student_id",
            "reason_code",
            "target_key",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
        Index("ix_recommendations_module_student_status", "module_id", "student_id", "status"),
        Index("ix_recommendations_student_status", "student_id", "status"),
        Index("ix_recommendations_ai_status", "ai_status", "updated_at"),
    )

    id: Mapped[UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True, default=uuid7)
    agent_run_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("agent_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    student_risk_snapshot_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("student_risk_snapshots.id", ondelete="CASCADE"),
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
    reason_code: Mapped[str] = mapped_column(Text, nullable=False)
    target_key: Mapped[str] = mapped_column(Text, nullable=False)
    target_label: Mapped[str] = mapped_column(Text, nullable=False)
    deterministic_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    algorithm_version: Mapped[str] = mapped_column(Text, nullable=False)
    input_hash: Mapped[str] = mapped_column(Text, nullable=False)
    source_cutoff_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'active'"))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    close_reason: Mapped[str | None] = mapped_column(Text)
    lecturer_state: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'new'"))
    lecturer_acted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lecturer_dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    student_state: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'new'"))
    student_shown_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    student_dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lecturer_ai_text: Mapped[str | None] = mapped_column(Text)
    student_ai_text: Mapped[str | None] = mapped_column(Text)
    ai_status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'not_requested'"))
    ai_failure_message_sanitized: Mapped[str | None] = mapped_column(Text)
    ai_request_log_id: Mapped[UUID | None] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("ai_request_logs.id", ondelete="SET NULL"),
    )
    ai_model_id: Mapped[str | None] = mapped_column(Text)
    ai_prompt_version: Mapped[str | None] = mapped_column(Text)
    ai_input_hash: Mapped[str | None] = mapped_column(Text)
    ai_generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
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
