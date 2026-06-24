"""Stage 12b — content-visibility gate uniformity for analytics reads.

Regression lock for the recurring leak class (F-LAND-1): unpublished sections must never surface in
student-facing analytics. Tests the three previously-ungated `analytics_read` queries directly at the
query layer — a published + an unpublished section are created, and the unpublished one must be excluded
from the workload context, upcoming-work detection, and the topic-deadline gap that feeds student risk text.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.db.models import (
    AppUser,
    CourseMembership,
    CourseModule,
    ModuleSection,
    StudentTopicMasterySnapshot,
)
from app.platform.query import analytics_read

pytestmark = pytest.mark.anyio


async def _student_and_module(db: AsyncSession) -> tuple[AppUser, CourseModule]:
    student = AppUser(
        auth_provider_id=f"vis-{uuid4()}",
        email=f"vis-{uuid4()}@example.test",
        full_name="Vis Student",
        role="student",
        is_active=True,
        timezone="UTC",
    )
    db.add(student)
    await db.flush()
    module = CourseModule(
        title="Vis Module",
        description=None,
        owner_id=student.id,
        timezone="UTC",
        starts_on=None,
        ends_on=None,
        is_active=True,
    )
    db.add(module)
    await db.flush()
    db.add(CourseMembership(user_id=student.id, module_id=module.id, role="student", status="active"))
    await db.flush()
    return student, module


def _section(
    module: CourseModule, *, title: str, publish_status: str, due_at: datetime, order_index: int
) -> ModuleSection:
    return ModuleSection(
        course_module_id=module.id,
        title=title,
        type="lecture",
        order_index=order_index,
        due_at=due_at,
        publish_status=publish_status,
        status="active",
    )


async def test_workload_context_excludes_unpublished_sections(db_session: AsyncSession) -> None:
    student, module = await _student_and_module(db_session)
    now = datetime.now(UTC)
    db_session.add_all(
        [
            _section(module, title="Published Lecture", publish_status="published",
                     due_at=now + timedelta(days=2), order_index=0),
            _section(module, title="Secret Draft Lecture", publish_status="draft",
                     due_at=now + timedelta(days=1), order_index=1),
        ]
    )
    await db_session.flush()

    context = await analytics_read.get_workload_module_context(
        db_session, module_id=module.id, source_cutoff_at=now
    )
    assert context is not None
    titles = {deadline.title for deadline in context.deadlines}
    assert "Published Lecture" in titles
    assert "Secret Draft Lecture" not in titles  # unpublished must never surface


async def test_has_upcoming_work_ignores_unpublished_sections(db_session: AsyncSession) -> None:
    student, module = await _student_and_module(db_session)
    now = datetime.now(UTC)
    # The ONLY section with an upcoming deadline is unpublished → no actionable upcoming work.
    db_session.add(
        _section(module, title="Draft Only", publish_status="draft",
                 due_at=now + timedelta(days=1), order_index=0)
    )
    await db_session.flush()

    assert (
        await analytics_read.has_upcoming_work(db_session, module_id=module.id, source_cutoff_at=now)
        is False
    )


async def test_topic_deadline_gap_excludes_unpublished_section(db_session: AsyncSession) -> None:
    student, module = await _student_and_module(db_session)
    now = datetime.now(UTC)
    published = _section(module, title="Published Topic", publish_status="published",
                         due_at=now + timedelta(hours=36), order_index=0)
    unpublished = _section(module, title="Draft Topic", publish_status="draft",
                           due_at=now + timedelta(hours=6), order_index=1)  # earlier deadline
    db_session.add_all([published, unpublished])
    await db_session.flush()
    for section in (published, unpublished):
        db_session.add(
            StudentTopicMasterySnapshot(
                student_id=student.id,
                module_id=module.id,
                module_section_id=section.id,
                mastery_percentage=Decimal("40"),
                status_label="needs_attention",
                source_metrics={"test": "12b"},
                calculated_at=now,
            )
        )
    await db_session.flush()

    gap = await analytics_read.earliest_topic_deadline_gap(
        db_session, student_id=student.id, module_id=module.id, source_cutoff_at=now, within_hours=72
    )
    # The earlier deadline belongs to the unpublished section; after the gate the earliest VISIBLE gap
    # is the published one — the draft's title never leaks into the student's risk reason text.
    assert gap is not None
    assert gap.title == "Published Topic"
