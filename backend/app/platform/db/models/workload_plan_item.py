from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from typing import Any

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import Mapped, mapped_column
from uuid6 import uuid7

from app.platform.db.models.base import Base


class WorkloadPlanItem(Base):
    __tablename__ = "workload_plan_items"
    __table_args__ = (
        CheckConstraint("estimate_minutes > 0", name="ck_workload_plan_items_estimate_positive"),
        CheckConstraint("reason IN ('deadline', 'gap')", name="ck_workload_plan_items_reason"),
        CheckConstraint(
            '"window" IS NULL OR "window" IN (\'morning\', \'afternoon\', \'evening\')',
            name="ck_workload_plan_items_window",
        ),
        CheckConstraint("sort_index >= 0", name="ck_workload_plan_items_sort_index"),
        CheckConstraint(
            """
            (
              scheduled_start_at IS NOT NULL
              AND scheduled_end_at IS NOT NULL
              AND scheduled_date IS NOT NULL
              AND "window" IS NOT NULL
              AND scheduled_end_at > scheduled_start_at
            )
            OR
            (
              scheduled_start_at IS NULL
              AND scheduled_end_at IS NULL
              AND scheduled_date IS NULL
              AND "window" IS NULL
              AND tight = true
              AND tight_message IS NOT NULL
            )
            """,
            name="ck_workload_plan_items_schedule_or_tight_residual",
        ),
        Index("ix_workload_plan_items_plan_sort", "workload_plan_id", "sort_index"),
        Index("ix_workload_plan_items_section", "source_section_id"),
    )

    id: Mapped[UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True, default=uuid7)
    workload_plan_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("workload_plans.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_section_id: Mapped[UUID | None] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("module_sections.id", ondelete="SET NULL"),
    )
    task_key: Mapped[str] = mapped_column(Text, nullable=False)
    scheduled_date: Mapped[date | None] = mapped_column(Date)
    window: Mapped[str | None] = mapped_column(Text)
    scheduled_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scheduled_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    label: Mapped[str] = mapped_column(Text, nullable=False)
    estimate_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    source_reason_code: Mapped[str | None] = mapped_column(Text)
    source_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    tight: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    tight_message: Mapped[str | None] = mapped_column(Text)
    sort_index: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
