"""Read-only section week resolver for Stage 5.5b / Stage 6.

This resolver reads stored ``week_number`` and ``session_date`` values only; it never derives week
numbers from dates and never mutates section metadata. The default ``include_unstamped=False`` is a
Stage 6 safety boundary: quiz scope resolution must exclude null/stale metadata so empty, holiday, or
unstamped curation rows cannot silently enter a recap/exam-prep scope. Stage 6 must still apply its
student-access, publish-status, and completed-detailed-summary filters before creating a quiz
definition.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.db.models import ModuleSection


@dataclass(frozen=True)
class SectionWeekRow:
    id: UUID
    course_module_id: UUID
    title: str
    type: str
    order_index: int
    week_number: int | None
    session_date: date | None
    due_at: datetime | None
    publish_status: str


def _normalize_weeks(covered_weeks: Iterable[int]) -> tuple[int, ...]:
    weeks = tuple(dict.fromkeys(int(week) for week in covered_weeks))
    if any(week < 1 for week in weeks):
        raise ValueError("covered_weeks must contain positive integers")
    return weeks


async def resolve_sections_by_weeks(
    db: AsyncSession,
    *,
    module_id: UUID,
    covered_weeks: Iterable[int],
    include_unstamped: bool = False,
) -> list[SectionWeekRow]:
    """Return lecture/lab section metadata by stored week.

    ``include_unstamped=False`` is the Stage 6 mode: only sections with both a matching
    ``week_number`` and non-null ``session_date`` are returned. ``include_unstamped=True`` is the admin
    curation mode: all active lecture/lab sections for the module are returned, including null metadata,
    so a by-week editor can surface rows that need correction.
    """
    weeks = _normalize_weeks(covered_weeks)
    if not include_unstamped and not weeks:
        return []

    clauses = [
        ModuleSection.course_module_id == module_id,
        ModuleSection.status == "active",
        ModuleSection.type.in_(("lecture", "lab")),
    ]
    if not include_unstamped:
        clauses.extend(
            [
                ModuleSection.week_number.in_(weeks),
                ModuleSection.session_date.is_not(None),
            ]
        )

    rows = (
        await db.execute(
            select(
                ModuleSection.id,
                ModuleSection.course_module_id,
                ModuleSection.title,
                ModuleSection.type,
                ModuleSection.order_index,
                ModuleSection.week_number,
                ModuleSection.session_date,
                ModuleSection.due_at,
                ModuleSection.publish_status,
            )
            .where(*clauses)
            .order_by(
                ModuleSection.week_number.asc().nulls_last(),
                ModuleSection.session_date.asc().nulls_last(),
                ModuleSection.order_index.asc(),
                ModuleSection.id.asc(),
            )
        )
    ).all()

    return [_to_row(row) for row in rows]


def _to_row(row) -> SectionWeekRow:
    return SectionWeekRow(
        id=row.id,
        course_module_id=row.course_module_id,
        title=row.title,
        type=row.type,
        order_index=row.order_index,
        week_number=row.week_number,
        session_date=row.session_date,
        due_at=row.due_at,
        publish_status=row.publish_status,
    )


async def resolve_sections_by_date_range(
    db: AsyncSession,
    *,
    module_id: UUID,
    start_date: date,
    end_date: date,
) -> list[SectionWeekRow]:
    """Stage 6b recap-by-date-range — additive sibling of ``resolve_sections_by_weeks`` (the existing
    signature is unchanged). Lecture/lab sections whose stored ``session_date`` falls within
    ``[start_date, end_date]`` inclusive; only stamped (non-null ``session_date``) active sections, the same
    Stage 6 safety boundary. Stage 6 still applies its student-access / publish / completed-summary filters
    before creating a definition."""
    if start_date > end_date:
        raise ValueError("start_date must be on or before end_date")
    rows = (
        await db.execute(
            select(
                ModuleSection.id,
                ModuleSection.course_module_id,
                ModuleSection.title,
                ModuleSection.type,
                ModuleSection.order_index,
                ModuleSection.week_number,
                ModuleSection.session_date,
                ModuleSection.due_at,
                ModuleSection.publish_status,
            )
            .where(
                ModuleSection.course_module_id == module_id,
                ModuleSection.status == "active",
                ModuleSection.type.in_(("lecture", "lab")),
                ModuleSection.session_date.is_not(None),
                ModuleSection.session_date >= start_date,
                ModuleSection.session_date <= end_date,
            )
            .order_by(
                ModuleSection.session_date.asc().nulls_last(),
                ModuleSection.order_index.asc(),
                ModuleSection.id.asc(),
            )
        )
    ).all()
    return [_to_row(row) for row in rows]
