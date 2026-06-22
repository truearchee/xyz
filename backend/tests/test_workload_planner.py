from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import func, select

from app.domains.analytics.service import workload_config
from app.domains.analytics.workload import (
    AvailabilityInput,
    DeadlineInput,
    RiskSnapshotInput,
    WorkloadConfig,
    WorkloadInputs,
    build_workload_plan,
)
from app.platform.db.models import (
    AgentRun,
    AppUser,
    CourseMembership,
    CourseModule,
    ModuleSection,
    StudentRiskSnapshot,
    WorkloadPlan,
)
from tests.test_workload_calendar_export import _parse_calendar, _parse_utc


def _uuid(value: int) -> UUID:
    return UUID(int=value)


def _config(
    *,
    deadline_estimate: int = 60,
    gap_estimate: int = 30,
    overflow_percent: int = 25,
) -> WorkloadConfig:
    return WorkloadConfig(
        algorithm_version="workload-v1",
        daily_overflow_percent=overflow_percent,
        deadline_estimate_minutes=deadline_estimate,
        gap_estimate_minutes=gap_estimate,
        window_morning_start="09:00",
        window_morning_end="11:00",
        window_afternoon_start="14:00",
        window_afternoon_end="16:00",
        window_evening_start="18:00",
        window_evening_end="21:00",
        legacy_fallback_horizon_days=90,
        min_availability_minutes=15,
        max_availability_minutes=480,
    )


def _availability(*, max_minutes: int = 480, days: tuple[str, ...] = ("monday",)) -> AvailabilityInput:
    return AvailabilityInput(
        study_days=days,
        preferred_window="evening",
        max_study_minutes_per_day=max_minutes,
        availability_version=1,
    )


def _deadline(section_id: int, title: str, due_at: datetime) -> DeadlineInput:
    return DeadlineInput(
        section_id=_uuid(section_id),
        title=title,
        section_type="assignment",
        week_number=1,
        due_at=due_at,
    )


def _inputs(
    *,
    availability: AvailabilityInput | None = None,
    deadlines: tuple[DeadlineInput, ...] = (),
    risk_reasons: tuple[dict, ...] = (),
    source_cutoff_at: datetime = datetime(2026, 6, 22, 8, tzinfo=UTC),
    course_ends_on=None,
) -> WorkloadInputs:
    return WorkloadInputs(
        student_id=_uuid(100),
        module_id=_uuid(200),
        module_title="Workload Test",
        module_timezone="UTC",
        course_ends_on=course_ends_on,
        source_cutoff_at=source_cutoff_at,
        availability=availability or _availability(),
        deadlines=deadlines,
        risk_snapshot=RiskSnapshotInput(
            id=_uuid(300),
            risk_reasons=risk_reasons,
            input_hash="risk-hash",
            source_cutoff_at=source_cutoff_at - timedelta(hours=1),
        ),
        forecast_context={"targetLetterGrade": "A", "latestProgress": {"weekNumber": 1}},
    )


def _topic_gap(topic: str, severity: str = "needs_support") -> dict:
    return {
        "code": "topic_deadline_gap",
        "severity": severity,
        "metricKeys": ["topicGapDueInHours", "topicTitle"],
        "lecturerText": f"{topic} needs attention",
        "studentText": f"{topic} could use a little time.",
        "supportingMetrics": {"topicGapDueInHours": 36, "topicTitle": topic},
    }


def _scheduled_minutes_by_day(result) -> dict:
    totals: dict[str, int] = {}
    for item in result.items:
        if item.scheduled_date is None:
            continue
        totals.setdefault(item.scheduled_date.isoformat(), 0)
        totals[item.scheduled_date.isoformat()] += item.estimate_minutes
    return totals


def test_workload_planner_orders_nearest_deadline_with_stable_tiebreak_and_gap_last():
    due_close = datetime(2026, 6, 23, 23, tzinfo=UTC)
    due_later = datetime(2026, 6, 24, 23, tzinfo=UTC)

    result = build_workload_plan(
        _inputs(
            deadlines=(
                _deadline(30, "Close B", due_close),
                _deadline(20, "Later", due_later),
                _deadline(10, "Close A", due_close),
            ),
            risk_reasons=(_topic_gap("Zeta Topic", "watch"),),
        ),
        config=_config(deadline_estimate=30, gap_estimate=30),
    )

    assert [item.label for item in result.items] == [
        "Prepare for Close A",
        "Prepare for Close B",
        "Prepare for Later",
        "Reinforce Zeta Topic",
    ]
    assert [item.reason for item in result.items] == ["deadline", "deadline", "deadline", "gap"]


