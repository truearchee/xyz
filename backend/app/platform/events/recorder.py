"""The platform activity event spine recorder (Stage 5 §8 / lock 8).

``EventRecorder.record`` inserts a ``StudentActivityEvent`` WITHIN the caller's open transaction and
NEVER commits — the domain owns the commit, so the event and the score it accompanies land atomically
(or roll back together). ``(event_type, source_id)`` is unique, so a re-emit surfaces as an
``IntegrityError`` to the caller (idempotency backstop). No consumer is built in Stage 5 (rule 7:
gamification consumes events, never owns them).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.db.models import StudentActivityEvent

# Stage 5 emits exactly these. The DB CHECK (ck_student_activity_events_event_type) is the real guard;
# this tuple is the single source of truth the recorder validates against and a test pins it to the CHECK.
COMPLETED_QUIZ = "completed_quiz"
PERFECT_QUIZ_SCORE = "perfect_quiz_score"
QUIZ_EVENT_TYPES: tuple[str, ...] = (COMPLETED_QUIZ, PERFECT_QUIZ_SCORE)


class EventRecorder:
    """Records platform activity events inside the caller's transaction (never commits)."""

    async def record(
        self,
        session: AsyncSession,
        *,
        student_id: UUID,
        module_id: UUID,
        event_type: str,
        source_id: UUID,
        metadata: dict | None = None,
        occurred_at: datetime | None = None,
    ) -> StudentActivityEvent:
        if event_type not in QUIZ_EVENT_TYPES:
            # Defensive — the DB CHECK is authoritative, but fail loud and early on a typo'd caller.
            raise ValueError(f"unknown event_type: {event_type!r}")

        event = StudentActivityEvent(
            student_id=student_id,
            module_id=module_id,
            event_type=event_type,
            source_id=source_id,
            metadata_json=metadata,
        )
        if occurred_at is not None:
            # Otherwise let the DB ``now()`` server default fire.
            event.occurred_at = occurred_at

        session.add(event)
        # flush() emits the INSERT inside the caller's open transaction (surfacing a duplicate
        # (event_type, source_id) as IntegrityError) WITHOUT committing — the domain owns the commit.
        await session.flush()
        return event
