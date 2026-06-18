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


class SectionQuestionPool(Base):
    """The durable, reusable question store (Stage 6a, Layer 1 — capacity ADR).

    Questions are AI-generated ONCE per ``(module_section_id, model, prompt_version)`` from the section's
    detailed summary and reused for every student / mode / attempt that touches the section (rule 15: one
    call per generation, never per attempt). The two partial-unique indexes are the concurrency contract:
    at most one ``ready`` pool per key (the live pool) and at most one ``generating`` pool per key (the
    thundering-herd lock — the migration-0007 ``ingestion_jobs`` pattern). Staleness is detected against
    ``source_summary_content_hash`` (sha256 of the detailed summary's ``content_json``); a stale pool is
    transitioned ``ready → superseded`` and regenerated (the 4.6 atomic-swap applied to pools), which frees
    the ready slot. Snapshot-at-assembly means superseding a pool NEVER mutates a started attempt.
    """

    __tablename__ = "section_question_pools"
    __table_args__ = (
        CheckConstraint(
            "status IN ('generating', 'ready', 'failed', 'superseded')",
            name="ck_section_question_pools_status",
        ),
        CheckConstraint(
            "failure_category IS NULL OR failure_category IN "
            "('provider_error', 'invalid_output', 'crashed')",
            name="ck_section_question_pools_failure_category",
        ),
        Index(
            "ix_section_question_pools_section",
            "module_section_id",
        ),
        # The live pool: at most one ready pool per (section, model, promptVersion).
        Index(
            "uq_section_question_pools_one_ready",
            "module_section_id",
            "model",
            "prompt_version",
            unique=True,
            postgresql_where=text("status = 'ready'"),
        ),
        # The herd lock: at most one in-flight generation per (section, model, promptVersion).
        Index(
            "uq_section_question_pools_one_generating",
            "module_section_id",
            "model",
            "prompt_version",
            unique=True,
            postgresql_where=text("status = 'generating'"),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        primary_key=True,
        default=uuid7,
    )
    module_section_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("module_sections.id", ondelete="CASCADE"),
        nullable=False,
    )
    model: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_version: Mapped[str] = mapped_column(Text, nullable=False)
    # The detailed-summary this pool was built from + the staleness signal (sha256 of content_json).
    source_summary_id: Mapped[UUID | None] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("generated_lecture_summaries.id", ondelete="SET NULL"),
    )
    source_summary_content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    ai_request_log_id: Mapped[UUID | None] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("ai_request_logs.id", ondelete="SET NULL"),
    )
    status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'generating'"),
    )
    failure_category: Mapped[str | None] = mapped_column(Text)
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
