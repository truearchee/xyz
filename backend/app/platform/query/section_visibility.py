"""The single, shared student section-visibility gate (Stage 10.x security fix).

Canonical definition mirrored from ``student_summary_read.get_visible_student_section`` (the §8.6
student-facing read): a section is visible to a student iff it is ``published`` + ``active`` in an
``active`` module the student is an ``active`` student-member of. Any read that COUNTS or LISTS sections
feeding student-visible output (badges, progress, mastery) must route through this one helper so a future
read cannot silently omit a condition — that omission is exactly the leak class this fix closes.

NOTE: this gate is deliberately NOT applied to the scheduled-day reads (a future class DATE may surface
before its section publishes — a schedule date, not hidden content; by design) nor to event-derived
counts (those count only activity the student already performed behind the published gate).
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import ColumnElement
from sqlalchemy.sql import Select

from app.platform.db.models import CourseMembership, CourseModule, ModuleSection


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
        .where(
            ModuleSection.publish_status == "published",
            ModuleSection.status == "active",
            CourseModule.is_active.is_(True),
            CourseMembership.user_id == student_id,
            CourseMembership.role == "student",
            CourseMembership.status == "active",
        )
    )
