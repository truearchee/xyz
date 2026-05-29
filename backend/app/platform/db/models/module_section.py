from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import Mapped, mapped_column
from uuid6 import uuid7

from app.platform.db.models.base import Base


class ModuleSection(Base):
    __tablename__ = "module_sections"
    __table_args__ = (
        UniqueConstraint(
            "course_module_id",
            "order_index",
            name="uq_module_sections_module_order",
        ),
        CheckConstraint(
            "type IN ('lecture', 'lab', 'assignment', 'supplementary')",
            name="ck_module_sections_type",
        ),
        CheckConstraint(
            "publish_status IN ('draft', 'published', 'unpublished')",
            name="ck_module_sections_publish_status",
        ),
        CheckConstraint(
            "status IN ('active', 'archived')",
            name="ck_module_sections_status",
        ),
        CheckConstraint("order_index >= 0", name="ck_module_sections_order_index"),
        CheckConstraint(
            "week_number IS NULL OR week_number > 0",
            name="ck_module_sections_week_number",
        ),
        Index(
            "ix_module_sections_module_week",
            "course_module_id",
            "week_number",
        ),
        Index(
            "ix_module_sections_module_session_date",
            "course_module_id",
            "session_date",
        ),
        Index(
            "ix_module_sections_due_at",
            "due_at",
            postgresql_where=text("due_at IS NOT NULL"),
        ),
        Index(
            "ix_module_sections_module_publish_status",
            "course_module_id",
            "publish_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        primary_key=True,
        default=uuid7,
    )
    course_module_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("course_modules.id"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    week_number: Mapped[int | None] = mapped_column(Integer)
    session_date: Mapped[date | None] = mapped_column(Date)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    publish_status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'draft'"),
    )
    lecturer_notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'active'"),
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
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
