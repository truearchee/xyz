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


class GlossaryDefinitionCache(Base):
    """Shared-across-students definition cache + the cross-student concurrency primitive (Stage 7a).

    Keyed ``(cache_key, prompt_version)`` where ``cache_key = sha256(normalizeVersion + normalizedTerm
    + subjectId + entryType + language)``. A cache HIT = no model call (the primary cost control). The
    UNIQUE ``(cache_key, prompt_version)`` IS the spec's "one-active index keyed on the cache key": a
    ``pending`` row means a single in-flight generation, so two students racing the same
    term/subject/language collapse to ONE model call (the loser hits ON CONFLICT DO NOTHING, attaches
    its entry, and waits for the fan-out). Including ``prompt_version`` in the key means a prompt
    promotion is a fresh miss, never an overwrite (the ``uq_gen_summaries_provenance`` philosophy).

    ``subject_id`` is a bare UUID (no FK) — the cache outlives a module's relevance and is keyed for
    cost/idempotency, not lineage (mirrors ``student_activity_events.source_id``).
    """

    __tablename__ = "glossary_definition_cache"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'generated', 'failed')",
            name="ck_glossary_definition_cache_status",
        ),
        CheckConstraint(
            "entry_type IN ('term', 'concept', 'formula')",
            name="ck_glossary_definition_cache_entry_type",
        ),
        CheckConstraint(
            "language IN ('en', 'ar', 'zh', 'es', 'fr')",
            name="ck_glossary_definition_cache_language",
        ),
        # The one-active-keyed-on-cache-key guard (+ prompt_version invalidation).
        Index(
            "uq_glossary_definition_cache_key",
            "cache_key",
            "prompt_version",
            unique=True,
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        primary_key=True,
        default=uuid7,
    )
    cache_key: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_version: Mapped[str] = mapped_column(Text, nullable=False)
    # Denormalized key components (debuggability / invalidation), not the unique key on their own.
    normalized_term: Mapped[str] = mapped_column(Text, nullable=False)
    subject_id: Mapped[UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False)
    entry_type: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(Text, nullable=False)
    # The display term + (capped) context the FIRST saver provided — the generation inputs. The cache is
    # shared, so the first saver's term/context win (context is deliberately NOT part of the cache key).
    term: Mapped[str] = mapped_column(Text, nullable=False)
    context_text: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'pending'"),
    )
    short_definition: Mapped[str | None] = mapped_column(Text)
    # Provenance (rule 6) — copied from the gateway AIRequestLog row on generation.
    model_id: Mapped[str | None] = mapped_column(Text)
    prompt_content_hash: Mapped[str | None] = mapped_column(Text)
    backend_used: Mapped[str | None] = mapped_column(Text)
    source_content_hash: Mapped[str | None] = mapped_column(Text)
    ai_request_log_id: Mapped[UUID | None] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("ai_request_logs.id", ondelete="SET NULL"),
    )
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
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
