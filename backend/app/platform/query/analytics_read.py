from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.query.section_visibility import (
    apply_visible_section_gate,
    published_active_section_conditions,
    visible_section_exists,
)
from app.platform.db.models import (
    AgentRun,
    AnswerOption,
    CourseGradeScheme,
    CourseMembership,
    CourseModule,
    GeneratedLectureSummary,
    GradeBoundary,
    GradeComponent,
    ModuleSection,
    QuizAttempt,
    QuizDefinition,
    QuizQuestion,
    StudentActivityEvent,
    StudentAnswer,
    StudentGradeRecord,
    StudentProgressSnapshot,
    StudentTargetGradeGoal,
    StudentTopicMasterySnapshot,
    StudentRiskSnapshot,
)


SMALL_COHORT_THRESHOLD = 3
SMALL_COHORT_MESSAGE = "Not enough submissions for an aggregate insight"


@dataclass(frozen=True)
class StudentModuleRiskSubject:
    student_id: UUID
    student_name: str
    student_email: str
    module_id: UUID
    module_title: str


@dataclass(frozen=True)
class TopicDeadlineGap:
    title: str
    due_at: datetime


@dataclass(frozen=True)
class GradeComponentScore:
    id: UUID
    weight: Decimal
    percentage_score: Decimal | None


@dataclass(frozen=True)
class GradeForecastInputs:
    target_letter_grade: str | None
    on_track_max: Decimal
    at_risk_max: Decimal
    boundaries: list[tuple[str, Decimal]]
    components: list[GradeComponentScore]


@dataclass(frozen=True)
class WorkloadDeadlineRead:
    section_id: UUID
    title: str
    section_type: str
    week_number: int | None
    due_at: datetime


@dataclass(frozen=True)
class WorkloadModuleContext:
    module_id: UUID
    module_title: str
    timezone: str
    ends_on: date | None
    deadlines: list[WorkloadDeadlineRead]


@dataclass(frozen=True)
class LatestRiskSnapshotRead:
    id: UUID
    risk_reasons: list[dict]
    input_hash: str
    source_cutoff_at: datetime


@dataclass(frozen=True)
class AssessmentAgentRunSummary:
    id: UUID
    status: str
    scope_type: str
    scope_id: UUID | None
    scheduled_for: datetime
    completed_at: datetime | None
    snapshot_count: int
    recommendation_count: int


@dataclass(frozen=True)
class AssessmentDistractorInsight:
    option_key: str
    option_text: str
    selected_count: int
    selected_rate_percent: Decimal | None


@dataclass(frozen=True)
class AssessmentQuestionInsight:
    question_key: str
    question_text: str
    answer_count: int
    correct_count: int
    incorrect_count: int
    correct_rate_percent: Decimal | None
    small_cohort: bool
    small_cohort_message: str | None
    distractors: list[AssessmentDistractorInsight]


@dataclass(frozen=True)
class AssessmentTopicMasteryRow:
    source_section_id: UUID
    topic_title: str
    week_number: int | None
    answer_count: int
    correct_count: int
    mastery_percent: Decimal | None
    small_cohort: bool
    small_cohort_message: str | None


@dataclass(frozen=True)
class AssessmentTopicMastery:
    available: bool
    unavailable_reason: str | None
    unmapped_answer_count: int
    unmapped_message: str | None
    rows: list[AssessmentTopicMasteryRow]


@dataclass(frozen=True)
class AssessmentInsights:
    module_id: UUID
    module_title: str
    latest_agent_run: AssessmentAgentRunSummary | None
    small_cohort_threshold: int
    small_cohort_message: str
    questions: list[AssessmentQuestionInsight]
    most_missed_questions: list[AssessmentQuestionInsight]
    topic_mastery: AssessmentTopicMastery


@dataclass(frozen=True)
class _AssessmentAnswerRow:
    question_id: UUID
    question_text: str
    source_pool_question_id: UUID | None
    source_module_id: UUID | None
    source_section_id: UUID | None
    source_summary_id: UUID | None
    summary_section_id: UUID | None
    selected_option_text: str
    is_correct: bool


