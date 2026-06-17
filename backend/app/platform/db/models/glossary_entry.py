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
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import Mapped, mapped_column
from uuid6 import uuid7

from app.platform.db.models.base import Base


class GlossaryEntry(Base):
    """A personal glossary term (Stage 7a) — per student.

    Two independent axes (spec "subject vs folder"):
      - ``subject_id`` (= course module) is the dedup / cache / practice-scope key, derived from the
        source summary's module on highlight-save and chosen on manual-add. Effectively immutable.
      - ``folder_id`` is a free-form bucket (nullable → resolves to the student's "Unsorted").

    The definition is generated ASYNCHRONOUSLY in the student's ``language`` (snapshot at save). Under
    Stage 7 (decision D3) only ``short_definition`` is AI-populated (the reused BriefSummary markdown
    shape, KaTeX-capable); ``detailed_explanation`` / ``example`` / ``formula_latex`` are RESERVED for
    a later 7.x structured upgrade or manual entry. "Delete" archives (status → archived).

    Dedup is language-INDEPENDENT (``UNIQUE(student_id, subject_id, normalized_term) WHERE active``);
    ``cache_key`` is stored so the async job can fan a single generated definition out to every pending
    entry that shares it (cross-student collapse).
    """

    __tablename__ = "glossary_entries"
    __table_args__ = (
        CheckConstraint(
            "entry_type IN ('term', 'concept', 'formula')",
            name="ck_glossary_entries_entry_type",
        ),
        CheckConstraint(
            "language IN ('en', 'ar', 'zh', 'es', 'fr')",
            name="ck_glossary_entries_language",
        ),
        CheckConstraint(
            "definition_status IN ('pending', 'generated', 'failed', 'manual')",
            name="ck_glossary_entries_definition_status",
        ),
        CheckConstraint(
            "status IN ('active', 'archived')",
            name="ck_glossary_entries_status",
        ),
        # Server-side dedup: one ACTIVE entry per (student, subject, normalized term). Language-independent
        # (first save wins; the entry keeps the language it was generated in). Archived rows do not block.
        Index(
            "uq_glossary_entries_dedup_active",
            "student_id",
            "subject_id",
            "normalized_term",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
        Index(
            "ix_glossary_entries_student_subject_status",
            "student_id",
            "subject_id",
            "status",
        ),
        Index("ix_glossary_entries_student_folder", "student_id", "folder_id"),
        # The async definition job fans a finished definition out via WHERE cache_key=? AND pending.
        Index("ix_glossary_entries_cache_key", "cache_key"),
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
    subject_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("course_modules.id", ondelete="CASCADE"),
        nullable=False,
    )
    folder_id: Mapped[UUID | None] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("glossary_folders.id", ondelete="SET NULL"),
    )
    # Denormalized origin section for a highlight-save (null for manual-add). NOT part of dedup/cache.
    module_section_id: Mapped[UUID | None] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("module_sections.id", ondelete="SET NULL"),
    )
    term: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_term: Mapped[str] = mapped_column(Text, nullable=False)
    normalize_version: Mapped[str] = mapped_column(Text, nullable=False)
    entry_type: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'term'"),
    )
    language: Mapped[str] = mapped_column(Text, nullable=False)
    # The shared definition-cache key (sha256 of normalizeVersion+normalizedTerm+subjectId+entryType+language).
    cache_key: Mapped[str] = mapped_column(Text, nullable=False)
    short_definition: Mapped[str | None] = mapped_column(Text)
    # Reserved (D3) — manual-only / future 7.x structured generation; not AI-populated in Stage 7.
    detailed_explanation: Mapped[str | None] = mapped_column(Text)
    example: Mapped[str | None] = mapped_column(Text)
    formula_latex: Mapped[str | None] = mapped_column(Text)
    definition_status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'pending'"),
    )
    status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'active'"),
    )
    # Provenance (rule 6) — copied from the gateway AIRequestLog row on generation (or from the cache row).
    model_id: Mapped[str | None] = mapped_column(Text)
    prompt_version: Mapped[str | None] = mapped_column(Text)
    prompt_content_hash: Mapped[str | None] = mapped_column(Text)
    backend_used: Mapped[str | None] = mapped_column(Text)
    source_content_hash: Mapped[str | None] = mapped_column(Text)
    ai_request_log_id: Mapped[UUID | None] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("ai_request_logs.id", ondelete="SET NULL"),
    )
    definition_generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
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
