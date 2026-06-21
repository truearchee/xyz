from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer, text
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.db.models.base import Base


class StudentStreakState(Base):
    """Persisted monotonic gamification state per student (Stage 10).

    The CURRENT streak is always recomputed on read from the event spine + schedule (ADR-057). This
    table persists only what must survive a break or a shrinking read window:
    - ``longest_streak`` — the max-ever streak (monotonic; streak-milestone badges key off it), kept
      O(1) to read.
    - ``last_seen_gamification_at`` — when the student last loaded gamification, so a freshly-earned
      badge can be surfaced once (``newBadgeIds``) without re-celebrating on every reload.
    """

    __tablename__ = "student_streak_state"

    student_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("app_users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    longest_streak: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )
    last_seen_gamification_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
