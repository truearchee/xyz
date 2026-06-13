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
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PostgresUUID
from sqlalchemy.orm import Mapped, mapped_column
from uuid6 import uuid7

from app.platform.db.models.base import Base


class MapUnitSummary(Base):
    """One map-unit's partial detailed summary (map-reduce, 4.5.1a / F-4.5-51).

    The map phase summarizes each consecutive PORTION of the transcript in its own background call;
    each successful partial is persisted here so the detailed job can RESUME (re-running only the
    units that have not yet succeeded) rather than re-summarizing the whole lecture after a failure.

    Partition-bound identity (C3): the unique key includes ``partition_config_hash`` AND
    ``source_transcript_checksum``. A partial is reusable on resume ONLY when BOTH match — so a budget
    change (different partition hash) or a transcript replacement (different checksum) never silently
    reuses a partial that covered a different span of segments. The reduce step reads the succeeded
    partials for one (transcript, partition_config_hash, source_transcript_checksum) tuple.
    """

    __tablename__ = "map_unit_summaries"
    __table_args__ = (
        UniqueConstraint(
            "transcript_id",
            "unit_index",
            "partition_config_hash",
            "source_transcript_checksum",
            name="uq_map_unit_summaries_identity",
        ),
        CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed')",
            name="ck_map_unit_summaries_status",
        ),
        CheckConstraint("unit_index >= 0", name="ck_map_unit_summaries_unit_index"),
        Index(
            "ix_map_unit_summaries_transcript_partition",
            "transcript_id",
            "partition_config_hash",
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
    unit_index: Mapped[int] = mapped_column(Integer, nullable=False)
    # The consecutive segment span this unit covered (the partition never splits a segment).
    start_segment_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("transcript_segments.id", ondelete="CASCADE"),
        nullable=False,
    )
    end_segment_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("transcript_segments.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Partition-bound identity (C3): both must match for a partial to be reusable on resume.
    partition_config_hash: Mapped[str] = mapped_column(Text, nullable=False)
    source_transcript_checksum: Mapped[str] = mapped_column(Text, nullable=False)
    map_prompt_version: Mapped[str] = mapped_column(Text, nullable=False)
    # The map gateway attempt that produced this partial (provenance). Null only on a non-succeeded row.
    ai_request_log_id: Mapped[UUID | None] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("ai_request_logs.id"),
    )
    status: Mapped[str] = mapped_column(Text, nullable=False)
    # The validated DetailedSummaryPartial (model_dump(by_alias=True)); null until succeeded.
    partial_content: Mapped[dict | None] = mapped_column(JSONB)
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