def test_workload_planner_overflow_uses_exact_config_rounding():
    cutoff = datetime(2026, 6, 22, 8, tzinfo=UTC)
    result = build_workload_plan(
        _inputs(
            availability=_availability(max_minutes=101),
            deadlines=(_deadline(10, "Same-day deliverable", datetime(2026, 6, 22, 21, tzinfo=UTC)),),
            source_cutoff_at=cutoff,
        ),
        config=_config(deadline_estimate=126, overflow_percent=25),
    )

    assert sum(item.estimate_minutes for item in result.items) == 126
    assert _scheduled_minutes_by_day(result) == {"2026-06-22": 126}
    assert _scheduled_minutes_by_day(result)["2026-06-22"] - 101 == 25
    assert all(not item.tight for item in result.items)


def test_workload_planner_impossible_deadline_is_placed_as_fits_and_tight_flagged():
    result = build_workload_plan(
        _inputs(
            availability=_availability(max_minutes=60),
            deadlines=(_deadline(10, "Impossible packet", datetime(2026, 6, 22, 21, tzinfo=UTC)),),
        ),
        config=_config(deadline_estimate=150, overflow_percent=25),
    )

    assert sum(item.estimate_minutes for item in result.items) == 150
    assert _scheduled_minutes_by_day(result) == {"2026-06-22": 75}
    assert max(_scheduled_minutes_by_day(result).values()) <= 75
    assert any(item.scheduled_start_at is None for item in result.items)
    assert all(item.tight for item in result.items)
    assert all(item.tight_message for item in result.items)


def test_workload_planner_zero_capacity_deadline_stays_visible_as_tight_residual():
    result = build_workload_plan(
        _inputs(
            availability=_availability(max_minutes=60),
            deadlines=(_deadline(10, "Before study window", datetime(2026, 6, 22, 17, tzinfo=UTC)),),
        ),
        config=_config(deadline_estimate=60),
    )

    assert len(result.items) == 1
    residual = result.items[0]
    assert residual.label == "Prepare for Before study window"
    assert residual.estimate_minutes == 60
    assert residual.tight is True
    assert residual.scheduled_start_at is None
    assert residual.scheduled_end_at is None


def test_workload_planner_same_day_due_at_is_clipped_not_dropped_or_counted_twice():
    due_at = datetime(2026, 6, 22, 20, tzinfo=UTC)
    result = build_workload_plan(
        _inputs(
            availability=_availability(max_minutes=120),
            deadlines=(_deadline(10, "Same-day clipped", due_at),),
        ),
        config=_config(deadline_estimate=90),
    )

    assert len(result.items) == 1
    assert result.items[0].estimate_minutes == 90
    assert result.items[0].scheduled_start_at == datetime(2026, 6, 22, 18, tzinfo=UTC)
    assert result.items[0].scheduled_end_at == datetime(2026, 6, 22, 19, 30, tzinfo=UTC)
    assert result.items[0].scheduled_end_at <= due_at


def test_workload_input_hash_is_stable_for_same_inputs_and_changes_with_availability():
    inputs = _inputs(
        deadlines=(_deadline(10, "Stable deadline", datetime(2026, 6, 23, 21, tzinfo=UTC)),),
        risk_reasons=(_topic_gap("Stable Topic"),),
    )
    first = build_workload_plan(inputs, config=_config())
    second = build_workload_plan(inputs, config=_config())
    changed = build_workload_plan(
        _inputs(
            availability=_availability(max_minutes=120),
            deadlines=inputs.deadlines,
            risk_reasons=inputs.risk_snapshot.risk_reasons if inputs.risk_snapshot else (),
        ),
        config=_config(),
    )

    assert first.input_hash == second.input_hash
    assert [item for item in first.items] == [item for item in second.items]
    assert changed.input_hash != first.input_hash


def _headers(user: AppUser, jwt_factory) -> dict[str, str]:
    return {"Authorization": f"Bearer {jwt_factory(sub=user.auth_provider_id)}"}


