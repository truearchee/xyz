"""Read-only gamification primitives (Stage 10) — the shared definition of "showing up".

These two functions are the SINGLE source of truth for "is the student active on scheduled days",
built here in Stage 10 and reused by Stage 11 (rule: build once, don't reinvent):

- ``scheduled_class_days`` → the set of local calendar dates with >=1 scheduled section across the
  student's assigned modules. Stage 5.5 ``session_date`` is already the local class DATE, so multiple
  sections on one date collapse to one day and the cross-module union falls out of set semantics for
  free. No-class days are simply absent (neutral).
- ``engagement_days`` → the set of local calendar dates with >=1 qualifying activity event, derived
  from ``StudentActivityEvent.occurred_at`` (the activity time, not processing time) converted to the
  configured course timezone.

Rule 8: read models only — no business decisions and no cross-domain imports. The streak/badge RULES
live in the gamification domain; this module only answers "which days".
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.db.models import (
    CourseMembership,
    CourseModule,
    ModuleSection,
    QuizDefinition,
    StudentActivityEvent,
    StudentTopicMasterySnapshot,
)
from app.platform.events import (
    COMPLETED_QUIZ,
    GLOSSARY_PRACTICE_COMPLETED,
    GLOSSARY_TERM_SAVED,
    PERFECT_QUIZ_SCORE,
    STUDIED_SECTION,
)
from app.platform.query.section_visibility import apply_visible_section_gate
from app.platform.query.section_week_resolver import resolve_sections_by_date_range

# Stage 9 mastery: "topic mastered" reuses Stage 9's notion (no invented threshold) — a snapshot at the
# top tier. "post_class" is the quiz_mode value (a DB literal, not a cross-domain import) for the
# per-section post-class quiz that module_completed counts against.
_MASTERED_STATUS_LABEL = "strong"
_POST_CLASS_QUIZ_MODE = "post_class"

# The qualifying-activity allowlist for the unified Learning streak (spec): opening a section summary,
# completing a quiz, saving a glossary term, reviewing flashcards (any practice session). Note
# ``perfect_quiz_score`` is deliberately EXCLUDED — it fires on the same attempt as ``completed_quiz``,
# so counting it would be redundant for "did any activity that day".
QUALIFYING_ENGAGEMENT_EVENT_TYPES: tuple[str, ...] = (
    STUDIED_SECTION,
    COMPLETED_QUIZ,
    GLOSSARY_TERM_SAVED,
    GLOSSARY_PRACTICE_COMPLETED,
)


async def _active_student_module_ids(db: AsyncSession, *, student_id: UUID) -> list[UUID]:
    return list(
        (
            await db.scalars(
                select(CourseModule.id)
                .join(CourseMembership, CourseMembership.module_id == CourseModule.id)
                .where(
                    CourseMembership.user_id == student_id,
                    CourseMembership.role == "student",
                    CourseMembership.status == "active",
                    CourseModule.is_active.is_(True),
                )
            )
        ).all()
    )


async def scheduled_class_days(
    db: AsyncSession,
    *,
    student_id: UUID,
    start_date: date,
    end_date: date,
) -> set[date]:
    """Local calendar dates in ``[start_date, end_date]`` with >=1 scheduled section across the
    student's active modules. Reuses ``resolve_sections_by_date_range`` so "what counts as a scheduled
    section" stays defined in one place (active lecture/lab sections with a stored ``session_date``,
    regardless of publish status — a class day is scheduled even before its section is published)."""
    if start_date > end_date:
        return set()
    days: set[date] = set()
    for module_id in await _active_student_module_ids(db, student_id=student_id):
        rows = await resolve_sections_by_date_range(
            db,
            module_id=module_id,
            start_date=start_date,
            end_date=end_date,
        )
        days.update(row.session_date for row in rows if row.session_date is not None)
    return days


async def engagement_days(
    db: AsyncSession,
    *,
    student_id: UUID,
    start_date: date,
    end_date: date,
    tz: ZoneInfo,
    event_types: tuple[str, ...] = QUALIFYING_ENGAGEMENT_EVENT_TYPES,
) -> set[date]:
    """Local calendar dates in ``[start_date, end_date]`` (in ``tz``) on which the student did >=1
    qualifying activity. The UTC query window is padded ±1 day so events near a local-day boundary are
    not clipped; each ``occurred_at`` is converted to ``tz`` before its date is taken, then filtered
    back to the requested local window."""
    if start_date > end_date:
        return set()
    # Pad generously in UTC (max tz offset is ~±14h) and post-filter by the converted local date.
    lo = datetime.combine(start_date - timedelta(days=1), time.min, tzinfo=UTC)
    hi = datetime.combine(end_date + timedelta(days=2), time.min, tzinfo=UTC)
    occurred_ats = (
        await db.scalars(
            select(StudentActivityEvent.occurred_at).where(
                StudentActivityEvent.student_id == student_id,
                StudentActivityEvent.event_type.in_(event_types),
                StudentActivityEvent.occurred_at >= lo,
                StudentActivityEvent.occurred_at < hi,
            )
        )
    ).all()
    days: set[date] = set()
    for occurred_at in occurred_ats:
        local_date = occurred_at.astimezone(tz).date()
        if start_date <= local_date <= end_date:
            days.add(local_date)
    return days


async def earliest_scheduled_day(db: AsyncSession, *, student_id: UUID) -> date | None:
    """The earliest scheduled ``session_date`` across the student's active modules — the lower bound for
    the streak/first-week window (exact, MVP-scale full scan; no fixed lookback)."""
    return await db.scalar(
        select(func.min(ModuleSection.session_date))
        .join(CourseModule, ModuleSection.course_module_id == CourseModule.id)
        .join(CourseMembership, CourseMembership.module_id == CourseModule.id)
        .where(
            CourseMembership.user_id == student_id,
            CourseMembership.role == "student",
            CourseMembership.status == "active",
            CourseModule.is_active.is_(True),
            ModuleSection.status == "active",
            ModuleSection.type.in_(("lecture", "lab")),
            ModuleSection.session_date.is_not(None),
        )
    )


async def next_scheduled_class_day(
    db: AsyncSession, *, student_id: UUID, after_date: date
) -> date | None:
    """The next scheduled class day after ``after_date`` across active student modules.

    This is the bounded future lookup for ``nextScheduledDay``: it asks Postgres for the nearest
    qualifying lecture/lab date rather than scanning an arbitrary future window in Python.
    """
    return await db.scalar(
        select(func.min(ModuleSection.session_date))
        .join(CourseModule, ModuleSection.course_module_id == CourseModule.id)
        .join(CourseMembership, CourseMembership.module_id == CourseModule.id)
        .where(
            CourseMembership.user_id == student_id,
            CourseMembership.role == "student",
            CourseMembership.status == "active",
            CourseModule.is_active.is_(True),
            ModuleSection.status == "active",
            ModuleSection.type.in_(("lecture", "lab")),
            ModuleSection.session_date.is_not(None),
            ModuleSection.session_date > after_date,
        )
    )


async def _count_events(db: AsyncSession, *, student_id: UUID, event_type: str) -> int:
    return (
        await db.scalar(
            select(func.count())
            .select_from(StudentActivityEvent)
            .where(
                StudentActivityEvent.student_id == student_id,
                StudentActivityEvent.event_type == event_type,
            )
        )
    ) or 0


async def _module_completion_progress(
    db: AsyncSession, *, student_id: UUID, module_ids: list[UUID]
) -> dict[UUID, tuple[int, int]]:
    """Per active module: (distinct post-class sections the student has completed a quiz for, total
    quiz-bearing sections). A "quiz-bearing section" = one with a ``post_class`` ``QuizDefinition``
    (the canonical "this section has a quiz" record). The numerator is distinct ``moduleSectionId`` from
    the student's ``completed_quiz`` events with ``quizMode='post_class'`` — fully event-derived."""
    if not module_ids:
        return {}
    quiz_bearing: dict[UUID, set[str]] = {}
    # Only sections the student can actually see count toward the denominator — a quiz on an
    # unpublished (or otherwise non-visible) section must NOT inflate `total`, or the module_completed
    # progress bar would leak that hidden content exists (and make the badge un-earnable).
    bearing_stmt = apply_visible_section_gate(
        select(QuizDefinition.module_id, QuizDefinition.module_section_id).where(
            QuizDefinition.module_id.in_(module_ids),
            QuizDefinition.quiz_mode == _POST_CLASS_QUIZ_MODE,
            QuizDefinition.module_section_id.is_not(None),
        ),
        student_id=student_id,
        section_id_col=QuizDefinition.module_section_id,
    )
    bearing_rows = await db.execute(bearing_stmt)
    for module_id, section_id in bearing_rows.all():
        quiz_bearing.setdefault(module_id, set()).add(str(section_id))

    completed: dict[UUID, set[str]] = {}
    done_rows = await db.execute(
        select(
            StudentActivityEvent.module_id,
            StudentActivityEvent.metadata_json["moduleSectionId"].astext,
        ).where(
            StudentActivityEvent.student_id == student_id,
            StudentActivityEvent.event_type == COMPLETED_QUIZ,
            StudentActivityEvent.metadata_json["quizMode"].astext == _POST_CLASS_QUIZ_MODE,
        )
    )
    for module_id, section_id_text in done_rows.all():
        if section_id_text is not None:
            completed.setdefault(module_id, set()).add(section_id_text)

    return {
        module_id: (len(sections & completed.get(module_id, set())), len(sections))
        for module_id, sections in quiz_bearing.items()
        if sections
    }


