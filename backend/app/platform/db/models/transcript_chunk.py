from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
    text as sa_text,
)
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import Mapped, mapped_column
from uuid6 import uuid7

from app.platform.db.models.base import Base


class TranscriptChunk(Base):
    __tablename__ = "transcript_chunks"
    __table_args__ = (
        UniqueConstraint(
            "transcript_id",
            "chunk_index",
            name="uq_transcript_chunks_transcript_chunk_index",
        ),
        CheckConstraint("token_count > 0", name="ck_transcript_chunks_token_count"),
        CheckConstraint("length(btrim(text)) > 0", name="ck_transcript_chunks_text_not_blank"),
        CheckConstraint("chunk_index >= 0", name="ck_transcript_chunks_chunk_index"),
        CheckConstraint(
            "end_sequence_number >= start_sequence_number",
            name="ck_transcript_chunks_sequence_range",
        ),
        CheckConstraint(
            """
            embedding IS NULL
            OR (
                embedding_model IS NOT NULL
                AND embedding_model_revision IS NOT NULL
                AND embedding_dimension = 384
                AND embedding_normalization = 'l2'
                AND embedding_version IS NOT NULL
                AND embedding_input_hash IS NOT NULL
            )
            """,
            name="ck_transcript_chunks_embedding_provenance",
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
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    start_segment_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("transcript_segments.id"),
        nullable=False,
    )
    end_segment_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("transcript_segments.id"),
        nullable=False,
    )
    start_sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    end_sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    start_time: Mapped[int | None] = mapped_column(BigInteger)
    end_time: Mapped[int | None] = mapped_column(BigInteger)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    token_count_method: Mapped[str] = mapped_column(Text, nullable=False)
    normalization_version: Mapped[str] = mapped_column(Text, nullable=False)
    chunking_version: Mapped[str] = mapped_column(Text, nullable=False)
    is_oversized: Mapped[bool] = mapped_column(
        nullable=False,
        server_default=sa_text("false"),
    )
    embedding: Mapped[list[float] | None] = mapped_column(Vector(384))
    embedding_model: Mapped[str | None] = mapped_column(Text)
    embedding_model_revision: Mapped[str | None] = mapped_column(Text)
    embedding_dimension: Mapped[int | None] = mapped_column(Integer)
    embedding_normalization: Mapped[str | None] = mapped_column(Text)
    embedding_version: Mapped[str | None] = mapped_column(Text)
    embedding_input_hash: Mapped[str | None] = mapped_column(Text)
    embedding_generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sa_text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sa_text("now()"),
    )
