from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PostgresUUID
from sqlalchemy.orm import Mapped, mapped_column
from uuid6 import uuid7

from app.platform.db.models.base import Base


class AssessmentScope(Base):
    """A lecturer-defined exam-prep scope (Stage 6b) — a named span of covered weeks within one module.

    One ``QuizDefinition`` (``quiz_mode='exam_prep'``, ``scope_key=str(assessment_scope_id)``) is shared
    across that module's students for the scope. ``covered_weeks`` resolve to eligible lecture/lab sections
    via the Stage 5.5 week resolver at create/edit and at attempt time. ``status='locked'`` records that the
    scope should not be silently re-resolved once attempts exist (the affordance surfaces in the 6d UI).
    """

    __tablename__ = "assessment_scopes"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'locked')",
            name="ck_assessment_scopes_status",
        ),
        Index("ix_assessment_scopes_module", "module_id"),
    )

    id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        primary_key=True,
        default=uuid7,
    )
    module_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("course_modules.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    covered_weeks: Mapped[list] = mapped_column(JSONB, nullable=False)  # array of week ints
    created_by_user_id: Mapped[UUID | None] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("app_users.id", ondelete="SET NULL"),
    )
    status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'active'"),
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
