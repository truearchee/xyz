"""Stage 5.5a — pure schedule-driven section generation + schedule validation.

These are PURE unit tests (no DB, no I/O): the generator is a deterministic function over
(start, end, week_start_day, session_pattern). The 28-section reference oracle is the load-bearing
assertion that cannot be silently weakened — it is the same count the browser gate asserts in 5.5e.
"""

from __future__ import annotations

from datetime import date

from pydantic import ValidationError
import pytest

from app.domains.admin.schemas import ModuleScheduleInput
from app.domains.admin.section_generation import (
    GENERATED_SECTION_TYPES,
    generate_sections,
    week_number_for,
)


# Reference course (product-confirmed): 11 May → 26 Jun 2026, Mon/Tue/Wed=lecture, Thu=lab,
# Fri=quiz (generates nothing). 11 May 2026 is a Monday (clean week-1 start).
REFERENCE_PATTERN = [
    {"weekday": "monday", "sectionType": "lecture"},
    {"weekday": "tuesday", "sectionType": "lecture"},
    {"weekday": "wednesday", "sectionType": "lecture"},
    {"weekday": "thursday", "sectionType": "lab"},
]


def _reference_sections():
    return generate_sections(
        start=date(2026, 5, 11),
        end=date(2026, 6, 26),
        week_start_day="monday",
        session_pattern=REFERENCE_PATTERN,
    )


def test_reference_oracle_counts() -> None:
    sections = _reference_sections()

    assert len(sections) == 28
    assert sum(1 for s in sections if s.type == "lecture") == 21
    assert sum(1 for s in sections if s.type == "lab") == 7
    assert max(s.week_number for s in sections) == 7
    assert all(s.type in GENERATED_SECTION_TYPES for s in sections)


def test_reference_oracle_has_no_friday_section() -> None:
    # The Friday quiz day generates nothing in this stage. weekday() == 4 is Friday.
    sections = _reference_sections()
    assert all(s.session_date.weekday() != 4 for s in sections)


def test_reference_boundary_dates() -> None:
    sections = _reference_sections()
    # 11 May 2026 is a Monday — week 1 starts cleanly.
    assert date(2026, 5, 11).weekday() == 0
    first = sections[0]
    assert first.session_date == date(2026, 5, 11)
    assert first.week_number == 1
    assert first.type == "lecture"
    # The final generated session is the last lab, Thu 25 Jun (week 7); 26 Jun (Fri, in range)
    # generates nothing.
    last = sections[-1]
    assert last.session_date == date(2026, 6, 25)
    assert last.type == "lab"
    assert last.week_number == 7
    assert date(2026, 6, 26) not in {s.session_date for s in sections}


def test_order_index_is_global_and_date_ascending() -> None:
    sections = _reference_sections()
    assert [s.order_index for s in sections] == list(range(1, 29))
    dates = [s.session_date for s in sections]
    assert dates == sorted(dates)


def test_default_title_format() -> None:
    sections = _reference_sections()
    # Stored default title carries the live week + weekday + date (locale-independent month abbr).
    assert sections[0].title == "Lecture — Week 1 (Mon 11 May)"
    assert sections[-1].title == "Lab — Week 7 (Thu 25 Jun)"


def test_week_number_for_matches_generator() -> None:
    start = date(2026, 5, 11)
    assert week_number_for(date(2026, 5, 11), start=start) == 1
    assert week_number_for(date(2026, 5, 18), start=start) == 2
    assert week_number_for(date(2026, 6, 25), start=start) == 7


def test_partial_first_week_yields_fewer_sections_not_an_error() -> None:
    # Course starts Wed 13 May 2026 (not the week_start_day). Anchor is Mon 11 May, so the partial
    # first week still numbers as week 1 and simply has fewer sessions.
    sections = generate_sections(
        start=date(2026, 5, 13),
        end=date(2026, 5, 14),
        week_start_day="monday",
        session_pattern=REFERENCE_PATTERN,
    )
    assert [(s.type, s.session_date, s.week_number) for s in sections] == [
        ("lecture", date(2026, 5, 13), 1),
        ("lab", date(2026, 5, 14), 1),
    ]


def test_empty_range_when_start_equals_end_off_pattern() -> None:
    # A single in-range day that is not in the pattern (Fri 15 May) generates nothing.
    sections = generate_sections(
        start=date(2026, 5, 15),
        end=date(2026, 5, 15),
        week_start_day="monday",
        session_pattern=REFERENCE_PATTERN,
    )
    assert sections == []


def test_configurable_week_start_day_changes_week_boundaries() -> None:
    # weekStartDay is a single configurable field (no branching). With Sunday as the start day, the
    # anchor shifts and week numbering follows.
    pattern = [{"weekday": "monday", "sectionType": "lecture"}]
    start = date(2026, 5, 11)  # Monday
    sunday_anchor = generate_sections(
        start=start,
        end=date(2026, 5, 25),
        week_start_day="sunday",
        session_pattern=pattern,
    )
    # Anchor = Sun 10 May. Mondays 11, 18, 25 May → weeks 1, 2, 3.
    assert [(s.session_date, s.week_number) for s in sunday_anchor] == [
        (date(2026, 5, 11), 1),
        (date(2026, 5, 18), 2),
        (date(2026, 5, 25), 3),
    ]


def test_generation_is_deterministic_no_double_generate() -> None:
    # Pure + deterministic: re-running over the same schedule yields an identical set (the service
    # calls this exactly once inside the creation transaction; re-runs never diverge or double up).
    first = _reference_sections()
    second = _reference_sections()
    assert first == second
    assert len(first) == 28


# ---- Schedule request validation (ModuleScheduleInput) ----


def _schedule(**overrides):
    # snake_case field names (populate_by_name) so **overrides replace, not duplicate-under-alias.
    payload = {
        "course_start_date": date(2026, 5, 11),
        "course_end_date": date(2026, 6, 26),
        "week_start_day": "monday",
        "session_pattern": REFERENCE_PATTERN,
        "quiz_day": "friday",
    }
    payload.update(overrides)
    return payload


def test_valid_schedule_defaults_week_start_to_monday() -> None:
    schedule = ModuleScheduleInput(
        course_start_date=date(2026, 5, 11),
        course_end_date=date(2026, 6, 26),
        session_pattern=REFERENCE_PATTERN,
    )
    assert schedule.week_start_day == "monday"
    assert schedule.quiz_day is None


def test_schedule_rejects_start_after_end() -> None:
    with pytest.raises(ValidationError):
        ModuleScheduleInput(**_schedule(course_start_date=date(2026, 6, 27)))


def test_schedule_rejects_duplicate_weekday() -> None:
    with pytest.raises(ValidationError):
        ModuleScheduleInput(
            **_schedule(
                session_pattern=[
                    {"weekday": "monday", "sectionType": "lecture"},
                    {"weekday": "monday", "sectionType": "lab"},
                ]
            )
        )


def test_schedule_rejects_quiz_day_overlapping_session_weekday() -> None:
    with pytest.raises(ValidationError):
        ModuleScheduleInput(**_schedule(quiz_day="monday"))


def test_schedule_rejects_empty_pattern() -> None:
    with pytest.raises(ValidationError):
        ModuleScheduleInput(**_schedule(session_pattern=[]))


def test_schedule_rejects_non_generated_section_type() -> None:
    with pytest.raises(ValidationError):
        ModuleScheduleInput(
            **_schedule(
                session_pattern=[{"weekday": "monday", "sectionType": "assignment"}]
            )
        )
