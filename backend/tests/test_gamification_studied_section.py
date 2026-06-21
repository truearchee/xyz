"""Stage 10 — the ``studied_section`` content-engagement event, on the REAL student section-read path.

Exercises ``student_summaries.get_student_section_detail`` (the endpoint the student section page calls,
``GET /student/sections/{id}``): opening a published section records exactly one event per
student/section/local-day (idempotent re-open), a different section adds its own event, and a recording
failure NEVER breaks the read (savepoint-swallowed) and IS logged (visible, not silently dropped)."""

from __future__ import annotations

import logging
from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from app.domains.student_summaries.service import get_student_section_detail
from app.platform.auth.context import CurrentUserContext
from app.platform.db.models import AppUser, CourseMembership, CourseModule, ModuleSection, StudentActivityEvent
from app.platform.events import STUDIED_SECTION
from app.platform.events.recorder import EventRecorder

pytestmark = pytest.mark.anyio


async def _published_section(db):
    owner = AppUser(auth_provider_id="own", email="own@example.test", full_name="Own", role="lecturer", is_active=True, timezone="UTC")
    student = AppUser(auth_provider_id="stu", email="stu@example.test", full_name="Stu", role="student", is_active=True, timezone="UTC")
    db.add_all([owner, student])
    await db.flush()
    module = CourseModule(title="M", description="d", owner_id=owner.id, timezone="UTC", is_active=True)
    db.add(module)
    await db.flush()
    db.add(CourseMembership(user_id=student.id, module_id=module.id, role="student", status="active"))
    section = ModuleSection(
        course_module_id=module.id,
        title="S",
        type="lecture",
        order_index=1,
        week_number=1,
        session_date=date(2026, 6, 17),
        publish_status="published",
        status="active",
    )
    db.add(section)
    await db.commit()
    return student, module, section


def _current_user(student) -> CurrentUserContext:
    return CurrentUserContext(
        user_id=student.id,
        auth_provider_id="stu",
        email="stu@example.test",
        full_name="Stu",
        role="student",
        is_active=True,
        timezone="UTC",
    )


async def _studied_count(db, student_id, section_id=None) -> int:
    clauses = [
        StudentActivityEvent.student_id == student_id,
        StudentActivityEvent.event_type == STUDIED_SECTION,
    ]
    if section_id is not None:
        clauses.append(StudentActivityEvent.metadata_json["sectionId"].astext == str(section_id))
    return await db.scalar(select(func.count()).select_from(StudentActivityEvent).where(*clauses)) or 0


async def test_opening_summary_records_one_event_and_dedups_same_day(db_session):
    student, _module, section = await _published_section(db_session)
    current_user = _current_user(student)

    result1 = await get_student_section_detail(db_session, current_user=current_user, section_id=section.id)
    assert result1 is not None
    assert await _studied_count(db_session, student.id) == 1

    # Re-open the SAME section the same local day → no second event (uuid5 dedup).
    await get_student_section_detail(db_session, current_user=current_user, section_id=section.id)
    assert await _studied_count(db_session, student.id) == 1


async def test_different_section_adds_its_own_event(db_session):
    student, module, section = await _published_section(db_session)
    other = ModuleSection(
        course_module_id=module.id,
        title="S2",
        type="lab",
        order_index=2,
        week_number=1,
        session_date=date(2026, 6, 18),
        publish_status="published",
        status="active",
    )
    db_session.add(other)
    await db_session.commit()
    current_user = _current_user(student)

    await get_student_section_detail(db_session, current_user=current_user, section_id=section.id)
    await get_student_section_detail(db_session, current_user=current_user, section_id=other.id)
    assert await _studied_count(db_session, student.id) == 2
    assert await _studied_count(db_session, student.id, section.id) == 1
    assert await _studied_count(db_session, student.id, other.id) == 1


async def test_read_survives_when_event_recording_fails(db_session, monkeypatch, caplog):
    student, _module, section = await _published_section(db_session)
    current_user = _current_user(student)

    async def boom(*args, **kwargs):
        raise SQLAlchemyError("simulated recorder failure")

    monkeypatch.setattr(EventRecorder, "record", boom)
    # The summary read must still succeed even though engagement recording raised...
    with caplog.at_level(logging.WARNING):
        result = await get_student_section_detail(db_session, current_user=current_user, section_id=section.id)
    assert result is not None
    assert await _studied_count(db_session, student.id) == 0  # nothing recorded, nothing crashed
    # ...but the failure is VISIBLE (logged + retryable on the next open), never silently swallowed.
    assert any(
        "studied_section" in record.getMessage() and record.levelno >= logging.WARNING
        for record in caplog.records
    )
