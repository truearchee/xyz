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
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PostgresUUID
from sqlalchemy.orm import Mapped, mapped_column
from uuid6 import uuid7

from app.platform.db.models.base import Base


class AIRequestLog(Base):
    """One row per ``LLMGateway.complete()`` attempt (gateway-attempt log, Patch A).

    The row is opened (status='running') BEFORE ``ContextBuilder.fit`` so that an
    ``invalid_input`` (over-context, detected before transport) is still loggable.
    Provider-specific fields are therefore nullable: a gateway attempt may terminate
    before any HTTP call is made. Never stores raw transcript text or full prompts —
    hashes and metadata only.
    """

    __tablename__ = "ai_request_logs"
    __table_args__ = (
        CheckConstraint("attempt_number >= 1", name="ck_ai_request_logs_attempt_number"),
        CheckConstraint(
            "feature IN ('summary_brief', 'summary_detailed', "
            "'detailed_summary_map', 'detailed_summary_reduce')",
            name="ck_ai_request_logs_feature",
        ),
        CheckConstraint(
            "backend_used IS NULL OR backend_used IN ('cerebras', 'nvidia')",
            name="ck_ai_request_logs_backend_used",
        ),
        CheckConstraint(
            "status IN ('running', 'succeeded', 'rate_limited', 'provider_transient', "
            "'invalid_output', 'invalid_input', 'provider_config_error', "
            "'provider_auth_error', 'failed')",
            name="ck_ai_request_logs_status",
        ),
        CheckConstraint(
            "backend_route_source IS NULL OR "
            "backend_route_source IN ('requested', 'provider_echoed')",
            name="ck_ai_request_logs_backend_route_source",
        ),
        Index("ix_ai_request_logs_feature_created_at", "feature", "created_at"),
        Index("ix_ai_request_logs_ingestion_job_id", "ingestion_job_id"),
    )

    id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        primary_key=True,
        default=uuid7,
    )
    ingestion_job_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("ingestion_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    attempt_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("1"),
    )
    feature: Mapped[str] = mapped_column(Text, nullable=False)
    # Prompt identity — known at open() (post-render). model_id is the declared model;
    # it is updated if ContextBuilder selects a fallback route.
    model_id: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_version: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    rendered_prompt_hash: Mapped[str] = mapped_column(Text, nullable=False)
    input_content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    # Filled by ContextBuilder.fit() — null while status='running' before fit.
    backend_used: Mapped[str | None] = mapped_column(Text)
    estimated_prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    reasoning_level: Mapped[str | None] = mapped_column(Text)
    # Provider transport fields — null when the attempt fails before/without transport.
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)
    total_tokens: Mapped[int | None] = mapped_column(Integer)
    request_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    provider_request_id: Mapped[str | None] = mapped_column(Text)
    error_class: Mapped[str | None] = mapped_column(Text)
    error_code: Mapped[str | None] = mapped_column(Text)
    # Transport-retry provenance — ONE gateway attempt may issue several transport POSTs (in-call 429
    # backoff, §9/§10); they are recorded IN THIS ROW, not as new rows. retry_events_json holds only
    # {attempt, statusCode, errorClass, latencyMs, atOffsetMs} — NO headers, key, prompt, or
    # transcript text. backend_route_source is the honesty bit on backend_used: 'requested' until the
    # provider ever echoes the served route (§6); always 'requested' in 4.5b.
    provider_attempt_count: Mapped[int | None] = mapped_column(Integer)
    rate_limit_backoff_count: Mapped[int | None] = mapped_column(Integer)
    last_provider_status_code: Mapped[int | None] = mapped_column(Integer)
    retry_events_json: Mapped[list | None] = mapped_column(JSONB)
    backend_route_source: Mapped[str | None] = mapped_column(Text)
    # Non-prod only; never populated from transcript or prompt text (error bodies / provider
    # metadata only). Truncated transcript text is still student PII.
    debug_text_truncated: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'running'"),
    )
    request_started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
