"""The single, shared student section-visibility gate (Stage 10.x security fix).

Canonical definition mirrored from ``student_summary_read.get_visible_student_section`` (the §8.6
student-facing read): a section is visible to a student iff it is ``published`` + ``active`` in an
``active`` module the student is an ``active`` student-member of. Any read that COUNTS or LISTS sections
feeding student-visible output (badges, progress, mastery, risk, recommendations, workload, forecast)
must route through this one helper so a future read cannot silently omit a condition — that omission is
exactly the leak class this fix closes.

Two shapes are provided so a caller never has to re-spell the predicate:

* ``apply_visible_section_gate`` — INNER-joins ``ModuleSection`` (+ module + membership) onto a statement
  whose rows each reference exactly one section. Use when every row MUST have a visible section (badges,
  mastery lists, deadline lookups).
* ``visible_section_exists`` — an EXISTS() predicate for the carve-out case where a row may legitimately
  have NO section (a scheme-level grade component, a module-level quiz). Pair it with an ``IS NULL`` arm,
  e.g. ``or_(col.is_(None), visible_section_exists(col, student_id=...))`` so section-less rows still
  count while rows pinned to a non-visible section are excluded.

NOTE: this gate is deliberately NOT applied to the scheduled-day reads (a future class DATE may surface
before its section publishes — a schedule date, not hidden content; by design) nor to event-derived
counts (those count only activity the student already performed behind the published gate).
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import ColumnElement, select
from sqlalchemy.sql import Select

from app.platform.db.models import CourseMembership, CourseModule, ModuleSection


def _visible_section_predicates(student_id: UUID) -> tuple[ColumnElement[bool], ...]:
    """The canonical "section is visible to this student" predicate, in ONE place. Both the join gate
    and the EXISTS helper consume it so they can never drift apart."""
    return (
        ModuleSection.publish_status == "published",
        ModuleSection.status == "active",
        CourseModule.is_active.is_(True),
        CourseMembership.user_id == student_id,
        CourseMembership.role == "student",
        CourseMembership.status == "active",
    )


def apply_visible_section_gate(
    stmt: Select,
    *,
    student_id: UUID,
    section_id_col: ColumnElement[UUID],
) -> Select:
    """Constrain ``stmt`` to sections the student may actually see, joining ``ModuleSection`` on
    ``section_id_col`` and applying the canonical published + active-section + active-module +
    active-student-membership predicate. Returns the augmented statement (the caller keeps any other
    filters / ordering it needs)."""
    return (
        stmt.join(ModuleSection, ModuleSection.id == section_id_col)
        .join(CourseModule, CourseModule.id == ModuleSection.course_module_id)
        .join(CourseMembership, CourseMembership.module_id == CourseModule.id)
        .where(*_visible_section_predicates(student_id))
    )


def visible_section_exists(
    section_id_col: ColumnElement[UUID],
    *,
    student_id: UUID,
) -> ColumnElement[bool]:
    """An EXISTS() predicate that is true iff ``section_id_col`` points at a section the student may see.

    For carve-out reads where a NULL section must STILL pass (scheme-level grade components,
    module-level quizzes), combine with the IS NULL arm::

        or_(SomeModel.module_section_id.is_(None),
            visible_section_exists(SomeModel.module_section_id, student_id=student_id))
    """
    return (
        select(ModuleSection.id)
        .join(CourseModule, CourseModule.id == ModuleSection.course_module_id)
        .join(CourseMembership, CourseMembership.module_id == CourseModule.id)
        .where(ModuleSection.id == section_id_col, *_visible_section_predicates(student_id))
        .exists()
    )
