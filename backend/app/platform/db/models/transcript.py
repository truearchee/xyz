from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, Text, text
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import Mapped, mapped_column
from uuid6 import uuid7

from app.platform.db.models.base import Base


class Transcript(Base):
    __tablename__ = "transcripts"
    __table_args__ = (
        CheckConstraint(
            "status IN ('uploaded', 'queued', 'parsing', 'chunking', 'embedding', 'generating', 'completed', 'failed')",
            name="ck_transcripts_status",
        ),
        CheckConstraint(
            "source_type IN ('manual_upload', 'zoom_import')",
            name="ck_transcripts_source_type",
        ),
        CheckConstraint(
            "NOT (is_active = true AND superseded_at IS NOT NULL)",
            name="ck_transcripts_active_not_superseded",
        ),
        CheckConstraint(
            "source_type <> 'manual_upload' OR uploaded_by_user_id IS NOT NULL",
            name="ck_transcripts_manual_upload_has_uploader",
        ),
        CheckConstraint("file_size > 0", name="ck_transcripts_file_size"),
        CheckConstraint(
            "checksum ~ '^[a-f0-9]{64}$'",
            name="ck_transcripts_checksum_lower_hex",
        ),
        Index(
            "uq_active_transcript_per_section",
            "module_section_id",
            unique=True,
            postgresql_where=text("is_active = true"),
        ),
        Index("uq_transcripts_storage_key", "storage_key", unique=True),
        Index("ix_transcripts_module_section_id", "module_section_id"),
    )

    id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        primary_key=True,
        default=uuid7,
    )
    module_section_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("module_sections.id"),
        nullable=False,
    )
    source_type: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'manual_upload'"),
    )
    original_file_name: Mapped[str] = mapped_column(Text, nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str] = mapped_column(Text, nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    checksum: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'uploaded'"),
    )
    uploaded_by_user_id: Mapped[UUID | None] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("app_users.id"),
    )
    is_active: Mapped[bool] = mapped_column(
        nullable=False,
        server_default=text("true"),
    )
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
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
