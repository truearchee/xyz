from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import Mapped, mapped_column
from uuid6 import uuid7

from app.platform.db.models.base import Base

# Sentinel scope_id for student-global badges. Postgres treats NULLs as DISTINCT in a UNIQUE index, so
# a NULL scope would let a global badge silently duplicate; the all-zeros UUID keeps the unique key
# total (ADR-057). Module-scoped badges store the real module_id.
GLOBAL_SCOPE_ID = UUID("00000000-0000-0000-0000-000000000000")


class StudentBadge(Base):
    """An earned badge (Stage 10).

    Awarded server-side on read when a metric crosses its threshold; **sticky** (never revoked, even if
    the underlying data later changes) and **idempotent** via UNIQUE(student_id, badge_key, scope_type,
    scope_id). The frontend NEVER grants a badge. ``triggering_event_id`` is a bare UUID (provenance,
    not a FK — the spine outlives its sources, like ``student_activity_events.source_id``);
    ``qualified_value`` / ``threshold`` record what value met what bar for debugging/audit.
    """

    __tablename__ = "student_badges"
    __table_args__ = (
        CheckConstraint(
            "scope_type IN ('global', 'module', 'topic', 'section')",
            name="ck_student_badges_scope_type",
        ),
        UniqueConstraint(
            "student_id",
            "badge_key",
            "scope_type",
            "scope_id",
            name="uq_student_badges_student_key_scope",
        ),
        Index("ix_student_badges_student", "student_id"),
    )

    id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        primary_key=True,
        default=uuid7,
    )
    student_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("app_users.id", ondelete="CASCADE"),
        nullable=False,
    )
    badge_key: Mapped[str] = mapped_column(Text, nullable=False)
    scope_type: Mapped[str] = mapped_column(Text, nullable=False)
    scope_id: Mapped[UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    rule_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    qualified_value: Mapped[int | None] = mapped_column(Integer)
    threshold: Mapped[int | None] = mapped_column(Integer)
    triggering_event_id: Mapped[UUID | None] = mapped_column(PostgresUUID(as_uuid=True))
    earned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