async def lecturer_has_module(db: AsyncSession, *, lecturer_id: UUID, module_id: UUID) -> bool:
    return bool(
        await db.scalar(
            select(CourseMembership.id).where(
                CourseMembership.user_id == lecturer_id,
                CourseMembership.module_id == module_id,
                CourseMembership.role == "lecturer",
                CourseMembership.status == "active",
            )
        )
    )


async def student_has_module(db: AsyncSession, *, student_id: UUID, module_id: UUID) -> bool:
    # Active student membership AND an active module: a deactivated module must not serve student-facing
    # analytics (risk / workload / forecast) to a still-enrolled student. This is the entry gate every
    # /student analytics endpoint runs through, so the active-module check belongs here.
    return bool(
        await db.scalar(
            select(CourseMembership.id)
            .join(CourseModule, CourseModule.id == CourseMembership.module_id)
            .where(
                CourseMembership.user_id == student_id,
                CourseMembership.module_id == module_id,
                CourseMembership.role == "student",
                CourseMembership.status == "active",
                CourseModule.is_active.is_(True),
            )
        )
    )


async def get_assessment_insights(db: AsyncSession, *, module_id: UUID) -> AssessmentInsights | None:
    module = await db.get(CourseModule, module_id)
    if module is None or not module.is_active:
        return None

    answer_rows = await _assessment_answer_rows(db, module_id=module_id)
    option_shape_by_question = await _answer_option_shape_by_question(
        db,
        question_ids={row.question_id for row in answer_rows},
    )
    candidate_section_ids = {
        _topic_section_id(row)
        for row in answer_rows
        if _topic_section_id(row) is not None
    }
    section_labels = await _section_labels(
        db,
        module_id=module_id,
        section_ids=candidate_section_ids,
    )

    question_acc: dict[str, dict] = {}
    topic_acc: dict[UUID, dict[str, int]] = defaultdict(lambda: {"answer_count": 0, "correct_count": 0})
    unmapped_answer_count = 0

    for row in answer_rows:
        question_key = _question_key(row, option_shape_by_question.get(row.question_id, ()))
        question = question_acc.setdefault(
            question_key,
            {
                "question_key": question_key,
                "question_text": row.question_text,
                "answer_count": 0,
                "correct_count": 0,
                "incorrect_count": 0,
                "distractors": {},
            },
        )
        question["answer_count"] += 1
        if row.is_correct:
            question["correct_count"] += 1
        else:
            question["incorrect_count"] += 1
            option_key = _option_key(question_key, row.selected_option_text)
            distractor = question["distractors"].setdefault(
                option_key,
                {
                    "option_key": option_key,
                    "option_text": row.selected_option_text,
                    "selected_count": 0,
                },
            )
            distractor["selected_count"] += 1

        candidate_section_id = _topic_section_id(row)
        if candidate_section_id is None or candidate_section_id not in section_labels:
            unmapped_answer_count += 1
        else:
            topic = topic_acc[candidate_section_id]
            topic["answer_count"] += 1
            if row.is_correct:
                topic["correct_count"] += 1

    questions = [_render_question_insight(question) for question in question_acc.values()]
    questions.sort(key=lambda item: (item.question_text.casefold(), item.question_key))
    most_missed = sorted(
        (
            question
            for question in questions
            if not question.small_cohort and question.incorrect_count > 0
        ),
        key=lambda item: (
            -item.incorrect_count,
            item.correct_rate_percent if item.correct_rate_percent is not None else Decimal("100"),
            item.question_text.casefold(),
            item.question_key,
        ),
    )

    topic_rows = [
        _render_topic_mastery_row(section_id, counts, section_labels)
        for section_id, counts in topic_acc.items()
    ]
    topic_rows.sort(key=lambda item: (item.week_number is None, item.week_number or 0, item.topic_title.casefold(), str(item.source_section_id)))
    topic_mastery = AssessmentTopicMastery(
        available=bool(topic_rows),
        unavailable_reason=(
            "Topic mastery unavailable because answered questions do not include source section or summary provenance."
            if not topic_rows and unmapped_answer_count > 0
            else ("No completed submissions yet." if not topic_rows else None)
        ),
        unmapped_answer_count=unmapped_answer_count,
        unmapped_message=(
            f"Topic mastery unavailable for {unmapped_answer_count} submissions without question provenance."
            if unmapped_answer_count > 0
            else None
        ),
        rows=topic_rows,
    )

    return AssessmentInsights(
        module_id=module.id,
        module_title=module.title,
        latest_agent_run=await _latest_agent_run_for_module(db, module_id=module_id),
        small_cohort_threshold=SMALL_COHORT_THRESHOLD,
        small_cohort_message=SMALL_COHORT_MESSAGE,
        questions=questions,
        most_missed_questions=most_missed,
        topic_mastery=topic_mastery,
    )


