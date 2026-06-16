from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.db.models import CourseModule, ModuleSection


# Stage 5.5a — schedule-driven section generation (replaces the fixed 4-section template).
# Generation is WEEKDAY + DATE-RANGE driven (D1): only (start date × weekday pattern) yields real
# session_dates. It is a PURE, unit-testable function (D8); the domain owns the write. Lectures and
# labs are the only generated section types; the quiz day generates nothing in this stage.

WEEKDAYS: tuple[str, ...] = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)
WEEKDAY_INDEX: dict[str, int] = {name: index for index, name in enumerate(WEEKDAYS)}
WEEKDAY_ABBR: tuple[str, ...] = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
# Hardcoded to keep titles locale-independent and deterministic across machines.
MONTH_ABBR: tuple[str, ...] = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)

GENERATED_SECTION_TYPES: tuple[str, ...] = ("lecture", "lab")
# Global ordering tie-break within a single session_date: lecture before lab.
_TYPE_PRIORITY: dict[str, int] = {"lecture": 0, "lab": 1}
_TYPE_LABEL: dict[str, str] = {"lecture": "Lecture", "lab": "Lab"}

DEFAULT_WEEK_START_DAY = "monday"


@dataclass(frozen=True)
class SectionDraft:
    """A generated section before it is persisted — pure data, no DB identity."""

    type: str
    session_date: date
    week_number: int
    order_index: int
    title: str


def _anchor(start: date, week_start_index: int) -> date:
    """Most recent week_start_day on-or-before the course start date."""
    delta = (start.weekday() - week_start_index) % 7
    return start - timedelta(days=delta)


def week_number_for(target: date, *, start: date, week_start_day: str = DEFAULT_WEEK_START_DAY) -> int:
    """Deterministic week number: floor((D - anchor)/7) + 1. Always >= 1 for D >= anchor."""
    anchor = _anchor(start, WEEKDAY_INDEX[week_start_day])
    return (target - anchor).days // 7 + 1


def _title(section_type: str, week_number: int, session_date: date) -> str:
    abbr = WEEKDAY_ABBR[session_date.weekday()]
    month = MONTH_ABBR[session_date.month - 1]
    return (
        f"{_TYPE_LABEL[section_type]} — Week {week_number} "
        f"({abbr} {session_date.day:02d} {month})"
    )


def generate_sections(
    *,
    start: date,
    end: date,
    week_start_day: str,
    session_pattern: list[dict[str, Any]],
) -> list[SectionDraft]:
    """Pure generator. Emits a lecture/lab section for each date in [start, end] inclusive whose
    weekday is in the pattern. The quiz day is not part of session_pattern, so it generates nothing.
    Partial first/last weeks (course not starting on week_start_day) simply yield fewer sections."""
    pattern_by_weekday: dict[int, str] = {
        WEEKDAY_INDEX[entry["weekday"]]: entry["sectionType"] for entry in session_pattern
    }
    anchor = _anchor(start, WEEKDAY_INDEX[week_start_day])

    matched: list[tuple[date, str]] = []
    current = start
    while current <= end:
        section_type = pattern_by_weekday.get(current.weekday())
        if section_type is not None:
            matched.append((current, section_type))
        current += timedelta(days=1)

    matched.sort(key=lambda item: (item[0], _TYPE_PRIORITY[item[1]]))

    drafts: list[SectionDraft] = []
    for order_index, (session_date, section_type) in enumerate(matched, start=1):
        week_number = (session_date - anchor).days // 7 + 1
        drafts.append(
            SectionDraft(
                type=section_type,
                session_date=session_date,
                week_number=week_number,
                order_index=order_index,
                title=_title(section_type, week_number, session_date),
            )
        )
    return drafts


def generate_initial_sections(
    db: AsyncSession,
    *,
    module: CourseModule,
) -> list[ModuleSection]:
    """Adapter: generate + add ModuleSection rows from the module's persisted schedule, inside the
    caller's transaction (synchronous + atomic, D14). Requires the schedule to be set — the service
    validates the request (422) before calling, so this is a defensive guard, not a user path."""
    if module.starts_on is None or module.ends_on is None or not module.session_pattern:
        raise ValueError("Cannot generate sections without a module schedule")

    drafts = generate_sections(
        start=module.starts_on,
        end=module.ends_on,
        week_start_day=module.week_start_day or DEFAULT_WEEK_START_DAY,
        session_pattern=module.session_pattern,
    )
    sections = [
        ModuleSection(
            course_module_id=module.id,
            title=draft.title,
            type=draft.type,
            order_index=draft.order_index,
            session_date=draft.session_date,
            week_number=draft.week_number,
            publish_status="draft",
            lecturer_notes=None,
            status="active",
        )
        for draft in drafts
    ]
    db.add_all(sections)
    return sections