async def load_badge_counts(db: AsyncSession, *, student_id: UUID, tz: ZoneInfo) -> dict:
    """Event/snapshot-derived badge metrics for a student (everything except the streak-derived
    ``longest_streak`` / ``has_first_week_activity``, which the service fills). Every value is
    reproducible from the event spine + Stage 9 snapshots; volume counts are DISTINCT source items so
    re-doing work cannot farm a badge."""
    # These two counts are event-derived: the studied_section / completed_quiz events were only emitted
    # behind the published+assigned visibility gate, so they count content the student legitimately saw.
    # A section unpublished AFTER the fact stays counted — accepted retroactive MVP behavior, not a leak.
    distinct_quiz_definitions = (
        await db.scalar(
            select(
                func.count(distinct(StudentActivityEvent.metadata_json["quizDefinitionId"].astext))
            ).where(
                StudentActivityEvent.student_id == student_id,
                StudentActivityEvent.event_type == COMPLETED_QUIZ,
            )
        )
    ) or 0
    distinct_studied_sections = (
        await db.scalar(
            select(
                func.count(distinct(StudentActivityEvent.metadata_json["sectionId"].astext))
            ).where(
                StudentActivityEvent.student_id == student_id,
                StudentActivityEvent.event_type == STUDIED_SECTION,
            )
        )
    ) or 0

    flashcard_occurred_ats = (
        await db.scalars(
            select(StudentActivityEvent.occurred_at).where(
                StudentActivityEvent.student_id == student_id,
                StudentActivityEvent.event_type == GLOSSARY_PRACTICE_COMPLETED,
                StudentActivityEvent.metadata_json["mode"].astext == "flashcard",
            )
        )
    ).all()
    flashcard_days = len({occurred_at.astimezone(tz).date() for occurred_at in flashcard_occurred_ats})

    # A mastery snapshot only counts toward the topic_mastered badge if its section is still visible to
    # the student — mastering a topic on an unpublished (or inactive-module / lost-membership) section
    # must NOT grant the badge, or it leaks that hidden content exists.
    has_mastered_topic = bool(
        await db.scalar(
            apply_visible_section_gate(
                select(func.count())
                .select_from(StudentTopicMasterySnapshot)
                .where(
                    StudentTopicMasterySnapshot.student_id == student_id,
                    StudentTopicMasterySnapshot.status_label == _MASTERED_STATUS_LABEL,
                ),
                student_id=student_id,
                section_id_col=StudentTopicMasterySnapshot.module_section_id,
            )
        )
    )

    module_ids = await _active_student_module_ids(db, student_id=student_id)
    module_progress = await _module_completion_progress(
        db, student_id=student_id, module_ids=module_ids
    )
    module_completed_ids = frozenset(
        module_id for module_id, (done, total) in module_progress.items() if total > 0 and done >= total
    )

    return {
        "distinct_quiz_definitions": int(distinct_quiz_definitions),
        "distinct_studied_sections": int(distinct_studied_sections),
        "flashcard_days": flashcard_days,
        "has_completed_quiz": (await _count_events(db, student_id=student_id, event_type=COMPLETED_QUIZ)) > 0,
        "has_perfect_quiz": (await _count_events(db, student_id=student_id, event_type=PERFECT_QUIZ_SCORE)) > 0,
        "has_term_saved": (await _count_events(db, student_id=student_id, event_type=GLOSSARY_TERM_SAVED)) > 0,
        "has_flashcard": len(flashcard_occurred_ats) > 0,
        "has_mastered_topic": has_mastered_topic,
        "module_completed_ids": module_completed_ids,
        "module_completion_progress": module_progress,
    }
