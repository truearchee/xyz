from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PostgresUUID
from sqlalchemy.orm import Mapped, mapped_column
from uuid6 import uuid7

from app.platform.db.models.base import Base

# Source of truth for ck_student_activity_events_event_type. Widened per consuming slice (Stage 5
# emits the two quiz events; Stage 7 adds the two glossary events). The 0030 migration hard-codes the
# matching string; a CI test asserts the live DB CHECK allowed-set == this tuple. A parallel stage
# (Stage 6) that also extends this constraint must union both stages' values at merge — CI is the
# guard (knowledge/steps/findings-stage-07.md).
STUDENT_ACTIVITY_EVENT_TYPES: tuple[str, ...] = (
    "completed_quiz",
    "perfect_quiz_score",
    "glossary_term_saved",
    "glossary_practice_completed",
)
_EVENT_TYPE_IN = ", ".join(f"'{event_type}'" for event_type in STUDENT_ACTIVITY_EVENT_TYPES)


class StudentActivityEvent(Base):
    """The platform activity event spine (Stage 5 §8).

    One immutable row per student action instance. Stage 5 EMITS only ``completed_quiz`` and
    ``perfect_quiz_score``; the CHECK is widened per consuming slice (same pattern 0011 used for
    ``ck_ingestion_jobs_failure_category``). ``source_id`` is the action instance (the quiz attempt id)
    and is deliberately NOT a foreign key — the spine outlives/precedes its sources and is keyed for
    idempotency via ``UNIQUE(event_type, source_id)``. Rows are inserted WITHIN the caller's transaction
    by ``EventRecorder`` (it never commits). No consumer is built in Stage 5 (rule 7).
    """

    __tablename__ = "student_activity_events"
    __table_args__ = (
        CheckConstraint(
            f"event_type IN ({_EVENT_TYPE_IN})",
            name="ck_student_activity_events_event_type",
        ),
        UniqueConstraint(
            "event_type",
            "source_id",
            name="uq_student_activity_events_type_source",
        ),
        Index(
            "ix_student_activity_events_student_type",
            "student_id",
            "event_type",
        ),
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
    module_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("course_modules.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    # The action instance (quiz attempt id). NOT a FK — the spine is keyed for idempotency, not lineage.
    source_id: Mapped[UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    # DeclarativeBase reserves ``.metadata``; map the Python attr ``metadata_json`` to the DB column.
    metadata_json: Mapped[dict | None] = mapped_column("metadata", JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
