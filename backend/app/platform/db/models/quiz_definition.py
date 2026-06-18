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


class QuizDefinition(Base):
    """A thin anchor row for one quiz of a module section (Stage 5 lock 2).

    Materialized get-or-create on ``POST start`` only — never on a read. There is NO persisted readiness
    ``status`` (a stored-but-untrusted status is a drift magnet; readiness is computed every time) and NO
    summary pointer (the active summary is resolved live at Start and snapshotted onto the attempt, which
    is supersession-safe). ``quiz_mode`` carries the full reserved vocabulary; Stage 5 uses ``post_class``
    only, enforced one-per-section by the partial-unique index. ``module_id`` is derived from the section's
    ``course_module_id`` by the writer (needed for event emit).
    """

    __tablename__ = "quiz_definitions"
    __table_args__ = (
        CheckConstraint(
            "quiz_mode IN ('post_class', 'recap', 'exam_prep', 'mistakes_bank')",
            name="ck_quiz_definitions_quiz_mode",
        ),
        Index(
            "uq_quiz_definitions_post_class_section",
            "module_section_id",
            unique=True,
            postgresql_where=text("quiz_mode = 'post_class'"),
        ),
        # Stage 6b — shared-definition dedup for the MULTI-SECTION modes (post_class keeps the index
        # above). scope_key = recap: sha256(sorted eligible section ids); exam_prep: str(assessmentScopeId);
        # mistakes_bank (6c): str(moduleId). Identical scope ⇒ ONE shared definition across students.
        Index(
            "uq_quiz_definitions_scope",
            "module_id",
            "quiz_mode",
            "scope_key",
            unique=True,
            postgresql_where=text("quiz_mode IN ('recap', 'exam_prep', 'mistakes_bank')"),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        primary_key=True,
        default=uuid7,
    )
    # Stage 6b: NULLABLE — multi-section modes (recap/exam_prep/mistakes_bank) carry scope in source_scope
    # + scope_key, not a single section. post_class rows still set it (and keep their 0015 partial-unique).
    module_section_id: Mapped[UUID | None] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("module_sections.id", ondelete="CASCADE"),
    )
    module_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("course_modules.id", ondelete="CASCADE"),
        nullable=False,
    )
    quiz_mode: Mapped[str] = mapped_column(Text, nullable=False)
    # Stage 6b multi-section scope: the canonical dedup key (see uq_quiz_definitions_scope) + the exam-prep
    # scope link. NULL for post_class. FK on assessment_scope_id is added in migration 0025; bare UUID here.
    scope_key: Mapped[str | None] = mapped_column(Text)
    assessment_scope_id: Mapped[UUID | None] = mapped_column(PostgresUUID(as_uuid=True))
    question_policy: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("""'{"count": 10, "optionsPerQuestion": 4}'::jsonb"""),
    )
    source_scope: Mapped[dict] = mapped_column(JSONB, nullable=False)
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