async def list_risk_subjects(
    db: AsyncSession,
    *,
    module_id: UUID | None = None,
    student_id: UUID | None = None,
) -> list[StudentModuleRiskSubject]:
    from app.platform.db.models import AppUser

    stmt = (
        select(
            AppUser.id.label("student_id"),
            AppUser.full_name.label("student_name"),
            AppUser.email.label("student_email"),
            CourseModule.id.label("module_id"),
            CourseModule.title.label("module_title"),
        )
        .join(CourseMembership, CourseMembership.user_id == AppUser.id)
        .join(CourseModule, CourseModule.id == CourseMembership.module_id)
        .where(
            AppUser.role == "student",
            AppUser.is_active.is_(True),
            CourseMembership.role == "student",
            CourseMembership.status == "active",
            CourseModule.is_active.is_(True),
        )
        .order_by(CourseModule.title.asc(), AppUser.full_name.asc(), AppUser.id.asc())
    )
    if module_id is not None:
        stmt = stmt.where(CourseModule.id == module_id)
    if student_id is not None:
        stmt = stmt.where(AppUser.id == student_id)
    rows = (await db.execute(stmt)).all()
    return [
        StudentModuleRiskSubject(
            student_id=row.student_id,
            student_name=row.student_name,
            student_email=row.student_email,
            module_id=row.module_id,
            module_title=row.module_title,
        )
        for row in rows
    ]


async def get_grade_forecast_inputs(
    db: AsyncSession,
    *,
    student_id: UUID,
    module_id: UUID,
) -> GradeForecastInputs | None:
    scheme = await db.scalar(select(CourseGradeScheme).where(CourseGradeScheme.module_id == module_id))
    if scheme is None:
        return None
    target = await db.scalar(
        select(StudentTargetGradeGoal).where(
            StudentTargetGradeGoal.student_id == student_id,
            StudentTargetGradeGoal.module_id == module_id,
            StudentTargetGradeGoal.status == "active",
        )
    )
    boundaries = (
        await db.execute(
            select(GradeBoundary.letter_grade, GradeBoundary.lower_bound)
            .where(GradeBoundary.scheme_id == scheme.id)
            .order_by(GradeBoundary.lower_bound.desc())
        )
    ).all()
    components = (
        await db.execute(
            select(
                GradeComponent.id,
                GradeComponent.weight,
                StudentGradeRecord.percentage_score,
            )
            .outerjoin(
                StudentGradeRecord,
                and_(
                    StudentGradeRecord.grade_component_id == GradeComponent.id,
                    StudentGradeRecord.student_id == student_id,
                ),
            )
            .where(
                GradeComponent.scheme_id == scheme.id,
                # A component tied to a non-visible section must not move the forecast the student reads.
                # Carve-out: a scheme-level component (module_section_id NULL) is legitimately section-less
                # and MUST still count — so this is an OR, not a blanket inner join.
                or_(
                    GradeComponent.module_section_id.is_(None),
                    visible_section_exists(
                        GradeComponent.module_section_id, student_id=student_id
                    ),
                ),
            )
            .order_by(GradeComponent.sort_order.asc(), GradeComponent.id.asc())
        )
    ).all()
    return GradeForecastInputs(
        target_letter_grade=target.target_letter_grade if target else None,
        on_track_max=scheme.on_track_max,
        at_risk_max=scheme.at_risk_max,
        boundaries=[(row.letter_grade, row.lower_bound) for row in boundaries],
        components=[
            GradeComponentScore(
                id=row.id,
                weight=row.weight,
                percentage_score=row.percentage_score,
            )
            for row in components
        ],
    )


