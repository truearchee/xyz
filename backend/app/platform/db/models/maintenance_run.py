from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PostgresUUID
from sqlalchemy.orm import Mapped, mapped_column
from uuid6 import uuid7

from app.platform.db.models.base import Base


class MaintenanceRun(Base):
    """Observability record for one reaper / reconciliation execution (Stage 4.6c, ADR-46-C/D).

    Every recovery run writes a row here — this is what Stage 12 verifies recovery from (queryable, not a
    log scavenger hunt). A run that cannot take its singleton advisory lock is a no-op and writes NO row
    (it is not a run).
    """

    __tablename__ = "maintenance_runs"
    __table_args__ = (
        CheckConstraint(
            "run_type IN ('stuck_row_reaper', 'storage_reconciliation')",
            name="ck_maintenance_runs_run_type",
        ),
        CheckConstraint(
            "mode IN ('report_only', 'cleanup')",
            name="ck_maintenance_runs_mode",
        ),
        CheckConstraint(
            "status IN ('running', 'completed', 'failed')",
            name="ck_maintenance_runs_status",
        ),
        Index(
            "ix_maintenance_runs_run_type_started_at",
            "run_type",
            "started_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        primary_key=True,
        default=uuid7,
    )
    run_type: Mapped[str] = mapped_column(Text, nullable=False)
    mode: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'running'"),
    )
    triggered_by_user_id: Mapped[UUID | None] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("app_users.id"),
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    summary_json: Mapped[dict | None] = mapped_column(JSONB)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
