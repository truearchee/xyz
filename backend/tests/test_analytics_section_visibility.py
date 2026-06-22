"""Stage 11 analytics section-visibility gate (re-closes the Stage 10.x leak class).

The Stage 10 fix routed the student-facing gamification/progress reads through
``apply_visible_section_gate`` so a section the student cannot see (unpublished / inactive module /
lost membership) never feeds student output. Stage 11's analytics reads (risk, recommendations,
workload, forecast) re-introduced the same omission: they filtered ``status == "active"`` but dropped
``publish_status == "published"`` (or had no section gate at all), so a hidden section's title /
metadata / due-date / grade weight could reach a student via risk text, the workload plan, the .ics,
or the forecast number.

These tests exercise the negative cases the all-published Stage 11 fixtures never did, plus the
NULL-section carve-out (a legitimately section-less grade component / module-level quiz must STILL
count) and a scheduler recompute: a snapshot recomputed after a section is unpublished must not
re-serve the stale leaked title.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.domains.analytics.service import (
    get_or_create_agent_run,
    run_agent_run,
)
from app.platform.db.models import (
    AppUser,
    CourseGradeScheme,
    CourseMembership,
    CourseModule,
    GradeComponent,
    ModuleSection,
    QuizDefinition,
    StudentRiskSnapshot,
    StudentTopicMasterySnapshot,
)
from app.platform.query import analytics_read

pytestmark = pytest.mark.anyio

# A fixed "now" so due-at windows are deterministic.
NOW = datetime(2026, 6, 22, 8, tzinfo=UTC)
SOON = NOW + timedelta(days=1)  # inside every watch window below


# --------------------------------------------------------------------------------------------------
# Builders (mirror tests/test_progress_topic_mastery_visibility.py)
# --------------------------------------------------------------------------------------------------
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


async def _module(db, owner_id, *, is_active: bool = True) -> CourseModule:
    module = CourseModule(
        title="Module",
        description="test",
        owner_id=owner_id,
        timezone="UTC",
        starts_on=date(2026, 6, 1),
        ends_on=date(2026, 8, 1),
        is_active=is_active,
    )
    db.add(module)
    await db.flush()
    return module


async def _section(
    db,
    module_id,
    *,
    order_index: int = 1,
    publish_status: str = "published",
    status: str = "active",
    due_at: datetime | None = SOON,
    title: str = "Section",
) -> ModuleSection:
    section = ModuleSection(
        course_module_id=module_id,
        title=title,
        type="lecture",
        order_index=order_index,
        week_number=1,
        session_date=date(2026, 6, 10),
        due_at=due_at,
        publish_status=publish_status,
        status=status,
    )
    db.add(section)
    await db.flush()
    return section


def _mastery(student_id, module_id, section_id, *, status_label: str = "needs_attention"):
    return StudentTopicMasterySnapshot(
        student_id=student_id,
        module_id=module_id,
        module_section_id=section_id,
        mastery_percentage=40,
        status_label=status_label,
    )


def _quiz(module_id, section_id, *, created_at: datetime):
    return QuizDefinition(
        module_id=module_id,
        module_section_id=section_id,
        quiz_mode="post_class",
        source_scope={},
        created_at=created_at,
    )


async def _student_in_module(db, *, module_active: bool = True, membership_status: str = "active"):
    owner = await _user(db, "owner@example.test", role="lecturer")
    student = await _user(db, "student@example.test", role="student")
    module = await _module(db, owner.id, is_active=module_active)
    db.add(
        CourseMembership(
            user_id=student.id, module_id=module.id, role="student", status=membership_status
        )
    )
    await db.flush()
    return student, module


# --------------------------------------------------------------------------------------------------
# #1 earliest_topic_deadline_gap — leaks a section TITLE verbatim into risk / recommendation text
# --------------------------------------------------------------------------------------------------
async def _gap(db, student_id, module_id):
    return await analytics_read.earliest_topic_deadline_gap(
        db,
        student_id=student_id,
        module_id=module_id,
        source_cutoff_at=NOW,
        within_hours=7 * 24,
    )


async def test_topic_deadline_gap_excludes_unpublished_section(db_session):
    student, module = await _student_in_module(db_session)
    hidden = await _section(
        db_session, module.id, publish_status="unpublished", title="Confidential Final Project"
    )
    db_session.add(_mastery(student.id, module.id, hidden.id))
    await db_session.commit()
    assert await _gap(db_session, student.id, module.id) is None


async def test_topic_deadline_gap_excludes_inactive_module(db_session):
    student, module = await _student_in_module(db_session, module_active=False)
    section = await _section(db_session, module.id)
    db_session.add(_mastery(student.id, module.id, section.id))
    await db_session.commit()
    assert await _gap(db_session, student.id, module.id) is None


async def test_topic_deadline_gap_excludes_lost_membership(db_session):
    student, module = await _student_in_module(db_session, membership_status="archived")
    section = await _section(db_session, module.id)
    db_session.add(_mastery(student.id, module.id, section.id))
    await db_session.commit()
    assert await _gap(db_session, student.id, module.id) is None


async def test_topic_deadline_gap_returns_visible_section(db_session):
    # Positive guard against over-correction.
    student, module = await _student_in_module(db_session)
    section = await _section(db_session, module.id, title="Cash Flow Analysis")
    db_session.add(_mastery(student.id, module.id, section.id))
    await db_session.commit()
    gap = await _gap(db_session, student.id, module.id)
    assert gap is not None
    assert gap.title == "Cash Flow Analysis"


# --------------------------------------------------------------------------------------------------
# #2 get_workload_module_context — unpublished section leaks into the workload plan / .ics
# --------------------------------------------------------------------------------------------------
async def test_workload_context_excludes_unpublished_section(db_session):
    student, module = await _student_in_module(db_session)
    visible = await _section(db_session, module.id, order_index=1, title="Visible Deliverable")
    hidden = await _section(
        db_session,
        module.id,
        order_index=2,
        publish_status="draft",
        title="Secret Deliverable",
    )
    await db_session.commit()

    context = await analytics_read.get_workload_module_context(
        db_session, module_id=module.id, source_cutoff_at=NOW
    )
    assert context is not None
    section_ids = {deadline.section_id for deadline in context.deadlines}
    titles = {deadline.title for deadline in context.deadlines}
    assert visible.id in section_ids
    assert hidden.id not in section_ids
    assert "Secret Deliverable" not in titles


# --------------------------------------------------------------------------------------------------
# #3 get_grade_forecast_inputs — components on hidden sections must not move the forecast,
#    but a NULL-section (scheme-level) component MUST still count (carve-out).
# --------------------------------------------------------------------------------------------------
async def test_grade_forecast_inputs_gate_with_null_section_carveout(db_session):
    student, module = await _student_in_module(db_session)
    visible = await _section(db_session, module.id, order_index=1)
    hidden = await _section(db_session, module.id, order_index=2, publish_status="unpublished")

    scheme = CourseGradeScheme(
        module_id=module.id,
        name="Default",
        on_track_max=Decimal("50"),
        at_risk_max=Decimal("80"),
        benchmark_min_cohort=3,
    )
    db_session.add(scheme)
    await db_session.flush()

    visible_component = GradeComponent(
        scheme_id=scheme.id, name="Visible", weight=Decimal("0.5"), sort_order=1,
        module_section_id=visible.id,
    )
    scheme_level_component = GradeComponent(
        scheme_id=scheme.id, name="SchemeLevel", weight=Decimal("0.3"), sort_order=2,
        module_section_id=None,  # legitimately section-less — must still count
    )
    hidden_component = GradeComponent(
        scheme_id=scheme.id, name="Hidden", weight=Decimal("0.2"), sort_order=3,
        module_section_id=hidden.id,
    )
    db_session.add_all([visible_component, scheme_level_component, hidden_component])
    await db_session.commit()

    inputs = await analytics_read.get_grade_forecast_inputs(
        db_session, student_id=student.id, module_id=module.id
    )
    assert inputs is not None
    component_ids = {component.id for component in inputs.components}
    assert visible_component.id in component_ids
    assert scheme_level_component.id in component_ids  # carve-out: NULL section still counts
    assert hidden_component.id not in component_ids  # unpublished-section component excluded
    # The hidden component's weight does not contaminate the forecast denominator.
    assert sum(component.weight for component in inputs.components) == Decimal("0.8")


# --------------------------------------------------------------------------------------------------
# #4 count_missed_recent_quizzes — a quiz on a hidden section must not count as "missed";
#    a section-less quiz (recap/exam_prep/mistakes_bank) still counts (carve-out).
# --------------------------------------------------------------------------------------------------
async def test_count_missed_recent_quizzes_gate_with_null_section_carveout(db_session):
    student, module = await _student_in_module(db_session)
    visible = await _section(db_session, module.id, order_index=1)
    hidden = await _section(db_session, module.id, order_index=2, publish_status="unpublished")
    created = NOW - timedelta(days=1)
    db_session.add_all(
        [
            _quiz(module.id, visible.id, created_at=created),
            _quiz(module.id, None, created_at=created),  # module-level quiz — still counts
            _quiz(module.id, hidden.id, created_at=created),  # hidden — must be excluded
        ]
    )
    await db_session.commit()

    # No completed attempts → every counted definition is "missed". Visible + NULL-section count (2);
    # the hidden-section quiz is excluded.
    missed = await analytics_read.count_missed_recent_quizzes(
        db_session, student_id=student.id, module_id=module.id, limit=10, source_cutoff_at=NOW
    )
    assert missed == 2


# --------------------------------------------------------------------------------------------------
# #4b has_upcoming_work — a draft future section must not flip the inactivity reason / risk tier.
# --------------------------------------------------------------------------------------------------
async def test_has_upcoming_work_ignores_unpublished_section(db_session):
    student, module = await _student_in_module(db_session)
    await _section(db_session, module.id, order_index=1, publish_status="draft", due_at=SOON)
    await db_session.commit()
    assert (
        await analytics_read.has_upcoming_work(
            db_session, module_id=module.id, source_cutoff_at=NOW
        )
        is False
    )


async def test_has_upcoming_work_true_for_published_section(db_session):
    student, module = await _student_in_module(db_session)
    await _section(db_session, module.id, order_index=1, due_at=SOON)
    await db_session.commit()
    assert (
        await analytics_read.has_upcoming_work(
            db_session, module_id=module.id, source_cutoff_at=NOW
        )
        is True
    )


# --------------------------------------------------------------------------------------------------
# #5 student_has_module — a deactivated module must not serve student-facing analytics.
# --------------------------------------------------------------------------------------------------
async def test_student_has_module_false_for_inactive_module(db_session):
    student, module = await _student_in_module(db_session, module_active=False)
    await db_session.commit()
    assert (
        await analytics_read.student_has_module(
            db_session, student_id=student.id, module_id=module.id
        )
        is False
    )


async def test_student_has_module_true_for_active_module(db_session):
    student, module = await _student_in_module(db_session)
    await db_session.commit()
    assert (
        await analytics_read.student_has_module(
            db_session, student_id=student.id, module_id=module.id
        )
        is True
    )


# --------------------------------------------------------------------------------------------------
# Scheduler recompute: a snapshot recomputed after the section is unpublished must not re-serve the
# stale leaked title (the title was frozen into StudentRiskSnapshot.risk_reasons at compute time).
# --------------------------------------------------------------------------------------------------
def _reasons_blob(snapshot: StudentRiskSnapshot) -> str:
    import json

    return json.dumps(snapshot.risk_reasons)


async def _run_snapshot(db, student_id, module_id, *, scheduled_for) -> StudentRiskSnapshot:
    run, _created = await get_or_create_agent_run(
        db,
        trigger_type="manual_admin",
        scope_type="student",
        scope_id=student_id,
        scheduled_for=scheduled_for,
        triggered_by_user_id=None,
        algorithm_version="risk-v1",
    )
    await db.commit()
    await run_agent_run(db, run_id=run.id)
    snapshot = await db.scalar(
        select(StudentRiskSnapshot).where(
            StudentRiskSnapshot.agent_run_id == run.id,
            StudentRiskSnapshot.student_id == student_id,
        )
    )
    assert snapshot is not None
    return snapshot


async def test_scheduler_recompute_drops_stale_title_after_unpublish(db_session):
    student, module = await _student_in_module(db_session)
    section = await _section(db_session, module.id, title="Mergers and Acquisitions")
    db_session.add(_mastery(student.id, module.id, section.id))
    await db_session.commit()

    # First run while published: the topic_deadline_gap reason carries the section title.
    first = await _run_snapshot(
        db_session, student.id, module.id, scheduled_for=NOW + timedelta(seconds=1)
    )
    assert "Mergers and Acquisitions" in _reasons_blob(first)
    assert any(reason["code"] == "topic_deadline_gap" for reason in first.risk_reasons)

    # Unpublish the section, then recompute. The fresh snapshot must not re-serve the stale title.
    section.publish_status = "unpublished"
    await db_session.commit()

    second = await _run_snapshot(
        db_session, student.id, module.id, scheduled_for=NOW + timedelta(seconds=2)
    )
    assert "Mergers and Acquisitions" not in _reasons_blob(second)
    assert not any(reason["code"] == "topic_deadline_gap" for reason in second.risk_reasons)
