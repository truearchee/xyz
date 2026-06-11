from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PostgresUUID
from sqlalchemy.orm import Mapped, mapped_column
from uuid6 import uuid7

from app.platform.db.models.base import Base


class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"
    __table_args__ = (
        CheckConstraint(
            "job_type IN ('parse', 'chunk', 'embed', 'generate_brief_summary', 'generate_detailed_summary')",
            name="ck_ingestion_jobs_job_type",
        ),
        CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed')",
            name="ck_ingestion_jobs_status",
        ),
        CheckConstraint("attempts >= 0", name="ck_ingestion_jobs_attempts"),
        CheckConstraint(
            "failure_category IS NULL OR failure_category IN "
            "('provider_transient', 'rate_limited', 'invalid_output', 'invalid_input', "
            "'provider_config_error', 'provider_auth_error', 'failed')",
            name="ck_ingestion_jobs_failure_category",
        ),
        Index("uq_ingestion_jobs_idempotency_key", "idempotency_key", unique=True),
        Index("ix_ingestion_jobs_transcript_job_type", "transcript_id", "job_type"),
        Index(
            "ingestion_jobs_one_active_embed_per_transcript",
            "transcript_id",
            "job_type",
            unique=True,
            postgresql_where=text(
                "job_type = 'embed' AND status IN ('queued', 'running')"
            ),
        ),
        Index(
            "ingestion_jobs_one_active_summary_per_transcript",
            "transcript_id",
            "job_type",
            unique=True,
            postgresql_where=text(
                "job_type IN ('generate_brief_summary', 'generate_detailed_summary') "
                "AND status IN ('queued', 'running')"
            ),
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
    job_type: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'queued'"),
    )
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    processor_version: Mapped[str | None] = mapped_column(Text)
    result_metadata: Mapped[dict | None] = mapped_column(JSONB)
    attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )
    error_message: Mapped[str | None] = mapped_column(Text)
    failure_category: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
