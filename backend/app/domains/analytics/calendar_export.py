from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID


DEADLINE_MARKER_DURATION = timedelta(minutes=15)
PRODUCT_ID = "XYZ LMS"


@dataclass(frozen=True, slots=True)
class CalendarPlanItem:
    id: UUID
    label: str
    estimate_minutes: int
    reason: str
    scheduled_start_at: datetime | None
    scheduled_end_at: datetime | None
    tight: bool = False
    tight_message: str | None = None


@dataclass(frozen=True, slots=True)
class CalendarDeadline:
    id: UUID
    title: str
    due_at: datetime


@dataclass(frozen=True, slots=True)
class CalendarExport:
    content: str
    filename: str


def build_workload_calendar(
    *,
    plan_id: UUID,
    module_title: str,
    calendar_timezone: str,
    exported_at: datetime,
    plan_items: list[CalendarPlanItem],
    deadlines: list[CalendarDeadline],
) -> str:
    dtstamp = _format_utc_datetime(exported_at)
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        _property("PRODID", PRODUCT_ID),
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        _property("X-WR-CALNAME", f"XYZ LMS Study Plan: {module_title}"),
        _property("X-WR-TIMEZONE", calendar_timezone),
        _property("X-XYZ-WORKLOAD-PLAN-ID", str(plan_id)),
        _property("X-XYZ-SNAPSHOT", "true"),
    ]

    for item in plan_items:
        if item.scheduled_start_at is None or item.scheduled_end_at is None:
            continue
        lines.extend(
            _event_lines(
                uid=f"workload-plan-item-{item.id}@xyz-lms",
                dtstamp=dtstamp,
                start_at=item.scheduled_start_at,
                end_at=item.scheduled_end_at,
                summary=f"Study: {item.label}",
                description=_study_description(item),
            )
        )

    for deadline in deadlines:
        lines.extend(
            _event_lines(
                uid=f"module-deadline-{deadline.id}@xyz-lms",
                dtstamp=dtstamp,
                start_at=deadline.due_at,
                end_at=deadline.due_at + DEADLINE_MARKER_DURATION,
                summary=f"Deadline: {deadline.title}",
                description=f"Deadline for {deadline.title}.",
            )
        )

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


def _event_lines(
    *,
    uid: str,
    dtstamp: str,
    start_at: datetime,
    end_at: datetime,
    summary: str,
    description: str,
) -> list[str]:
    return [
        "BEGIN:VEVENT",
        _property("UID", uid),
        _property("DTSTAMP", dtstamp),
        _property("DTSTART", _format_utc_datetime(start_at)),
        _property("DTEND", _format_utc_datetime(end_at)),
        _property("SUMMARY", summary),
        _property("DESCRIPTION", description),
        "END:VEVENT",
    ]


def _study_description(item: CalendarPlanItem) -> str:
    parts = [
        f"Reason: {_reason_label(item.reason)}",
        f"Estimate: {item.estimate_minutes} minutes",
    ]
    if item.tight and item.tight_message:
        parts.append(item.tight_message)
    return "\n".join(parts)


def _reason_label(reason: str) -> str:
    if reason == "deadline":
        return "deadline"
    if reason == "gap":
        return "gap"
    return reason


def _property(name: str, value: str) -> str:
    return "\r\n".join(_fold_line(f"{name}:{_escape_text(value)}"))


def _escape_text(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\n", "\\n")
        .replace(";", "\\;")
        .replace(",", "\\,")
    )


def _format_utc_datetime(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("iCalendar datetimes must be timezone-aware")
    return value.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def _fold_line(line: str) -> list[str]:
    if len(line.encode("utf-8")) <= 75:
        return [line]

    folded: list[str] = []
    prefix = ""
    current = ""
    for char in line:
        candidate = f"{prefix}{current}{char}"
        if current and len(candidate.encode("utf-8")) > 75:
            folded.append(f"{prefix}{current}")
            prefix = " "
            current = char
        else:
            current += char
    folded.append(f"{prefix}{current}")
    return folded