async def get_workload_module_context(
    db: AsyncSession,
    *,
    module_id: UUID,
    source_cutoff_at: datetime,
) -> WorkloadModuleContext | None:
    module = await db.get(CourseModule, module_id)
    if module is None or not module.is_active:
        return None
    rows = (
        await db.execute(
            select(
                ModuleSection.id,
                ModuleSection.title,
                ModuleSection.type,
                ModuleSection.week_number,
                ModuleSection.due_at,
            )
            .where(
                ModuleSection.course_module_id == module_id,
                # Student-facing workload deadlines use the shared section-level half of the visibility
                # gate. Membership/module activity is caller-enforced (`student_has_module`), while this
                # read enumerates ModuleSection 1:many and therefore cannot use the 1:1 join gate.
                *published_active_section_conditions(),
                ModuleSection.due_at.is_not(None),
                ModuleSection.due_at >= source_cutoff_at,
            )
            .order_by(ModuleSection.due_at.asc(), ModuleSection.id.asc())
        )
    ).all()
    return WorkloadModuleContext(
        module_id=module.id,
        module_title=module.title,
        timezone=module.timezone,
        ends_on=module.ends_on,
        deadlines=[
            WorkloadDeadlineRead(
                section_id=row.id,
                title=row.title,
                section_type=row.type,
                week_number=row.week_number,
                due_at=row.due_at,
            )
            for row in rows
        ],
    )


async def latest_risk_snapshot(
    db: AsyncSession,
    *,
    student_id: UUID,
    module_id: UUID,
) -> LatestRiskSnapshotRead | None:
    row = await db.scalar(
        select(StudentRiskSnapshot)
        .where(
            StudentRiskSnapshot.student_id == student_id,
            StudentRiskSnapshot.module_id == module_id,
        )
        .order_by(
            StudentRiskSnapshot.computed_at.desc(),
            StudentRiskSnapshot.created_at.desc(),
            StudentRiskSnapshot.id.desc(),
        )
        .limit(1)
    )
    if row is None:
        return None
    return LatestRiskSnapshotRead(
        id=row.id,
        risk_reasons=row.risk_reasons,
        input_hash=row.input_hash,
        source_cutoff_at=row.source_cutoff_at,
    )


async def get_workload_forecast_context(
    db: AsyncSession,
    *,
    student_id: UUID,
    module_id: UUID,
) -> dict:
    forecast = await get_grade_forecast_inputs(db, student_id=student_id, module_id=module_id)
    latest_progress = await db.scalar(
        select(StudentProgressSnapshot)
        .where(
            StudentProgressSnapshot.student_id == student_id,
            StudentProgressSnapshot.module_id == module_id,
        )
        .order_by(StudentProgressSnapshot.week_number.desc(), StudentProgressSnapshot.calculated_at.desc())
        .limit(1)
    )
    return {
        "targetLetterGrade": forecast.target_letter_grade if forecast else None,
        "boundaries": [
            {"letterGrade": letter, "lowerBound": lower}
            for letter, lower in (forecast.boundaries if forecast else [])
        ],
        "components": [
            {
                "id": component.id,
                "weight": component.weight,
                "percentageScore": component.percentage_score,
            }
            for component in (forecast.components if forecast else [])
        ],
        "latestProgress": None
        if latest_progress is None
        else {
            "weekNumber": latest_progress.week_number,
            "snapshotDate": latest_progress.snapshot_date,
            "standingPoints": latest_progress.standing_points,
            "calculatedAt": latest_progress.calculated_at,
        },
    }


