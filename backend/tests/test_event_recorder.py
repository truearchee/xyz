"""Stage 5a — EventRecorder same-transaction + idempotency contract (§8 / lock 8).

Proves the recorder inserts WITHIN the caller's open transaction (visible before any commit), never
commits on its own (a caller rollback drops the row), and surfaces a duplicate (event_type, source_id)
as IntegrityError. Also pins the QUIZ_EVENT_TYPES tuple to the 0014 DB CHECK so the two never drift.
"""

from __future__ import annotations

import re
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.db.models import AppUser, CourseModule, StudentActivityEvent
from app.platform.events import (
    COMPLETED_QUIZ,
    PERFECT_QUIZ_SCORE,
    QUIZ_EVENT_TYPES,
    EventRecorder,
)

pytestmark = pytest.mark.anyio


async def _seed_student_module(session: AsyncSession) -> tuple[AppUser, CourseModule]:
    student = AppUser(
        auth_provider_id=f"auth-{uuid4()}",
        email=f"student-{uuid4()}@example.com",
        full_name="Event Student",
        role="student",
        timezone="UTC",
    )
    owner = AppUser(
        auth_provider_id=f"auth-{uuid4()}",
        email=f"owner-{uuid4()}@example.com",
        full_name="Event Owner",
        role="lecturer",
        timezone="UTC",
    )
    session.add_all([student, owner])
    await session.flush()
    module = CourseModule(title="Event Module", owner_id=owner.id, timezone="UTC", is_active=True)
    session.add(module)
    await session.flush()
    return student, module


async def test_record_inserts_in_caller_transaction(db_session: AsyncSession) -> None:
    student, module = await _seed_student_module(db_session)
    source_id = uuid4()

    await EventRecorder().record(
        db_session,
        student_id=student.id,
        module_id=module.id,
        event_type=COMPLETED_QUIZ,
        source_id=source_id,
        metadata={"scorePercentage": "90.00"},
    )

    # Visible within the SAME open transaction, before any commit.
    assert db_session.in_transaction()
    row = await db_session.scalar(
        select(StudentActivityEvent).where(StudentActivityEvent.source_id == source_id)
    )
    assert row is not None
    assert row.event_type == COMPLETED_QUIZ
    assert row.metadata_json == {"scorePercentage": "90.00"}
    assert row.occurred_at is not None  # server default now() fired


async def test_record_does_not_commit(db_session: AsyncSession) -> None:
    student, module = await _seed_student_module(db_session)
    source_id = uuid4()

    await EventRecorder().record(
        db_session,
        student_id=student.id,
        module_id=module.id,
        event_type=PERFECT_QUIZ_SCORE,
        source_id=source_id,
    )
    # The recorder never commits; a caller rollback must drop the row.
    await db_session.rollback()

    count = await db_session.scalar(
        select(func.count())
        .select_from(StudentActivityEvent)
        .where(StudentActivityEvent.source_id == source_id)
    )
    assert count == 0


async def test_record_idempotency_raises_integrity_error(db_session: AsyncSession) -> None:
    student, module = await _seed_student_module(db_session)
    source_id = uuid4()
    recorder = EventRecorder()

    await recorder.record(
        db_session,
        student_id=student.id,
        module_id=module.id,
        event_type=COMPLETED_QUIZ,
        source_id=source_id,
    )
    with pytest.raises(IntegrityError):
        await recorder.record(
            db_session,
            student_id=student.id,
            module_id=module.id,
            event_type=COMPLETED_QUIZ,
            source_id=source_id,
        )


async def test_record_rejects_unknown_event_type(db_session: AsyncSession) -> None:
    student, module = await _seed_student_module(db_session)
    with pytest.raises(ValueError):
        await EventRecorder().record(
            db_session,
            student_id=student.id,
            module_id=module.id,
            event_type="streak_extended",
            source_id=uuid4(),
        )


async def test_quiz_event_types_match_check_constraint(db_session: AsyncSession) -> None:
    constraint_def = await db_session.scalar(
        text(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conname = 'ck_student_activity_events_event_type'"
        )
    )
    assert constraint_def is not None
    literals = set(re.findall(r"'([a-z_]+)'", constraint_def))
    assert literals == set(QUIZ_EVENT_TYPES)
