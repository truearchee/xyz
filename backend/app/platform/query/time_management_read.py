"""Read-only time-management context for the Stage 8.6c assistant mode.

This query layer deliberately returns only the requesting student's own visible deadlines and progress.
It is a structured context snapshot for a conversational assistant turn; it does not create plans,
calendar events, analytics artifacts, or rankings.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.db.models import (
    CourseMembership,
    CourseModule,
    ModuleSection,
)
from app.platform.query.progress_read import (
    get_active_target_goal,
    get_grade_scheme_bundle,
    list_progress_snapshots,
    list_student_progress_modules,
    list_topic_mastery,
)


@dataclass(frozen=True)
class TimeManagementDeadline:
    module_id: UUID
    module_title: str
    section_id: UUID
    section_title: str
    section_type: str
    session_date: date | None
    due_at: datetime | None
    event_date: date
    event_source: str
    state: str


@dataclass(frozen=True)
class TimeManagementProgressModule:
    module_id: UUID
    module_title: str
    latest_week: int | None
    standing_points: Decimal | None
    letter_grade: str | None
    target_letter_grade: str | None
    graded_components: int
    total_components: int
    has_topic_mastery: bool


@dataclass(frozen=True)
class TimeManagementWeakTopic:
    module_id: UUID
    module_title: str
    section_id: UUID
    section_title: str
    mastery_percentage: Decimal
    status_label: str


@dataclass(frozen=True)
class TimeManagementContext:
    as_of: date
    window_days: int
    deadlines: list[TimeManagementDeadline]
    progress_modules: list[TimeManagementProgressModule]
    weak_topics: list[TimeManagementWeakTopic]


def _today() -> date:
    return datetime.now(UTC).date()


def _letter_for(points: Decimal | None, boundaries) -> str | None:
    if points is None:
        return None
    for boundary in sorted(boundaries, key=lambda b: b.lower_bound, reverse=True):
        if points >= boundary.lower_bound:
            return boundary.letter_grade
    return None


async def list_time_management_context(
    db: AsyncSession,
    *,
    student_id: UUID,
    as_of: date | None = None,
    window_days: int = 14,
    max_deadlines: int = 16,
    max_weak_topics: int = 6,
) -> TimeManagementContext:
    """Return deterministic, bounded schedule/progress context for one student's time-management chat."""
    start = as_of or _today()
    end = start + timedelta(days=window_days)
    deadlines = await _list_deadlines(
        db, student_id=student_id, start=start, end=end, limit=max_deadlines
    )
    progress_modules, weak_topics = await _list_progress(
        db, student_id=student_id, max_weak_topics=max_weak_topics
    )
    return TimeManagementContext(
        as_of=start,
        window_days=window_days,
        deadlines=deadlines,
        progress_modules=progress_modules,
        weak_topics=weak_topics,
    )


async def _list_deadlines(
    db: AsyncSession, *, student_id: UUID, start: date, end: date, limit: int
) -> list[TimeManagementDeadline]:
    due_date = func.date(ModuleSection.due_at)
    event_date = func.coalesce(due_date, ModuleSection.session_date)
    rows = (
        await db.execute(
            select(
                CourseModule.id,
                CourseModule.title,
                ModuleSection.id,
                ModuleSection.title,
                ModuleSection.type,
                ModuleSection.session_date,
                ModuleSection.due_at,
                event_date.label("event_date"),
            )
            .join(CourseModule, CourseModule.id == ModuleSection.course_module_id)
            .join(CourseMembership, CourseMembership.module_id == CourseModule.id)
            .where(
                CourseMembership.user_id == student_id,
                CourseMembership.role == "student",
                CourseMembership.status == "active",
                CourseModule.is_active.is_(True),
                ModuleSection.status == "active",
                ModuleSection.publish_status == "published",
                or_(ModuleSection.due_at.is_not(None), ModuleSection.session_date.is_not(None)),
                or_(
                    event_date < start,
                    and_(event_date >= start, event_date <= end),
                ),
            )
            .order_by(
                (event_date >= start).asc(),  # overdue first, then upcoming
                event_date.asc(),
                CourseModule.title.asc(),
                ModuleSection.order_index.asc(),
                ModuleSection.id.asc(),
            )
            .limit(limit)
        )
    ).all()
    out: list[TimeManagementDeadline] = []
    for row in rows:
        date_value = row.event_date
        if isinstance(date_value, str):
            date_value = date.fromisoformat(date_value[:10])
        source = "due_at" if row.due_at is not None else "session_date"
        out.append(
            TimeManagementDeadline(
                module_id=row[0],
                module_title=row[1],
                section_id=row[2],
                section_title=row[3],
                section_type=row[4],
                session_date=row[5],
                due_at=row[6],
                event_date=date_value,
                event_source=source,
                state="overdue" if date_value < start else "upcoming",
            )
        )
    return out


async def _list_progress(
    db: AsyncSession, *, student_id: UUID, max_weak_topics: int
) -> tuple[list[TimeManagementProgressModule], list[TimeManagementWeakTopic]]:
    modules = await list_student_progress_modules(db, student_id=student_id)
    progress_rows: list[TimeManagementProgressModule] = []
    weak_rows: list[TimeManagementWeakTopic] = []

    for module in modules:
        snapshots = await list_progress_snapshots(db, student_id=student_id, module_id=module.id)
        latest = snapshots[-1] if snapshots else None
        bundle = await get_grade_scheme_bundle(db, student_id=student_id, module_id=module.id)
        target = await get_active_target_goal(db, student_id=student_id, module_id=module.id)
        components = bundle.components if bundle is not None else []
        graded_components = sum(1 for c in components if c.percentage_score is not None)
        topic_rows = await list_topic_mastery(db, student_id=student_id, module_id=module.id)

        progress_rows.append(
            TimeManagementProgressModule(
                module_id=module.id,
                module_title=module.title,
                latest_week=latest.week_number if latest is not None else None,
                standing_points=latest.standing_points if latest is not None else None,
                letter_grade=(
                    _letter_for(latest.standing_points if latest is not None else None, bundle.boundaries)
                    if bundle is not None
                    else None
                ),
                target_letter_grade=target.target_letter_grade if target is not None else None,
                graded_components=graded_components,
                total_components=len(components),
                has_topic_mastery=bool(topic_rows),
            )
        )
        for mastery, section in topic_rows:
            weak_rows.append(
                TimeManagementWeakTopic(
                    module_id=module.id,
                    module_title=module.title,
                    section_id=section.id,
                    section_title=section.title,
                    mastery_percentage=mastery.mastery_percentage,
                    status_label=mastery.status_label,
                )
            )

    weak_rows.sort(key=lambda r: (r.mastery_percentage, r.module_title, r.section_title))
    return progress_rows, weak_rows[:max_weak_topics]