async def _seed_workload_api(db_session):
    now = datetime.now(UTC)
    lecturer = AppUser(
        auth_provider_id="workload-lecturer",
        email="workload-lecturer@example.test",
        full_name="Workload Lecturer",
        role="lecturer",
        is_active=True,
        timezone="UTC",
    )
    student_one = AppUser(
        auth_provider_id="workload-student-one",
        email="workload-student-one@example.test",
        full_name="Workload Student One",
        role="student",
        is_active=True,
        timezone="UTC",
    )
    student_two = AppUser(
        auth_provider_id="workload-student-two",
        email="workload-student-two@example.test",
        full_name="Workload Student Two",
        role="student",
        is_active=True,
        timezone="UTC",
    )
    unassigned = AppUser(
        auth_provider_id="workload-unassigned",
        email="workload-unassigned@example.test",
        full_name="Workload Unassigned",
        role="student",
        is_active=True,
        timezone="UTC",
    )
    admin = AppUser(
        auth_provider_id="workload-admin",
        email="workload-admin@example.test",
        full_name="Workload Admin",
        role="admin",
        is_active=True,
        timezone="UTC",
    )
    db_session.add_all([lecturer, student_one, student_two, unassigned, admin])
    await db_session.flush()
    module = CourseModule(
        title="Workload API Module",
        description="Stage 11.4 API module",
        owner_id=lecturer.id,
        timezone="UTC",
        starts_on=now.date(),
        ends_on=(now + timedelta(days=28)).date(),
        is_active=True,
    )
    db_session.add(module)
    await db_session.flush()
    db_session.add_all(
        [
            CourseMembership(user_id=lecturer.id, module_id=module.id, role="lecturer", status="active"),
            CourseMembership(user_id=student_one.id, module_id=module.id, role="student", status="active"),
            CourseMembership(user_id=student_two.id, module_id=module.id, role="student", status="active"),
        ]
    )
    first_due = now + timedelta(days=2)
    second_due = now + timedelta(days=4)
    db_session.add_all(
        [
            ModuleSection(
                course_module_id=module.id,
                title="Alpha assignment",
                type="assignment",
                order_index=1,
                week_number=1,
                session_date=now.date(),
                due_at=first_due,
                publish_status="published",
                status="active",
            ),
            ModuleSection(
                course_module_id=module.id,
                title="Beta lab",
                type="lab",
                order_index=2,
                week_number=1,
                session_date=now.date(),
                due_at=second_due,
                publish_status="published",
                status="active",
            ),
        ]
    )
    run = AgentRun(
        trigger_type="manual_admin",
        scope_type="module",
        scope_id=module.id,
        scheduled_for=now,
        algorithm_version="risk-v1",
        status="completed",
        idempotency_key=f"workload-api-{module.id}",
    )
    db_session.add(run)
    await db_session.flush()
    for student, topic in ((student_one, "Gamma Topic"), (student_two, "Delta Topic")):
        db_session.add(
            StudentRiskSnapshot(
                agent_run_id=run.id,
                student_id=student.id,
                module_id=module.id,
                risk_tier="needs_support",
                risk_reasons=[_topic_gap(topic)],
                algorithm_version="risk-v1",
                input_hash=f"risk-{student.id}",
                source_cutoff_at=now,
                computed_at=now,
            )
        )
    await db_session.commit()
    return lecturer, student_one, student_two, unassigned, admin, module