async def count_missed_recent_quizzes(
    db: AsyncSession,
    *,
    student_id: UUID,
    module_id: UUID,
    limit: int,
    source_cutoff_at: datetime,
) -> int:
    definitions = (
        await db.scalars(
            select(QuizDefinition.id)
            .where(
                QuizDefinition.module_id == module_id,
                QuizDefinition.created_at <= source_cutoff_at,
                # A quiz pinned to a non-visible section (unpublished / inactive-module / lost-membership)
                # must not count toward the student's "missed recent quizzes" — that would let the section's
                # existence influence the student's risk tier. A section-less quiz (recap / exam_prep /
                # mistakes_bank, module_section_id NULL) carries no section identity and still counts.
                or_(
                    QuizDefinition.module_section_id.is_(None),
                    visible_section_exists(
                        QuizDefinition.module_section_id, student_id=student_id
                    ),
                ),
            )
            .order_by(QuizDefinition.created_at.desc(), QuizDefinition.id.desc())
            .limit(limit)
        )
    ).all()
    if not definitions:
        return 0
    completed = (
        await db.scalars(
            select(QuizAttempt.quiz_definition_id).where(
                QuizAttempt.student_id == student_id,
                QuizAttempt.quiz_definition_id.in_(definitions),
                QuizAttempt.status == "completed",
                QuizAttempt.completed_at <= source_cutoff_at,
            )
        )
    ).all()
    return len(set(definitions) - set(completed))


async def list_recent_quiz_scores(
    db: AsyncSession,
    *,
    student_id: UUID,
    module_id: UUID,
    limit: int,
    source_cutoff_at: datetime,
) -> list[Decimal]:
    rows = (
        await db.scalars(
            select(QuizAttempt.score_percentage)
            .join(QuizDefinition, QuizDefinition.id == QuizAttempt.quiz_definition_id)
            .where(
                QuizDefinition.module_id == module_id,
                QuizAttempt.student_id == student_id,
                QuizAttempt.status == "completed",
                QuizAttempt.score_percentage.is_not(None),
                QuizAttempt.completed_at <= source_cutoff_at,
            )
            .order_by(QuizAttempt.completed_at.desc(), QuizAttempt.id.desc())
            .limit(limit)
        )
    ).all()
    return [Decimal(row) for row in rows if row is not None]


async def latest_activity_at(
    db: AsyncSession,
    *,
    student_id: UUID,
    module_id: UUID,
    source_cutoff_at: datetime,
    event_types: Sequence[str],
) -> datetime | None:
    # Only events whose type is in the explicit qualifying set (config-backed RISK_ACTIVITY_EVENT_TYPES,
    # incl. the content-domain `studied_section`) reset the inactivity clock. Reading the shared activity
    # spine by event_type is intentional and carries NO gamification-domain dependency.
    return await db.scalar(
        select(func.max(StudentActivityEvent.occurred_at)).where(
            StudentActivityEvent.student_id == student_id,
            StudentActivityEvent.module_id == module_id,
            StudentActivityEvent.event_type.in_(tuple(event_types)),
            StudentActivityEvent.occurred_at <= source_cutoff_at,
        )
    )


async def has_upcoming_work(
    db: AsyncSession,
    *,
    module_id: UUID,
    source_cutoff_at: datetime,
) -> bool:
    return bool(
        await db.scalar(
            select(ModuleSection.id)
            .where(
                ModuleSection.course_module_id == module_id,
                # Upcoming work is student-facing risk input; unpublished/inactive sections must not flip
                # the student's inactivity reason or risk tier.
                *published_active_section_conditions(),
                ModuleSection.due_at.is_not(None),
                ModuleSection.due_at > source_cutoff_at,
            )
            .limit(1)
        )
    )


async def earliest_topic_deadline_gap(
    db: AsyncSession,
    *,
    student_id: UUID,
    module_id: UUID,
    source_cutoff_at: datetime,
    within_hours: int,
) -> TopicDeadlineGap | None:
    deadline_cutoff = source_cutoff_at + timedelta(hours=within_hours)
    # Route the snapshot→section join through the canonical visibility gate (published + active section +
    # active module + active student membership). Without it a topic mastered on a section that is now
    # unpublished leaks the section's title verbatim into the student's risk reason / recommendation text
    # (and is frozen into StudentRiskSnapshot by the scheduler). Mirrors progress_read.list_topic_mastery.
    stmt = apply_visible_section_gate(
        select(ModuleSection.title, ModuleSection.due_at)
        .select_from(StudentTopicMasterySnapshot)
        .where(
            StudentTopicMasterySnapshot.student_id == student_id,
            StudentTopicMasterySnapshot.module_id == module_id,
            StudentTopicMasterySnapshot.status_label == "needs_attention",
            ModuleSection.due_at.is_not(None),
            ModuleSection.due_at > source_cutoff_at,
            ModuleSection.due_at <= deadline_cutoff,
        ),
        student_id=student_id,
        section_id_col=StudentTopicMasterySnapshot.module_section_id,
    ).order_by(ModuleSection.due_at.asc(), ModuleSection.id.asc()).limit(1)
    row = (await db.execute(stmt)).one_or_none()
    if row is None:
        return None
    return TopicDeadlineGap(title=row.title, due_at=row.due_at)


