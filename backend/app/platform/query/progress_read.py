from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.db.models import (
    CourseGradeScheme,
    CourseMembership,
    CourseModule,
    GradeBoundary,
    GradeComponent,
    ModuleSection,
    QuizAttempt,
    QuizDefinition,
    StudentGradeRecord,
    StudentProgressSnapshot,
    StudentTargetGradeGoal,
    StudentTopicMasterySnapshot,
)


@dataclass(frozen=True)
class GradeComponentRow:
    id: UUID
    name: str
    weight: Decimal
    sort_order: int
    percentage_score: Decimal | None


@dataclass(frozen=True)
class GradeSchemeBundle:
    scheme: CourseGradeScheme
    boundaries: list[GradeBoundary]
    components: list[GradeComponentRow]


async def list_student_progress_modules(db: AsyncSession, *, student_id: UUID) -> list[CourseModule]:
    return (
        await db.scalars(
            select(CourseModule)
            .join(CourseMembership, CourseMembership.module_id == CourseModule.id)
            .where(
                CourseMembership.user_id == student_id,
                CourseMembership.role == "student",
                CourseMembership.status == "active",
                CourseModule.is_active.is_(True),
            )
            .order_by(CourseModule.created_at.desc(), CourseModule.id.desc())
        )
    ).all()


async def get_visible_student_module(
    db: AsyncSession,
    *,
    student_id: UUID,
    module_id: UUID,
) -> CourseModule | None:
    return await db.scalar(
        select(CourseModule)
        .join(CourseMembership, CourseMembership.module_id == CourseModule.id)
        .where(
            CourseModule.id == module_id,
            CourseMembership.user_id == student_id,
            CourseMembership.role == "student",
            CourseMembership.status == "active",
            CourseModule.is_active.is_(True),
        )
    )


async def get_grade_scheme_bundle(
    db: AsyncSession,
    *,
    student_id: UUID,
    module_id: UUID,
) -> GradeSchemeBundle | None:
    scheme = await db.scalar(select(CourseGradeScheme).where(CourseGradeScheme.module_id == module_id))
    if scheme is None:
        return None

    boundaries = (
        await db.scalars(
            select(GradeBoundary)
            .where(GradeBoundary.scheme_id == scheme.id)
            .order_by(GradeBoundary.lower_bound.desc(), GradeBoundary.sort_order.asc())
        )
    ).all()
    component_rows = (
        await db.execute(
            select(
                GradeComponent.id,
                GradeComponent.name,
                GradeComponent.weight,
                GradeComponent.sort_order,
                StudentGradeRecord.percentage_score,
            )
            .outerjoin(
                StudentGradeRecord,
                and_(
                    StudentGradeRecord.grade_component_id == GradeComponent.id,
                    StudentGradeRecord.student_id == student_id,
                ),
            )
            .where(GradeComponent.scheme_id == scheme.id)
            .order_by(GradeComponent.sort_order.asc(), GradeComponent.id.asc())
        )
    ).all()
    components = [
        GradeComponentRow(
            id=row.id,
            name=row.name,
            weight=row.weight,
            sort_order=row.sort_order,
            percentage_score=row.percentage_score,
        )
        for row in component_rows
    ]
    return GradeSchemeBundle(scheme=scheme, boundaries=list(boundaries), components=components)


async def get_active_target_goal(
    db: AsyncSession,
    *,
    student_id: UUID,
    module_id: UUID,
) -> StudentTargetGradeGoal | None:
    return await db.scalar(
        select(StudentTargetGradeGoal).where(
            StudentTargetGradeGoal.student_id == student_id,
            StudentTargetGradeGoal.module_id == module_id,
            StudentTargetGradeGoal.status == "active",
        )
    )


async def list_progress_snapshots(
    db: AsyncSession,
    *,
    student_id: UUID,
    module_id: UUID,
) -> list[StudentProgressSnapshot]:
    return (
        await db.scalars(
            select(StudentProgressSnapshot)
            .where(
                StudentProgressSnapshot.student_id == student_id,
                StudentProgressSnapshot.module_id == module_id,
            )
            .order_by(StudentProgressSnapshot.week_number.asc())
        )
    ).all()


async def list_topic_mastery(
    db: AsyncSession,
    *,
    student_id: UUID,
    module_id: UUID,
) -> list[tuple[StudentTopicMasterySnapshot, ModuleSection]]:
    rows = (
        await db.execute(
            select(StudentTopicMasterySnapshot, ModuleSection)
            .join(ModuleSection, ModuleSection.id == StudentTopicMasterySnapshot.module_section_id)
            .where(
                StudentTopicMasterySnapshot.student_id == student_id,
                StudentTopicMasterySnapshot.module_id == module_id,
                ModuleSection.status == "active",
                ModuleSection.type.in_(("lecture", "lab")),
            )
            .order_by(ModuleSection.week_number.asc().nulls_last(), ModuleSection.order_index.asc())
        )
    ).all()
    return [(row[0], row[1]) for row in rows]


async def get_quiz_average_benchmark(
    db: AsyncSession,
    *,
    student_id: UUID,
    module_id: UUID,
) -> tuple[Decimal | None, Decimal | None, int]:
    student_average = await db.scalar(
        select(func.avg(QuizAttempt.score_percentage))
        .join(QuizDefinition, QuizDefinition.id == QuizAttempt.quiz_definition_id)
        .where(
            QuizDefinition.module_id == module_id,
            QuizAttempt.student_id == student_id,
            QuizAttempt.status == "completed",
            QuizAttempt.score_percentage.is_not(None),
        )
    )
    cohort_row = (
        await db.execute(
            select(
                func.avg(QuizAttempt.score_percentage),
                func.count(func.distinct(QuizAttempt.student_id)),
            )
            .join(QuizDefinition, QuizDefinition.id == QuizAttempt.quiz_definition_id)
            .join(CourseMembership, CourseMembership.user_id == QuizAttempt.student_id)
            .where(
                QuizDefinition.module_id == module_id,
                CourseMembership.module_id == module_id,
                CourseMembership.role == "student",
                CourseMembership.status == "active",
                QuizAttempt.status == "completed",
                QuizAttempt.score_percentage.is_not(None),
            )
        )
    ).one()
    return student_average, cohort_row[0], int(cohort_row[1] or 0)