@pytest.mark.anyio
async def test_workload_api_is_student_scoped_reproducible_and_supersedes(
    auth_client,
    db_session,
    jwt_factory,
    mock_jwks_client,
):
    lecturer, student_one, student_two, unassigned, admin, module = await _seed_workload_api(db_session)

    lecturer_forbidden = await auth_client.get(
        f"/student/modules/{module.id}/workload/plan",
        headers=_headers(lecturer, jwt_factory),
    )
    assert lecturer_forbidden.status_code == 403
    admin_forbidden = await auth_client.get(
        f"/student/modules/{module.id}/workload/plan",
        headers=_headers(admin, jwt_factory),
    )
    assert admin_forbidden.status_code == 403
    unassigned_forbidden = await auth_client.get(
        f"/student/modules/{module.id}/workload/plan",
        headers=_headers(unassigned, jwt_factory),
    )
    assert unassigned_forbidden.status_code == 403

    availability = await auth_client.put(
        f"/student/modules/{module.id}/workload/availability",
        headers=_headers(student_one, jwt_factory),
        json={
            "studyDays": ["monday", "tuesday", "wednesday", "thursday", "friday"],
            "preferredWindow": "evening",
            "maxStudyMinutesPerDay": 120,
        },
    )
    assert availability.status_code == 200, availability.text
    assert availability.json()["availabilityVersion"] == 1

    first = await auth_client.post(
        f"/student/modules/{module.id}/workload/plan:generate",
        headers=_headers(student_one, jwt_factory),
    )
    assert first.status_code == 200, first.text
    first_body = first.json()
    assert first_body["algorithmVersion"] == workload_config().algorithm_version
    assert first_body["items"]
    assert all("estimateMinutes" in item and "reason" in item for item in first_body["items"])
    assert str(student_two.id) not in first.text
    assert student_two.email not in first.text

    student_two_missing_own_plan = await auth_client.get(
        f"/student/modules/{module.id}/workload/plan",
        headers=_headers(student_two, jwt_factory),
    )
    assert student_two_missing_own_plan.status_code == 404

    student_two_plan = await auth_client.post(
        f"/student/modules/{module.id}/workload/plan:generate",
        headers=_headers(student_two, jwt_factory),
    )
    assert student_two_plan.status_code == 200, student_two_plan.text
    assert student_two_plan.json()["id"] != first_body["id"]
    assert str(student_one.id) not in student_two_plan.text
    assert student_one.email not in student_two_plan.text

    changed_availability = await auth_client.put(
        f"/student/modules/{module.id}/workload/availability",
        headers=_headers(student_one, jwt_factory),
        json={
            "studyDays": ["monday", "tuesday", "wednesday", "thursday", "friday"],
            "preferredWindow": "evening",
            "maxStudyMinutesPerDay": 180,
        },
    )
    assert changed_availability.status_code == 200, changed_availability.text
    assert changed_availability.json()["availabilityVersion"] == 2

    second = await auth_client.post(
        f"/student/modules/{module.id}/workload/plan:generate",
        headers=_headers(student_one, jwt_factory),
    )
    assert second.status_code == 200, second.text
    second_body = second.json()
    assert second_body["id"] != first_body["id"]
    assert second_body["inputHash"] != first_body["inputHash"]

    old_plan = await db_session.get(WorkloadPlan, UUID(first_body["id"]))
    assert old_plan is not None
    assert old_plan.is_active is False
    assert old_plan.superseded_at is not None
    active_count = await db_session.scalar(
        select(func.count())
        .select_from(WorkloadPlan)
        .where(
            WorkloadPlan.student_id == student_one.id,
            WorkloadPlan.module_id == module.id,
            WorkloadPlan.is_active.is_(True),
        )
    )
    assert active_count == 1