async def _assessment_answer_rows(db: AsyncSession, *, module_id: UUID) -> list[_AssessmentAnswerRow]:
    selected = AnswerOption
    rows = (
        await db.execute(
            select(
                QuizQuestion.id.label("question_id"),
                QuizQuestion.question_text,
                QuizQuestion.source_pool_question_id,
                QuizQuestion.source_module_id,
                QuizQuestion.source_section_id,
                QuizQuestion.source_summary_id,
                GeneratedLectureSummary.module_section_id.label("summary_section_id"),
                selected.text.label("selected_option_text"),
                StudentAnswer.is_correct,
            )
            .select_from(StudentAnswer)
            .join(QuizQuestion, QuizQuestion.id == StudentAnswer.quiz_question_id)
            .join(QuizAttempt, QuizAttempt.id == StudentAnswer.quiz_attempt_id)
            .join(QuizDefinition, QuizDefinition.id == QuizAttempt.quiz_definition_id)
            .join(selected, selected.id == StudentAnswer.selected_answer_option_id)
            .outerjoin(GeneratedLectureSummary, GeneratedLectureSummary.id == QuizQuestion.source_summary_id)
            .where(
                QuizDefinition.module_id == module_id,
                QuizAttempt.status == "completed",
            )
            .order_by(QuizQuestion.display_order.asc(), QuizQuestion.question_text.asc(), selected.display_order.asc())
        )
    ).all()
    return [
        _AssessmentAnswerRow(
            question_id=row.question_id,
            question_text=row.question_text,
            source_pool_question_id=row.source_pool_question_id,
            source_module_id=row.source_module_id,
            source_section_id=row.source_section_id,
            source_summary_id=row.source_summary_id,
            summary_section_id=row.summary_section_id,
            selected_option_text=row.selected_option_text,
            is_correct=row.is_correct,
        )
        for row in rows
    ]


async def _answer_option_shape_by_question(
    db: AsyncSession,
    *,
    question_ids: set[UUID],
) -> dict[UUID, tuple[tuple[str, bool], ...]]:
    if not question_ids:
        return {}
    rows = (
        await db.execute(
            select(AnswerOption.quiz_question_id, AnswerOption.text, AnswerOption.is_correct)
            .where(AnswerOption.quiz_question_id.in_(question_ids))
            .order_by(AnswerOption.quiz_question_id.asc(), AnswerOption.text.asc(), AnswerOption.is_correct.desc())
        )
    ).all()
    shaped: dict[UUID, list[tuple[str, bool]]] = defaultdict(list)
    for row in rows:
        shaped[row.quiz_question_id].append((_normalize_text(row.text), bool(row.is_correct)))
    return {question_id: tuple(options) for question_id, options in shaped.items()}


async def _section_labels(
    db: AsyncSession,
    *,
    module_id: UUID,
    section_ids: set[UUID],
) -> dict[UUID, tuple[str, int | None]]:
    if not section_ids:
        return {}
    rows = (
        await db.execute(
            select(ModuleSection.id, ModuleSection.title, ModuleSection.week_number)
            .where(
                ModuleSection.id.in_(section_ids),
                ModuleSection.course_module_id == module_id,
            )
            .order_by(ModuleSection.week_number.asc().nullslast(), ModuleSection.title.asc())
        )
    ).all()
    return {row.id: (row.title, row.week_number) for row in rows}


