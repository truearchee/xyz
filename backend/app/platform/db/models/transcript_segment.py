from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Integer, Text, UniqueConstraint, text as sa_text
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import Mapped, mapped_column
from uuid6 import uuid7

from app.platform.db.models.base import Base


class TranscriptSegment(Base):
    __tablename__ = "transcript_segments"
    __table_args__ = (
        UniqueConstraint(
            "transcript_id",
            "sequence_number",
            name="uq_transcript_segments_transcript_sequence",
        ),
        CheckConstraint("sequence_number >= 0", name="ck_transcript_segments_sequence_number"),
        CheckConstraint(
            "(start_ms IS NULL AND end_ms IS NULL) OR (start_ms IS NOT NULL AND end_ms IS NOT NULL)",
            name="ck_transcript_segments_timestamp_pair",
        ),
        CheckConstraint("start_ms IS NULL OR start_ms >= 0", name="ck_transcript_segments_start_ms"),
        CheckConstraint("end_ms IS NULL OR end_ms > start_ms", name="ck_transcript_segments_end_ms"),
        CheckConstraint("length(trim(text)) > 0", name="ck_transcript_segments_text_not_blank"),
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
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    start_ms: Mapped[int | None] = mapped_column(BigInteger)
    end_ms: Mapped[int | None] = mapped_column(BigInteger)
    speaker_name: Mapped[str | None] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sa_text("now()"),
    )
