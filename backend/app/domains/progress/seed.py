from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid6 import uuid7

from app.platform.db.models import (
    AppUser,
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


GRADE_BOUNDARIES: tuple[tuple[str, Decimal], ...] = (
    ("A", Decimal("93.00")),
    ("A-", Decimal("87.00")),
    ("B+", Decimal("84.00")),
    ("B", Decimal("80.00")),
    ("C+", Decimal("75.00")),
    ("C", Decimal("70.00")),
    ("D", Decimal("60.00")),
    ("F", Decimal("0.00")),
)


@dataclass(frozen=True)
class Stage9SeedSummary:
    module_one_id: UUID
    module_two_id: UUID
    student_ids_by_key: dict[str, UUID]
    student_emails_by_key: dict[str, str]


async def seed_progress_dataset(
    db: AsyncSession,
    *,
    prefix: str,
    reset: bool,
    cohort_size: int = 6,
    source: str = "e2e",
) -> Stage9SeedSummary:
    if cohort_size < 6:
        raise ValueError("cohort_size must be at least 6 to realize the scenario matrix")
    if reset:
        await _delete_existing(db, prefix=prefix)

    lecturer = await _create_user(db, prefix=prefix, key="lecturer", role="lecturer")
    students = [
        await _create_user(db, prefix=prefix, key=f"student-{letter}", role="student")
        for letter in ("a", "b", "c", "d", "e", "f")
    ]
    for index in range(6, cohort_size):
        students.append(
            await _create_user(db, prefix=prefix, key=f"student-{index + 1}", role="student")
        )

    module_one = CourseModule(
        title=f"{prefix} Module 1 Progress",
        description="Stage 9 seeded progress module",
        owner_id=lecturer.id,
        timezone="UTC",
        starts_on=date(2026, 1, 12),
        ends_on=date(2026, 5, 1),
        is_active=True,
    )
    module_two = CourseModule(
        title=f"{prefix} Module 2 Progress",
        description="Stage 9 seeded progress module",
        owner_id=lecturer.id,
        timezone="UTC",
        starts_on=date(2026, 1, 12),
        ends_on=date(2026, 5, 1),
        is_active=True,
    )
    db.add_all([module_one, module_two])
    await db.flush()

    db.add_all(
        [
            CourseMembership(user_id=lecturer.id, module_id=module_one.id, role="lecturer", status="active"),
            CourseMembership(user_id=lecturer.id, module_id=module_two.id, role="lecturer", status="active"),
            *[
                CourseMembership(
                    user_id=student.id,
                    module_id=module_one.id,
                    role="student",
                    status="active",
                )
                for student in students
            ],
            *[
                CourseMembership(
                    user_id=student.id,
                    module_id=module_two.id,
                    role="student",
                    status="active",
                )
                for student in students
            ],
        ]
    )
    sections_one = await _create_sections(db, module_one.id, "M1")
    sections_two = await _create_sections(db, module_two.id, "M2")
    scheme_one, components_one = await _create_scheme(
        db,
        module_id=module_one.id,
        name="Stage 9 module 1 scheme",
        components=(
            ("Quiz average", Decimal("0.20"), "quiz", sections_one[0].id),
            ("Lab portfolio", Decimal("0.20"), "lab", sections_one[1].id),
            ("Midterm", Decimal("0.25"), "exam", None),
            ("Assignments", Decimal("0.25"), "assignment", None),
            ("Final exam", Decimal("0.10"), "exam", None),
        ),
    )
    scheme_two, components_two = await _create_scheme(
        db,
        module_id=module_two.id,
        name="Stage 9 module 2 scheme",
        components=(
            ("Quiz average", Decimal("0.20"), "quiz", sections_two[0].id),
            ("Lab portfolio", Decimal("0.20"), "lab", sections_two[1].id),
            ("Project", Decimal("0.20"), "assignment", None),
            ("Midterm", Decimal("0.20"), "exam", None),
            ("Final exam", Decimal("0.20"), "exam", None),
        ),
    )
    await db.flush()

    del scheme_one, scheme_two
    await _seed_matrix(
        db,
        students=students,
        module_one_id=module_one.id,
        module_two_id=module_two.id,
        components_one=components_one,
        components_two=components_two,
        sections_one=sections_one,
        sections_two=sections_two,
        source=source,
    )
    await _seed_quiz_benchmark(
        db,
        students=students,
        module=module_one,
        section=sections_one[0],
        scores=[Decimal("82"), Decimal("88"), Decimal("91"), Decimal("74"), Decimal("86"), Decimal("85")],
    )
    await _seed_quiz_benchmark(
        db,
        students=students,
        module=module_two,
        section=sections_two[0],
        scores=[Decimal("79"), Decimal("81"), Decimal("84"), Decimal("70"), Decimal("77"), Decimal("80")],
    )
    await db.commit()

    keys = ["a", "b", "c", "d", "e", "f"]
    return Stage9SeedSummary(
        module_one_id=module_one.id,
        module_two_id=module_two.id,
        student_ids_by_key={key: student.id for key, student in zip(keys, students, strict=False)},
        student_emails_by_key={key: student.email for key, student in zip(keys, students, strict=False)},
    )


async def _delete_existing(db: AsyncSession, *, prefix: str) -> None:
    module_ids = select(CourseModule.id).where(CourseModule.title.like(f"{prefix} Module %"))
    user_ids = select(AppUser.id).where(AppUser.email.like(f"{prefix}-%@example.test"))
    scheme_ids = select(CourseGradeScheme.id).where(CourseGradeScheme.module_id.in_(module_ids))
    component_ids = select(GradeComponent.id).where(GradeComponent.scheme_id.in_(scheme_ids))
    quiz_definition_ids = select(QuizDefinition.id).where(QuizDefinition.module_id.in_(module_ids))

    await db.execute(delete(QuizAttempt).where(QuizAttempt.quiz_definition_id.in_(quiz_definition_ids)))
    await db.execute(delete(QuizAttempt).where(QuizAttempt.student_id.in_(user_ids)))
    await db.execute(delete(QuizDefinition).where(QuizDefinition.id.in_(quiz_definition_ids)))
    await db.execute(delete(StudentGradeRecord).where(StudentGradeRecord.grade_component_id.in_(component_ids)))
    await db.execute(delete(StudentGradeRecord).where(StudentGradeRecord.student_id.in_(user_ids)))
    await db.execute(delete(CourseGradeScheme).where(CourseGradeScheme.id.in_(scheme_ids)))
    await db.execute(delete(StudentTargetGradeGoal).where(StudentTargetGradeGoal.module_id.in_(module_ids)))
    await db.execute(delete(StudentTargetGradeGoal).where(StudentTargetGradeGoal.student_id.in_(user_ids)))
    await db.execute(delete(StudentTopicMasterySnapshot).where(StudentTopicMasterySnapshot.module_id.in_(module_ids)))
    await db.execute(delete(StudentTopicMasterySnapshot).where(StudentTopicMasterySnapshot.student_id.in_(user_ids)))
    await db.execute(delete(StudentProgressSnapshot).where(StudentProgressSnapshot.module_id.in_(module_ids)))
    await db.execute(delete(StudentProgressSnapshot).where(StudentProgressSnapshot.student_id.in_(user_ids)))
    await db.execute(delete(CourseMembership).where(CourseMembership.module_id.in_(module_ids)))
    await db.execute(delete(CourseMembership).where(CourseMembership.user_id.in_(user_ids)))
    await db.execute(delete(ModuleSection).where(ModuleSection.course_module_id.in_(module_ids)))
    await db.execute(delete(CourseModule).where(CourseModule.id.in_(module_ids)))
    await db.execute(delete(AppUser).where(AppUser.id.in_(user_ids)))
    await db.flush()


async def _create_user(db: AsyncSession, *, prefix: str, key: str, role: str) -> AppUser:
    email = f"{prefix}-{key}@example.test"
    user = AppUser(
        auth_provider_id=f"{prefix}-{key}",
        email=email,
        full_name=f"Stage 9 {key.replace('-', ' ').title()}",
        role=role,
        is_active=True,
        timezone="UTC",
    )
    db.add(user)
    await db.flush()
    return user


async def _create_sections(db: AsyncSession, module_id: UUID, label: str) -> list[ModuleSection]:
    sections = [
        ModuleSection(
            course_module_id=module_id,
            title=f"{label} Financial Modelling",
            type="lecture",
            order_index=1,
            week_number=1,
            session_date=date(2026, 1, 12),
            publish_status="published",
            status="active",
        ),
        ModuleSection(
            course_module_id=module_id,
            title=f"{label} Applied Lab",
            type="lab",
            order_index=2,
            week_number=1,
            session_date=date(2026, 1, 13),
            publish_status="published",
            status="active",
        ),
    ]
    db.add_all(sections)
    await db.flush()
    return sections


async def _create_scheme(
    db: AsyncSession,
    *,
    module_id: UUID,
    name: str,
    components: tuple[tuple[str, Decimal, str, UUID | None], ...],
) -> tuple[CourseGradeScheme, list[GradeComponent]]:
    scheme = CourseGradeScheme(
        module_id=module_id,
        name=name,
        on_track_max=Decimal("70.00"),
        at_risk_max=Decimal("85.00"),
        benchmark_min_cohort=5,
    )
    db.add(scheme)
    await db.flush()
    db.add_all(
        [
            GradeBoundary(
                scheme_id=scheme.id,
                letter_grade=letter,
                lower_bound=lower,
                sort_order=index + 1,
            )
            for index, (letter, lower) in enumerate(GRADE_BOUNDARIES)
        ]
    )
    grade_components = [
        GradeComponent(
            scheme_id=scheme.id,
            name=component_name,
            weight=weight,
            sort_order=index + 1,
            component_kind=kind,
            module_section_id=section_id,
        )
        for index, (component_name, weight, kind, section_id) in enumerate(components)
    ]
    db.add_all(grade_components)
    await db.flush()
    return scheme, grade_components


async def _seed_matrix(
    db: AsyncSession,
    *,
    students: list[AppUser],
    module_one_id: UUID,
    module_two_id: UUID,
    components_one: list[GradeComponent],
    components_two: list[GradeComponent],
    sections_one: list[ModuleSection],
    sections_two: list[ModuleSection],
    source: str,
) -> None:
    # A: on_track, B: at_risk, E: achieved, F: final_no_remaining on module 1.
    await _grade_first_components(db, students[0].id, components_one, Decimal("89.44"), 4, source)
    await _grade_first_components(db, students[1].id, components_one, Decimal("94.44"), 4, source)
    await _grade_first_components(db, students[4].id, components_one, Decimal("91.11"), 4, source)
    await _grade_first_components(db, students[5].id, components_one, Decimal("85.00"), 5, source)
    await _target(db, students[0].id, module_one_id, "A-")
    await _target(db, students[1].id, module_one_id, "A")
    await _target(db, students[4].id, module_one_id, "B")
    await _target(db, students[5].id, module_one_id, "A")

    # C: requires_high_score, D: impossible on module 2.
    await _grade_first_components(db, students[2].id, components_two, Decimal("92.50"), 4, source)
    await _grade_first_components(db, students[3].id, components_two, Decimal("82.50"), 4, source)
    await _target(db, students[2].id, module_two_id, "A")
    await _target(db, students[3].id, module_two_id, "A")

    for index, student in enumerate(students):
        await _seed_snapshots(
            db,
            student_id=student.id,
            module_id=module_one_id,
            latest=Decimal("78") + Decimal(index % 8),
            sections=sections_one,
        )
        await _seed_snapshots(
            db,
            student_id=student.id,
            module_id=module_two_id,
            latest=Decimal("72") + Decimal(index % 10),
            sections=sections_two,
        )
        if index >= 6:
            await _grade_first_components(db, student.id, components_one, Decimal("82.00"), 4, source)
            await _grade_first_components(db, student.id, components_two, Decimal("80.00"), 4, source)


async def _grade_first_components(
    db: AsyncSession,
    student_id: UUID,
    components: list[GradeComponent],
    score: Decimal,
    count: int,
    source: str,
) -> None:
    db.add_all(
        [
            StudentGradeRecord(
                student_id=student_id,
                grade_component_id=component.id,
                percentage_score=score,
                source=source,
            )
            for component in components[:count]
        ]
    )


async def _target(db: AsyncSession, student_id: UUID, module_id: UUID, letter: str) -> None:
    db.add(
        StudentTargetGradeGoal(
            student_id=student_id,
            module_id=module_id,
            target_letter_grade=letter,
            status="active",
        )
    )


async def _seed_snapshots(
    db: AsyncSession,
    *,
    student_id: UUID,
    module_id: UUID,
    latest: Decimal,
    sections: list[ModuleSection],
) -> None:
    points = [latest - Decimal("8"), latest - Decimal("4"), latest]
    db.add_all(
        [
            StudentProgressSnapshot(
                student_id=student_id,
                module_id=module_id,
                week_number=index + 1,
                snapshot_date=date(2026, 1, 12 + index * 7),
                standing_points=point,
                source_metrics={"seed": "stage9"},
                calculated_at=datetime.now(UTC),
            )
            for index, point in enumerate(points)
        ]
    )
    db.add_all(
        [
            StudentTopicMasterySnapshot(
                student_id=student_id,
                module_id=module_id,
                module_section_id=sections[0].id,
                mastery_percentage=latest - Decimal("5"),
                status_label="on_track",
                source_metrics={"seed": "stage9"},
                calculated_at=datetime.now(UTC),
            ),
            StudentTopicMasterySnapshot(
                student_id=student_id,
                module_id=module_id,
                module_section_id=sections[1].id,
                mastery_percentage=latest - Decimal("12"),
                status_label="needs_attention",
                source_metrics={"seed": "stage9"},
                calculated_at=datetime.now(UTC),
            ),
        ]
    )


async def _seed_quiz_benchmark(
    db: AsyncSession,
    *,
    students: list[AppUser],
    module: CourseModule,
    section: ModuleSection,
    scores: list[Decimal],
) -> None:
    definition = QuizDefinition(
        module_section_id=section.id,
        module_id=module.id,
        quiz_mode="post_class",
        source_scope={"sectionIds": [str(section.id)]},
    )
    db.add(definition)
    await db.flush()
    now = datetime.now(UTC)
    for index, student in enumerate(students):
        score = scores[index % len(scores)]
        correct = int(score // 10)
        db.add(
            QuizAttempt(
                quiz_definition_id=definition.id,
                student_id=student.id,
                attempt_number=1,
                status="completed",
                total_questions=10,
                new_question_count=10,
                mistake_review_question_count=0,
                correct_count=correct,
                incorrect_count=10 - correct,
                score_percentage=score,
                started_at=now,
                completed_at=now,
            )
        )