async def _latest_agent_run_for_module(
    db: AsyncSession,
    *,
    module_id: UUID,
) -> AssessmentAgentRunSummary | None:
    row = await db.scalar(
        select(AgentRun)
        .where(
            (AgentRun.scope_type == "all")
            | ((AgentRun.scope_type == "module") & (AgentRun.scope_id == module_id))
        )
        .order_by(
            AgentRun.completed_at.desc().nullslast(),
            AgentRun.scheduled_for.desc(),
            AgentRun.created_at.desc(),
        )
        .limit(1)
    )
    if row is None:
        return None
    return AssessmentAgentRunSummary(
        id=row.id,
        status=row.status,
        scope_type=row.scope_type,
        scope_id=row.scope_id,
        scheduled_for=row.scheduled_for,
        completed_at=row.completed_at,
        snapshot_count=row.snapshot_count,
        recommendation_count=row.recommendation_count,
    )


def _question_key(
    row: _AssessmentAnswerRow,
    option_shape: tuple[tuple[str, bool], ...],
) -> str:
    if row.source_pool_question_id is not None:
        return f"pool:{row.source_pool_question_id}"
    payload = {
        "questionText": _normalize_text(row.question_text),
        "sourceModuleId": str(row.source_module_id) if row.source_module_id else None,
        "sourceSectionId": str(row.source_section_id) if row.source_section_id else None,
        "sourceSummaryId": str(row.source_summary_id) if row.source_summary_id else None,
        "optionShape": option_shape,
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:24]
    return f"snapshot:{digest}"


def _option_key(question_key: str, option_text: str) -> str:
    digest = hashlib.sha256(
        json.dumps(
            {"questionKey": question_key, "optionText": _normalize_text(option_text)},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()[:16]
    return f"option:{digest}"


def _topic_section_id(row: _AssessmentAnswerRow) -> UUID | None:
    return row.source_section_id or row.summary_section_id


def _render_question_insight(question: dict) -> AssessmentQuestionInsight:
    answer_count = question["answer_count"]
    small_cohort = answer_count < SMALL_COHORT_THRESHOLD
    distractors = [
        AssessmentDistractorInsight(
            option_key=distractor["option_key"],
            option_text=distractor["option_text"],
            selected_count=distractor["selected_count"],
            selected_rate_percent=None
            if small_cohort
            else _percent(distractor["selected_count"], answer_count),
        )
        for distractor in question["distractors"].values()
    ]
    distractors.sort(key=lambda item: (-item.selected_count, item.option_text.casefold(), item.option_key))
    return AssessmentQuestionInsight(
        question_key=question["question_key"],
        question_text=question["question_text"],
        answer_count=answer_count,
        correct_count=question["correct_count"],
        incorrect_count=question["incorrect_count"],
        correct_rate_percent=None if small_cohort else _percent(question["correct_count"], answer_count),
        small_cohort=small_cohort,
        small_cohort_message=SMALL_COHORT_MESSAGE if small_cohort else None,
        distractors=distractors,
    )


def _render_topic_mastery_row(
    section_id: UUID,
    counts: dict[str, int],
    section_labels: dict[UUID, tuple[str, int | None]],
) -> AssessmentTopicMasteryRow:
    answer_count = counts["answer_count"]
    correct_count = counts["correct_count"]
    small_cohort = answer_count < SMALL_COHORT_THRESHOLD
    title, week_number = section_labels.get(section_id, ("Unknown topic", None))
    return AssessmentTopicMasteryRow(
        source_section_id=section_id,
        topic_title=title,
        week_number=week_number,
        answer_count=answer_count,
        correct_count=correct_count,
        mastery_percent=None if small_cohort else _percent(correct_count, answer_count),
        small_cohort=small_cohort,
        small_cohort_message=SMALL_COHORT_MESSAGE if small_cohort else None,
    )


def _percent(numerator: int, denominator: int) -> Decimal:
    if denominator <= 0:
        return Decimal("0.00")
    return (Decimal(numerator) * Decimal("100") / Decimal(denominator)).quantize(Decimal("0.01"))


def _normalize_text(value: str) -> str:
    return " ".join(value.casefold().split())
