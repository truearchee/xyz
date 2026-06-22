from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from app.domains.analytics.calendar_export import (
    CalendarDeadline,
    CalendarPlanItem,
    build_workload_calendar,
)


def _uuid(value: int) -> UUID:
    return UUID(int=value)


def _unfold_lines(content: str) -> list[str]:
    assert "\r\n" in content
    raw_lines = content.split("\r\n")
    assert raw_lines[-1] == ""
    unfolded: list[str] = []
    for line in raw_lines[:-1]:
        if line.startswith(" "):
            assert unfolded, "Continuation line without a parent line"
            unfolded[-1] += line[1:]
        else:
            unfolded.append(line)
    return unfolded


def _parse_calendar(content: str) -> tuple[dict[str, str], list[dict[str, str]]]:
    lines = _unfold_lines(content)
    assert lines[0] == "BEGIN:VCALENDAR"
    assert lines[-1] == "END:VCALENDAR"
    properties: dict[str, str] = {}
    events: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    for line in lines[1:-1]:
        if line == "BEGIN:VEVENT":
            assert current is None
            current = {}
            continue
        if line == "END:VEVENT":
            assert current is not None
            events.append(current)
            current = None
            continue
        assert ":" in line, f"Invalid iCalendar line: {line!r}"
        name, value = line.split(":", 1)
        if current is None:
            properties[name] = value
        else:
            current[name] = value
    assert current is None
    return properties, events


def _parse_utc(value: str) -> datetime:
    assert value.endswith("Z")
    return datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)


def test_workload_calendar_exports_parseable_study_items_deadlines_and_required_fields():
    exported_at = datetime(2026, 6, 21, 8, 30, tzinfo=UTC)
    content = build_workload_calendar(
        plan_id=_uuid(1),
        module_title="Calendar Module",
        calendar_timezone="UTC",
        exported_at=exported_at,
        plan_items=[
            CalendarPlanItem(
                id=_uuid(10),
                label="Close assignment, semicolon; newline\nbackslash \\ topic",
                estimate_minutes=90,
                reason="deadline",
                scheduled_start_at=datetime(2026, 6, 22, 18, tzinfo=UTC),
                scheduled_end_at=datetime(2026, 6, 22, 19, 30, tzinfo=UTC),
            ),
            CalendarPlanItem(
                id=_uuid(11),
                label="Unscheduled tight residual",
                estimate_minutes=45,
                reason="deadline",
                scheduled_start_at=None,
                scheduled_end_at=None,
                tight=True,
                tight_message="Plan may not fully fit before the deadline.",
            ),
        ],
        deadlines=[
            CalendarDeadline(
                id=_uuid(20),
                title="Portfolio review",
                due_at=datetime(2026, 6, 23, 21, tzinfo=UTC),
            )
        ],
    )

    properties, events = _parse_calendar(content)
    assert properties["VERSION"] == "2.0"
    assert properties["PRODID"] == "XYZ LMS"
    assert properties["X-XYZ-SNAPSHOT"] == "true"
    assert len(events) == 2
    study, deadline = events

    assert study["UID"] == f"workload-plan-item-{_uuid(10)}@xyz-lms"
    assert study["DTSTAMP"] == "20260621T083000Z"
    assert study["DTSTART"] == "20260622T180000Z"
    assert study["DTEND"] == "20260622T193000Z"
    assert study["SUMMARY"] == r"Study: Close assignment\, semicolon\; newline\nbackslash \\ topic"
    assert study["DESCRIPTION"] == r"Reason: deadline\nEstimate: 90 minutes"

    assert deadline["UID"] == f"module-deadline-{_uuid(20)}@xyz-lms"
    assert deadline["SUMMARY"] == "Deadline: Portfolio review"
    assert deadline["DTSTART"] == "20260623T210000Z"
    assert deadline["DTEND"] == "20260623T211500Z"


def test_workload_calendar_uid_stability_ignores_export_dtstamp():
    item = CalendarPlanItem(
        id=_uuid(10),
        label="Stable topic",
        estimate_minutes=60,
        reason="gap",
        scheduled_start_at=datetime(2026, 6, 22, 18, tzinfo=UTC),
        scheduled_end_at=datetime(2026, 6, 22, 19, tzinfo=UTC),
    )

    first = build_workload_calendar(
        plan_id=_uuid(1),
        module_title="Calendar Module",
        calendar_timezone="UTC",
        exported_at=datetime(2026, 6, 21, 8, tzinfo=UTC),
        plan_items=[item],
        deadlines=[],
    )
    second = build_workload_calendar(
        plan_id=_uuid(1),
        module_title="Calendar Module",
        calendar_timezone="UTC",
        exported_at=datetime(2026, 6, 21, 9, tzinfo=UTC),
        plan_items=[item],
        deadlines=[],
    )

    _, first_events = _parse_calendar(first)
    _, second_events = _parse_calendar(second)
    assert first_events[0]["UID"] == second_events[0]["UID"]
    assert first_events[0]["DTSTAMP"] == "20260621T080000Z"
    assert second_events[0]["DTSTAMP"] == "20260621T090000Z"


def test_workload_calendar_cross_timezone_dst_edge_preserves_the_same_absolute_instant():
    institution_tz = ZoneInfo("Europe/London")
    viewer_tz = ZoneInfo("Asia/Dubai")
    institution_start = datetime(2026, 3, 29, 18, 0, tzinfo=institution_tz)
    institution_end = datetime(2026, 3, 29, 19, 0, tzinfo=institution_tz)

    content = build_workload_calendar(
        plan_id=_uuid(1),
        module_title="DST Module",
        calendar_timezone="Europe/London",
        exported_at=datetime(2026, 3, 29, 12, tzinfo=UTC),
        plan_items=[
            CalendarPlanItem(
                id=_uuid(10),
                label="DST study block",
                estimate_minutes=60,
                reason="deadline",
                scheduled_start_at=institution_start.astimezone(UTC),
                scheduled_end_at=institution_end.astimezone(UTC),
            )
        ],
        deadlines=[],
    )

    properties, events = _parse_calendar(content)
    assert properties["X-WR-TIMEZONE"] == "Europe/London"
    start = _parse_utc(events[0]["DTSTART"])
    end = _parse_utc(events[0]["DTEND"])

    assert events[0]["DTSTART"] == "20260329T170000Z"
    assert start.timestamp() == institution_start.timestamp()
    assert end.timestamp() == institution_end.timestamp()
    assert start.astimezone(institution_tz).hour == 18
    assert start.astimezone(viewer_tz).hour == 21
    assert start.astimezone(viewer_tz).hour != 18


def test_workload_calendar_allows_empty_snapshot_without_events():
    content = build_workload_calendar(
        plan_id=_uuid(1),
        module_title="Empty Module",
        calendar_timezone="UTC",
        exported_at=datetime(2026, 6, 21, 8, tzinfo=UTC),
        plan_items=[],
        deadlines=[],
    )

    properties, events = _parse_calendar(content)
    assert properties["PRODID"] == "XYZ LMS"
    assert events == []
