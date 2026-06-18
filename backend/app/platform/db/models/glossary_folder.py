from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
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


class GlossaryFolder(Base):
    """A free-form, per-student organizational bucket for glossary entries (Stage 7a).

    Pure display/organization — ``folder_id`` does NOT participate in dedup, cache, or practice scope
    (that is ``subject_id`` on the entry). The auto-created "Unsorted" inbox is ``is_system=true`` and
    is not user-deletable; it is the default destination for highlight-saved terms. "Delete" archives
    (status → archived), never hard-deletes (Stage 10 event reproducibility).
    """

    __tablename__ = "glossary_folders"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'archived')",
            name="ck_glossary_folders_status",
        ),
        # A student cannot have two ACTIVE folders with the same name; an archived one does not block reuse.
        Index(
            "uq_glossary_folders_student_name_active",
            "student_id",
            "name",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
        # Exactly one active system "Unsorted" folder per student.
        Index(
            "uq_glossary_folders_one_system",
            "student_id",
            unique=True,
            postgresql_where=text("is_system AND status = 'active'"),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        primary_key=True,
        default=uuid7,
    )
    student_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("app_users.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    is_system: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
    )
    status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'active'"),
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
