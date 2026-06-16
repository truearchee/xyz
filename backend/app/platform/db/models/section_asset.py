from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import Mapped, mapped_column
from uuid6 import uuid7

from app.platform.db.models.base import Base


class SectionAsset(Base):
    __tablename__ = "section_assets"
    __table_args__ = (
        CheckConstraint(
            "processing_status IN ('uploaded', 'processing', 'completed', 'failed')",
            name="ck_section_assets_processing_status",
        ),
        CheckConstraint(
            "asset_kind IN ('processable', 'attachment')",
            name="ck_section_assets_asset_kind",
        ),
        CheckConstraint("file_size > 0", name="ck_section_assets_file_size"),
        UniqueConstraint("storage_key", name="uq_section_assets_storage_key"),
        Index("ix_section_assets_section", "module_section_id"),
        Index("ix_section_assets_uploader", "uploaded_by_user_id"),
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
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    file_name: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str] = mapped_column(Text, nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    asset_kind: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'processable'"),
    )
    processing_status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'completed'"),
    )
    uploaded_by_user_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("app_users.id"),
        nullable=False,
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
