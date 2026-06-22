from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import Mapped, mapped_column
from uuid6 import uuid7

from app.platform.db.models.base import Base


class StudentForecastAdvice(Base):
    """Stage 11.6 grade-forecast advice cache (one row per student/module).

    The advice EXPLAINS Stage 9's deterministic forecast — it never calculates. The deterministic
    template (in ``deterministic_payload``) renders immediately and is the validator-safe fallback; a
    lazy/cached AI phrasing layer fills ``ai_text`` and swaps in when ready. ``input_hash`` keys the AI
    cache: it is reused only while ``ai_input_hash == input_hash`` and ``ai_prompt_version`` matches the
    current prompt version; otherwise it regenerates. Reproducibility lives on the row
    (``algorithm_version`` / ``input_hash`` / ``source_cutoff_at`` / ``forecast_state``).
    """

    __tablename__ = "student_forecast_advice"
    __table_args__ = (
        CheckConstraint(
            "forecast_state IN ('final_no_remaining', 'achieved', 'impossible', "
            "'on_track', 'at_risk', 'requires_high_score')",
            name="ck_student_forecast_advice_forecast_state",
        ),
        CheckConstraint(
            "ai_status IN ('not_requested', 'queued', 'succeeded', 'failed', 'template_fallback')",
            name="ck_student_forecast_advice_ai_status",
        ),
        UniqueConstraint(
            "student_id",
            "module_id",
            name="uq_student_forecast_advice_student_module",
        ),
        Index("ix_student_forecast_advice_ai_status", "ai_status", "updated_at"),
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
    algorithm_version: Mapped[str] = mapped_column(Text, nullable=False)
    input_hash: Mapped[str] = mapped_column(Text, nullable=False)
    source_cutoff_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    forecast_state: Mapped[str] = mapped_column(Text, nullable=False)
    deterministic_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    ai_status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'not_requested'"))
    ai_text: Mapped[str | None] = mapped_column(Text)
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
