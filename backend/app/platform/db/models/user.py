from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, DateTime, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import Mapped, mapped_column
from uuid6 import uuid7

from app.platform.db.models.base import Base


class AppUser(Base):
    __tablename__ = "app_users"
    __table_args__ = (
        UniqueConstraint("auth_provider_id", name="uq_app_users_auth_provider_id"),
        UniqueConstraint("email", name="uq_app_users_email"),
        CheckConstraint(
            "role IN ('student', 'lecturer', 'admin')",
            name="ck_app_users_role",
        ),
        CheckConstraint(
            "preferred_language IN ('en', 'ar', 'zh', 'es', 'fr')",
            name="ck_app_users_preferred_language",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        primary_key=True,
        default=uuid7,
    )
    auth_provider_id: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str] = mapped_column(Text, nullable=False)
    full_name: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("true"),
    )
    timezone: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'UTC'"),
    )
    # Stage 7: the language a student's glossary definitions are generated in (default English).
    preferred_language: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'en'"),
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
