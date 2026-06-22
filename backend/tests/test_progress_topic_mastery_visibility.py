"""Stage 9 / My Progress topic-mastery visibility (Stage 10.x security fix).

``list_topic_mastery`` feeds the My Progress topic-mastery list. It must apply the same student
section-visibility gate as the rest of the student-facing app, so a topic mastered on a section the
student cannot see (unpublished / inactive module / lost membership) never surfaces. The Stage 9 read
filtered section status/type but omitted ``publish_status == "published"`` — that omission was live on
main. These tests exercise the negative cases the all-published fixtures never did.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.platform.db.models import (
    AppUser,
    CourseMembership,
    CourseModule,
    ModuleSection,
    StudentTopicMasterySnapshot,
)
from app.platform.query.progress_read import list_topic_mastery

pytestmark = pytest.mark.anyio


async def _user(db, email: str, role: str = "student") -> AppUser:
    user = AppUser(
        auth_provider_id=email,
        email=email,
        full_name="Test User",
        role=role,
        is_active=True,
        timezone="UTC",
    )
    db.add(user)
    await db.flush()
    return user


async def _module(db, owner_id) -> CourseModule:
    module = CourseModule(
        title="Module",
        description="test",
        owner_id=owner_id,
        timezone="UTC",
        starts_on=date(2026, 6, 1),
        ends_on=date(2026, 8, 1),
        is_active=True,
    )
    db.add(module)
    await db.flush()
    return module


async def _section(db, module_id, *, order_index, publish_status="published") -> ModuleSection:
    section = ModuleSection(
        course_module_id=module_id,
        title="Section",
        type="lecture",
        order_index=order_index,
        week_number=1,
        session_date=date(2026, 6, 10),
        publish_status=publish_status,
        status="active",
    )
    db.add(section)
    await db.flush()
    return section


def _mastery(student_id, module_id, section_id):
    return StudentTopicMasterySnapshot(
        student_id=student_id,
        module_id=module_id,
        module_section_id=section_id,
        mastery_percentage=95,
        status_label="strong",
    )


async def _student_in_module(db):
    owner = await _user(db, "owner@example.test", role="lecturer")
    student = await _user(db, "student@example.test", role="student")
    module = await _module(db, owner.id)
    db.add(CourseMembership(user_id=student.id, module_id=module.id, role="student", status="active"))
    await db.flush()
    return student, module


async def test_my_progress_hides_unpublished_section_mastery(db_session):
    student, module = await _student_in_module(db_session)
    visible = await _section(db_session, module.id, order_index=1)
    hidden = await _section(db_session, module.id, order_index=2, publish_status="unpublished")
    db_session.add(_mastery(student.id, module.id, visible.id))
    db_session.add(_mastery(student.id, module.id, hidden.id))
    await db_session.commit()

    rows = await list_topic_mastery(db_session, student_id=student.id, module_id=module.id)
    section_ids = {section.id for _, section in rows}
    assert visible.id in section_ids
    assert hidden.id not in section_ids  # unpublished topic must not leak into My Progress


async def test_my_progress_shows_published_section_mastery(db_session):
    # Positive guard against over-correction: a visible mastered section still appears.
    student, module = await _student_in_module(db_session)
    visible = await _section(db_session, module.id, order_index=1)
    db_session.add(_mastery(student.id, module.id, visible.id))
    await db_session.commit()

    rows = await list_topic_mastery(db_session, student_id=student.id, module_id=module.id)
    assert [section.id for _, section in rows] == [visible.id]
