from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    UniqueConstraint,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PostgresUUID
from sqlalchemy.orm import Mapped, mapped_column
from uuid6 import uuid7

from app.platform.db.models.base import Base


class GeneratedLectureSummary(Base):
    """A successfully generated summary artifact (Patch B).

    Success-only: a row existing means a summary was generated and validated. Failures never
    produce a row here — they live in ``IngestionJob`` + ``AIRequestLog``. Every row carries the
    full provenance chain, including ``ai_request_log_id`` (FK NOT NULL) back to the gateway
    attempt that produced it. The unique constraint includes prompt identity so a new prompt
    version produces a distinct row rather than overwriting history.
    """

    __tablename__ = "generated_lecture_summaries"
    __table_args__ = (
        CheckConstraint(
            "summary_type IN ('brief', 'detailed_study')",
            name="ck_gen_summaries_summary_type",
        ),
        CheckConstraint(
            "backend_used IN ('cerebras', 'nvidia')",
            name="ck_gen_summaries_backend_used",
        ),
        UniqueConstraint(
            "transcript_id",
            "summary_type",
            "source_transcript_checksum",
            "prompt_version",
            "prompt_content_hash",
            "input_hash",
            name="uq_gen_summaries_provenance",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        primary_key=True,
        default=uuid7,
    )
    transcript_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("transcripts.id", ondelete="CASCADE"),
        nullable=False,
    )
    module_section_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("module_sections.id", ondelete="CASCADE"),
        nullable=False,
    )
    summary_type: Mapped[str] = mapped_column(Text, nullable=False)
    content_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    content_schema_version: Mapped[str] = mapped_column(Text, nullable=False)
    model_id: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_version: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    backend_used: Mapped[str] = mapped_column(Text, nullable=False)
    reasoning_level: Mapped[str | None] = mapped_column(Text)
    source_transcript_checksum: Mapped[str] = mapped_column(Text, nullable=False)
    input_hash: Mapped[str] = mapped_column(Text, nullable=False)
    # Option A (F-4.5-50): the transcript was truncated to the char budget before generation (full lectures
    # 408 the provider). Surfaced in the UI ("based on the first portion …") — truncation is never silent.
    truncated: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    source_char_count: Mapped[int | None] = mapped_column(Integer)
    summarized_char_count: Mapped[int | None] = mapped_column(Integer)
    ai_request_log_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("ai_request_logs.id"),
        nullable=False,
    )
    # Provenance: the summary IngestionJob that produced this artifact (4.6 fencing/audit). Nullable,
    # forward-only; ON DELETE SET NULL so deleting the job never deletes the summary.
    created_by_ingestion_job_id: Mapped[UUID | None] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("ingestion_jobs.id", ondelete="SET NULL"),
    )
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
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
