"""Record the content-engagement event ``studied_section`` (Stage 10).

A platform-events helper (NOT a domain) so any content-serving domain that serves a student's section
summary can record the engagement WITHOUT a cross-domain import (rule 8) — it sits beside
``EventRecorder`` as "how to emit this specific spine event with per-day idempotency". Gamification only
CONSUMES the event (rule 7); this is the single emission point, called from the student-facing section
read (``student_summaries``).

Deduped per (student, section, configured-tz local day) via a deterministic ``uuid5`` ``source_id`` that
reuses the existing ``UNIQUE(event_type, source_id)``. The one ``now_utc`` read feeds BOTH ``occurred_at``
and the dedup day, so a midnight-edge request can't store the row under one day but key it under another.

Reliability (ADR-057): emitted inside a SAVEPOINT so a dedup ``IntegrityError`` (or any DB error) cannot
poison the caller's read session; a non-dedup failure is LOGGED (visible + retried on the next open),
never silently dropped; on success it commits so the row exists by the time the response returns (E2E
asserts it directly — no production-leakable test flag).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID, uuid5
from zoneinfo import ZoneInfo

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.config import settings
from app.platform.events.recorder import STUDIED_SECTION, EventRecorder

logger = logging.getLogger(__name__)

# Frozen namespace for studied_section dedup source_ids — NEVER change it (would let every section be
# "studied" again). The uuid5 of (student, section, local-day) collapses same-day re-opens (and
# concurrent double-opens) to ONE event via the existing UNIQUE(event_type, source_id).
STUDIED_SECTION_NAMESPACE = UUID("7c9e6a4b-2d1f-4e8a-b3c5-0a1b2c3d4e5f")


async def record_studied_section(
    db: AsyncSession,
    *,
    student_id: UUID,
    module_id: UUID,
    section_id: UUID,
) -> None:
    now_utc = datetime.now(UTC)
    local_day = now_utc.astimezone(ZoneInfo(settings.COURSE_TIMEZONE)).date()
    source_id = uuid5(
        STUDIED_SECTION_NAMESPACE,
        f"{student_id}:{section_id}:{local_day.isoformat()}",
    )
    try:
        async with db.begin_nested():
            await EventRecorder().record(
                db,
                student_id=student_id,
                module_id=module_id,
                event_type=STUDIED_SECTION,
                source_id=source_id,
                occurred_at=now_utc,
                metadata={"sectionId": str(section_id), "localDay": local_day.isoformat()},
            )
    except IntegrityError:
        # Already studied this section today — the uuid5 collapses re-opens to one row. Idempotent.
        return
    except SQLAlchemyError:
        # Recording failed — log (retryable on the next open) but NEVER break the summary read.
        logger.warning(
            "Failed to record studied_section engagement event",
            extra={
                "student_id": str(student_id),
                "section_id": str(section_id),
                "local_day": local_day.isoformat(),
            },
        )
        return
    await db.commit()
