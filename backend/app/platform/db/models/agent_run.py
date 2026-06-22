from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import Mapped, mapped_column
from uuid6 import uuid7

from app.platform.db.models.base import Base


class AgentRun(Base):
    """Recorded execution of the Stage 11 deterministic agent.

    The run ledger is the scheduler's idempotency boundary. A duplicate trigger with the same
    ``idempotency_key`` returns the existing row rather than recomputing or creating duplicate snapshots.
    """

    __tablename__ = "agent_runs"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_agent_runs_idempotency_key"),
        CheckConstraint(
            "trigger_type IN ('scheduled_daily', 'pre_deadline', 'manual_admin')",
            name="ck_agent_runs_trigger_type",
        ),
        CheckConstraint(
            "scope_type IN ('all', 'module', 'student', 'deadline')",
            name="ck_agent_runs_scope_type",
        ),
        CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed')",
            name="ck_agent_runs_status",
        ),
        CheckConstraint("snapshot_count >= 0", name="ck_agent_runs_snapshot_count"),
        CheckConstraint("recommendation_count >= 0", name="ck_agent_runs_recommendation_count"),
        CheckConstraint("plan_count >= 0", name="ck_agent_runs_plan_count"),
        Index("ix_agent_runs_status_scheduled_for", "status", "scheduled_for"),
        Index("ix_agent_runs_trigger_type", "trigger_type"),
    )

    id: Mapped[UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True, default=uuid7)
    trigger_type: Mapped[str] = mapped_column(Text, nullable=False)
    scope_type: Mapped[str] = mapped_column(Text, nullable=False)
    scope_id: Mapped[UUID | None] = mapped_column(PostgresUUID(as_uuid=True))
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    triggered_by_user_id: Mapped[UUID | None] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("app_users.id", ondelete="SET NULL"),
    )
    algorithm_version: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'queued'"))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    snapshot_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    recommendation_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    plan_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    failure_message_sanitized: Mapped[str | None] = mapped_column(Text)
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
