"""Stage 11.1 reconciliation (three-branch landing): `studied_section` counts as qualifying activity.

The `inactive_recently` risk reason resets its clock only on events whose type is in the explicit,
config-backed qualifying set (`settings.RISK_ACTIVITY_EVENT_TYPES`, threaded through
`RiskConfig.activity_event_types`). `studied_section` — the CONTENT-domain engagement event added to the
shared activity spine by Stage 10's migration 0080 — is in that set per owner decision (ADR-060).

These tests prove both halves of the owner contract and that the filter is genuinely honored:
- a student whose only recent activity is `studied_section` is NOT flagged inactive;
- a student with no *recent* qualifying activity IS flagged after the threshold;
- removing `studied_section` from the event-type set excludes the event (the set is not cosmetic).

Isolation: this reads a content-owned event off the shared `StudentActivityEvent` spine by `event_type`.
It imports nothing from the gamification domain.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest

from app.domains.analytics.risk import RiskMetrics, RiskResult, classify_risk
from app.domains.analytics.service import risk_config
from app.platform.db.models import (
    AppUser,
    CourseMembership,
    CourseModule,
    ModuleSection,
    StudentActivityEvent,
)
from app.platform.query.analytics_read import has_upcoming_work, latest_activity_at

pytestmark = pytest.mark.anyio

CUTOFF = datetime(2026, 3, 1, 6, tzinfo=UTC)


async def _scaffold(db, *, prefix: str) -> tuple[AppUser, CourseModule]:
    lecturer = AppUser(
        auth_provider_id=f"{prefix}-lect",
        email=f"{prefix}-lect@example.test",
        full_name="Inactivity Lecturer",
        role="lecturer",
        is_active=True,
        timezone="UTC",
    )
    student = AppUser(
        auth_provider_id=f"{prefix}-stud",
        email=f"{prefix}-stud@example.test",
        full_name="Inactivity Student",
        role="student",
        is_active=True,
        timezone="UTC",
    )
    db.add_all([lecturer, student])
    await db.flush()

    module = CourseModule(
        title=f"{prefix} Module",
        description="risk inactivity reconciliation test",
        owner_id=lecturer.id,
        timezone="UTC",
        starts_on=date(2026, 1, 12),
        ends_on=date(2026, 5, 1),
        is_active=True,
    )
    db.add(module)
    await db.flush()

    db.add(CourseMembership(user_id=student.id, module_id=module.id, role="student", status="active"))
    # A future-due active section so `upcoming_work_exists` is True — inactive_recently is gated on it.
    db.add(
        ModuleSection(
            course_module_id=module.id,
            title="Upcoming deliverable",
            type="lecture",
            order_index=1,
            week_number=1,
            session_date=date(2026, 4, 1),
            due_at=datetime(2026, 4, 1, 12, tzinfo=UTC),
            publish_status="published",
            status="active",
        )
    )
    await db.flush()
    return student, module


def _record(db, *, student_id, module_id, event_type: str, occurred_at: datetime) -> None:
    db.add(
        StudentActivityEvent(
            student_id=student_id,
            module_id=module_id,
            event_type=event_type,
            source_id=uuid4(),
            occurred_at=occurred_at,
        )
    )


def _classify(student_id, module_id, *, days_since_activity, upcoming, config) -> RiskResult:
    metrics = RiskMetrics(
        student_id=student_id,
        module_id=module_id,
        forecast_state=None,
        missed_recent_quiz_count=0,
        recent_quiz_scores=(),
        days_since_activity=days_since_activity,
        upcoming_work_exists=upcoming,
        topic_gap_title=None,
        topic_gap_due_in_hours=None,
    )
    return classify_risk(metrics, config=config, source_cutoff_at=CUTOFF)


async def test_studied_section_only_recent_activity_is_not_flagged_inactive(db_session) -> None:
    student, module = await _scaffold(db_session, prefix="risk-studied")
    _record(
        db_session,
        student_id=student.id,
        module_id=module.id,
        event_type="studied_section",
        occurred_at=CUTOFF - timedelta(days=2),
    )
    await db_session.commit()

    config = risk_config()
    assert "studied_section" in config.activity_event_types  # owner decision is live in config

    latest = await latest_activity_at(
        db_session,
        student_id=student.id,
        module_id=module.id,
        source_cutoff_at=CUTOFF,
        event_types=config.activity_event_types,
    )
    assert latest is not None  # studied_section COUNTS as qualifying activity
    days = max(0, (CUTOFF - latest).days)
    assert days == 2

    upcoming = await has_upcoming_work(db_session, module_id=module.id, source_cutoff_at=CUTOFF)
    assert upcoming is True

    result = _classify(student.id, module.id, days_since_activity=days, upcoming=upcoming, config=config)
    assert "inactive_recently" not in {reason.code for reason in result.reasons}

    # The set is genuinely honored: drop studied_section and the only event is excluded -> None.
    excluded = await latest_activity_at(
        db_session,
        student_id=student.id,
        module_id=module.id,
        source_cutoff_at=CUTOFF,
        event_types=("completed_quiz", "perfect_quiz_score"),
    )
    assert excluded is None


async def test_no_recent_qualifying_activity_is_flagged_inactive_after_threshold(db_session) -> None:
    student, module = await _scaffold(db_session, prefix="risk-inactive")
    config = risk_config()
    stale_offset = config.inactivity_needs_support_days + 5  # comfortably past the needs_support threshold
    _record(
        db_session,
        student_id=student.id,
        module_id=module.id,
        event_type="studied_section",
        occurred_at=CUTOFF - timedelta(days=stale_offset),
    )
    await db_session.commit()

    latest = await latest_activity_at(
        db_session,
        student_id=student.id,
        module_id=module.id,
        source_cutoff_at=CUTOFF,
        event_types=config.activity_event_types,
    )
    days = max(0, (CUTOFF - latest).days)
    assert days == stale_offset

    upcoming = await has_upcoming_work(db_session, module_id=module.id, source_cutoff_at=CUTOFF)
    result = _classify(student.id, module.id, days_since_activity=days, upcoming=upcoming, config=config)
    inactive = [reason for reason in result.reasons if reason.code == "inactive_recently"]
    assert inactive, "a student past the inactivity threshold must be flagged inactive_recently"
    assert inactive[0].severity == "needs_support"
    assert inactive[0].supporting_metrics == {"daysSinceActivity": days}