@pytest.mark.anyio
async def test_workload_calendar_export_is_student_scoped_parseable_and_handles_empty_plan(
    auth_client,
    db_session,
    jwt_factory,
    mock_jwks_client,
):
    lecturer, student_one, student_two, unassigned, admin, module = await _seed_workload_api(db_session)

    availability = await auth_client.put(
        f"/student/modules/{module.id}/workload/availability",
        headers=_headers(student_one, jwt_factory),
        json={
            "studyDays": ["monday", "tuesday", "wednesday", "thursday", "friday"],
            "preferredWindow": "evening",
            "maxStudyMinutesPerDay": 120,
        },
    )
    assert availability.status_code == 200, availability.text
    generated = await auth_client.post(
        f"/student/modules/{module.id}/workload/plan:generate",
        headers=_headers(student_one, jwt_factory),
    )
    assert generated.status_code == 200, generated.text
    plan_id = generated.json()["id"]

    before_export = datetime.now(UTC)
    exported = await auth_client.get(
        f"/student/workload/plans/{plan_id}/calendar.ics",
        headers=_headers(student_one, jwt_factory),
    )
    after_export = datetime.now(UTC)
    assert exported.status_code == 200, exported.text
    assert exported.headers["content-type"].startswith("text/calendar")
    assert "attachment" in exported.headers["content-disposition"]
    assert f"{plan_id}.ics" in exported.headers["content-disposition"]

    properties, events = _parse_calendar(exported.text)
    assert properties["PRODID"] == "XYZ LMS"
    assert events
    study_events = [event for event in events if event["UID"].startswith("workload-plan-item-")]
    deadline_events = [event for event in events if event["UID"].startswith("module-deadline-")]
    assert study_events
    assert deadline_events
    first_study = study_events[0]
    assert first_study["SUMMARY"].startswith("Study: ")
    assert "Reason: " in first_study["DESCRIPTION"]
    assert "Estimate: " in first_study["DESCRIPTION"]
    dtstamp = _parse_utc(first_study["DTSTAMP"])
    assert before_export.timestamp() - 1 <= dtstamp.timestamp() <= after_export.timestamp() + 1
    assert str(student_two.id) not in exported.text
    assert student_two.email not in exported.text

    second_export = await auth_client.get(
        f"/student/workload/plans/{plan_id}/calendar.ics",
        headers=_headers(student_one, jwt_factory),
    )
    assert second_export.status_code == 200, second_export.text
    _, second_events = _parse_calendar(second_export.text)
    assert sorted(event["UID"] for event in events) == sorted(event["UID"] for event in second_events)

    other_student = await auth_client.get(
        f"/student/workload/plans/{plan_id}/calendar.ics",
        headers=_headers(student_two, jwt_factory),
    )
    assert other_student.status_code == 403
    assert other_student.text
    lecturer_forbidden = await auth_client.get(
        f"/student/workload/plans/{plan_id}/calendar.ics",
        headers=_headers(lecturer, jwt_factory),
    )
    assert lecturer_forbidden.status_code == 403
    admin_forbidden = await auth_client.get(
        f"/student/workload/plans/{plan_id}/calendar.ics",
        headers=_headers(admin, jwt_factory),
    )
    assert admin_forbidden.status_code == 403
    unassigned_forbidden = await auth_client.get(
        f"/student/workload/plans/{plan_id}/calendar.ics",
        headers=_headers(unassigned, jwt_factory),
    )
    assert unassigned_forbidden.status_code == 403

    changed_availability = await auth_client.put(
        f"/student/modules/{module.id}/workload/availability",
        headers=_headers(student_one, jwt_factory),
        json={
            "studyDays": ["monday", "tuesday", "wednesday", "thursday", "friday"],
            "preferredWindow": "evening",
            "maxStudyMinutesPerDay": 180,
        },
    )
    assert changed_availability.status_code == 200, changed_availability.text
    regenerated = await auth_client.post(
        f"/student/modules/{module.id}/workload/plan:generate",
        headers=_headers(student_one, jwt_factory),
    )
    assert regenerated.status_code == 200, regenerated.text
    inactive = await auth_client.get(
        f"/student/workload/plans/{plan_id}/calendar.ics",
        headers=_headers(student_one, jwt_factory),
    )
    assert inactive.status_code == 409
    assert inactive.json()["detail"] == "Workload plan is no longer active"

    missing = await auth_client.get(
        f"/student/workload/plans/{_uuid(999)}/calendar.ics",
        headers=_headers(student_one, jwt_factory),
    )
    assert missing.status_code == 404

    now = datetime.now(UTC)
    empty_module = CourseModule(
        title="Empty Calendar Module",
        description="No workload items or deadlines",
        owner_id=lecturer.id,
        timezone="UTC",
        starts_on=now.date(),
        ends_on=(now + timedelta(days=14)).date(),
        is_active=True,
    )
    db_session.add(empty_module)
    await db_session.flush()
    db_session.add(CourseMembership(user_id=student_one.id, module_id=empty_module.id, role="student", status="active"))
    empty_plan = WorkloadPlan(
        student_id=student_one.id,
        module_id=empty_module.id,
        algorithm_version="workload-v1",
        input_hash="empty-plan",
        availability_version=1,
        source_cutoff_at=now,
        is_active=True,
        provenance={},
        updated_at=now,
    )
    db_session.add(empty_plan)
    await db_session.commit()

    empty_export = await auth_client.get(
        f"/student/workload/plans/{empty_plan.id}/calendar.ics",
        headers=_headers(student_one, jwt_factory),
    )
    assert empty_export.status_code == 200, empty_export.text
    empty_properties, empty_events = _parse_calendar(empty_export.text)
    assert empty_properties["PRODID"] == "XYZ LMS"
    assert empty_events == []
