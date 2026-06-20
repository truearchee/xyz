"""Scoped student-summary read models (Stage 4.7 §8.6 / §8.1).

Read models ONLY (rule 8): the WHERE clause enforces the already-defined policy — it returns only rows
visible to the requesting student and never makes or invents policy, and never mutates. Zero rows for
unpublished / not-a-member / inactive-membership (the caller maps that to the pinned 404 — never
fetch-then-branch). Membership is MODULE-LEVEL (P2d): ``cm.module_id = section.course_module_id``,
``role='student'``, ``status='active'``, plus the existing published+active-section and active-module
guards so this surface is never MORE permissive than Stage 3 content visibility.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.transcripts.summary_eligibility import is_summary_eligible
from app.platform.db.models import (
    AssistantConversation,
    AssistantMessage,
    CourseMembership,
    CourseModule,
    GeneratedLectureSummary,
    ModuleSection,
    SectionAsset,
    Transcript,
)
from app.platform.query.summary_read import get_latest_transcript_summaries
from app.platform.query.transcript_status import (
    SUMMARY_STEP_KEYS,
    get_transcript_processing_status_read,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class VisibleStudentSection:
    id: UUID
    title: str
    type: str
    order_index: int
    due_at: datetime | None
    lecturer_notes: str | None
    course_module_id: UUID


@dataclass(frozen=True)
class VisibleStudentModule:
    id: UUID
    title: str


@dataclass(frozen=True)
class StudentMaterialRow:
    id: UUID
    file_name: str
    mime_type: str
    file_size: int
    asset_kind: str


@dataclass(frozen=True)
class SectionSummaryInputs:
    """Everything ``precedence.derive_slot_state`` needs for one section's two slots."""

    active_transcript: Transcript | None
    brief_row: GeneratedLectureSummary | None
    detailed_row: GeneratedLectureSummary | None
    overall_state: str | None
    brief_step_status: str | None
    detailed_step_status: str | None


def resolve_single_active(transcripts: list[Transcript], *, section_id: object = None) -> Transcript | None:
    """>1-active fail-safe (§4). A read surface never guesses which content a student is entitled to.

    The ``uq_active_transcript_per_section`` partial-unique index makes >1 impossible at the DB level;
    this is pure defense-in-depth. 0 → None; 1 → the row; >1 → None + a loud log (fail safe).
    """
    if not transcripts:
        return None
    if len(transcripts) > 1:
        logger.error(
            "student-summary data-integrity violation: %d active transcripts for section %s — refusing "
            "to guess; failing safe to no-active",
            len(transcripts),
            section_id,
        )
        return None
    return transcripts[0]


# ---- single section detail (§8.6 scoped query) -----------------------------------------------------
async def get_visible_student_section(
    db: AsyncSession,
    *,
    student_id: UUID,
    section_id: UUID,
) -> VisibleStudentSection | None:
    """The §8.6 scoped query. One row iff the section is published+active in a module the student is an
    active student-member of; otherwise zero rows (caller → pinned 404). No fetch-then-branch."""
    result = await db.execute(
        select(
            ModuleSection.id,
            ModuleSection.title,
            ModuleSection.type,
            ModuleSection.order_index,
            ModuleSection.due_at,
            ModuleSection.lecturer_notes,
            ModuleSection.course_module_id,
        )
        .join(CourseModule, CourseModule.id == ModuleSection.course_module_id)
        .join(CourseMembership, CourseMembership.module_id == CourseModule.id)
        .where(
            ModuleSection.id == section_id,
            ModuleSection.publish_status == "published",
            ModuleSection.status == "active",
            CourseModule.is_active.is_(True),
            CourseMembership.user_id == student_id,
            CourseMembership.role == "student",
            CourseMembership.status == "active",
        )
    )
    row = result.one_or_none()
    if row is None:
        return None
    return VisibleStudentSection(
        id=row.id,
        title=row.title,
        type=row.type,
        order_index=row.order_index,
        due_at=row.due_at,
        lecturer_notes=row.lecturer_notes,
        course_module_id=row.course_module_id,
    )


async def get_visible_student_module(
    db: AsyncSession,
    *,
    student_id: UUID,
    module_id: UUID,
) -> VisibleStudentModule | None:
    """Module-level analogue of ``get_visible_student_section`` (Stage 8.6a). One row iff the module is
    active and the student is an active student-member; otherwise zero rows (caller → pinned 404). Used by
    the homework mode, which binds a MODULE (not a single section). No fetch-then-branch."""
    result = await db.execute(
        select(CourseModule.id, CourseModule.title)
        .join(CourseMembership, CourseMembership.module_id == CourseModule.id)
        .where(
            CourseModule.id == module_id,
            CourseModule.is_active.is_(True),
            CourseMembership.user_id == student_id,
            CourseMembership.role == "student",
            CourseMembership.status == "active",
        )
    )
    row = result.one_or_none()
    if row is None:
        return None
    return VisibleStudentModule(id=row.id, title=row.title)


async def get_student_section_materials(
    db: AsyncSession,
    *,
    section_id: UUID,
) -> list[StudentMaterialRow]:
    """Completed published materials for a section (same safe shape as Stage 3 student assets)."""
    result = await db.execute(
        select(
            SectionAsset.id,
            SectionAsset.file_name,
            SectionAsset.mime_type,
            SectionAsset.file_size,
            SectionAsset.asset_kind,
        )
        .where(
            SectionAsset.module_section_id == section_id,
            SectionAsset.processing_status == "completed",
        )
        .order_by(SectionAsset.created_at.asc(), SectionAsset.id.asc())
    )
    return [
        StudentMaterialRow(
            id=r.id,
            file_name=r.file_name,
            mime_type=r.mime_type,
            file_size=r.file_size,
            asset_kind=r.asset_kind,
        )
        for r in result.all()
    ]


async def get_section_summary_inputs(
    db: AsyncSession,
    *,
    section_id: UUID,
) -> SectionSummaryInputs:
    """Resolve the active transcript (with >1-active fail-safe) + its latest summary rows + the 4.5
    projection step statuses. When there is no active transcript, every field is None (precedence
    resolves that to UNAVAILABLE at step 1)."""
    actives = (
        (
            await db.execute(
                select(Transcript).where(
                    Transcript.module_section_id == section_id,
                    Transcript.lifecycle_state == "active",
                )
            )
        )
        .scalars()
        .all()
    )
    active = resolve_single_active(list(actives), section_id=section_id)
    if active is None:
        return SectionSummaryInputs(None, None, None, None, None, None)

    brief_row, detailed_row = await get_latest_transcript_summaries(db, transcript_id=active.id)
    status_read = await get_transcript_processing_status_read(db, transcript=active)
    return SectionSummaryInputs(
        active_transcript=active,
        brief_row=brief_row,
        detailed_row=detailed_row,
        overall_state=status_read.overall_state,
        brief_step_status=status_read.steps["summary_brief"].status,
        detailed_step_status=status_read.steps["summary_detailed"].status,
    )


# ---- batched module list with coarse flag (§8.1 — no per-section fan-out) ---------------------------
@dataclass(frozen=True)
class StudentSectionListRow:
    id: UUID
    title: str
    type: str
    order_index: int
    lecturer_notes: str | None
    has_materials: bool
    summaries_state: str


async def get_visible_student_section_list(
    db: AsyncSession,
    *,
    student_id: UUID,
    module_id: UUID,
) -> list[StudentSectionListRow]:
    """All published+active sections of ``module_id`` that ``student_id`` actively belongs to, each with
    a COARSE ``summaries_state`` — computed in a handful of batched queries (no per-section fan-out, no
    per-section projection). The section-detail endpoint is authoritative; this is a list hint."""
    from app.domains.student_summaries.precedence import (  # local import avoids a domain↔platform cycle
        LIST_GENERATING,
        LIST_NONE,
        LIST_NOT_APPLICABLE,
        LIST_PARTIAL,
        LIST_READY,
        SUMMARY_SECTION_TYPES,
        _content_is_blank,
    )

    section_rows = (
        await db.execute(
            select(
                ModuleSection.id,
                ModuleSection.title,
                ModuleSection.type,
                ModuleSection.order_index,
                ModuleSection.lecturer_notes,
            )
            .join(CourseModule, CourseModule.id == ModuleSection.course_module_id)
            .join(CourseMembership, CourseMembership.module_id == CourseModule.id)
            .where(
                ModuleSection.course_module_id == module_id,
                ModuleSection.publish_status == "published",
                ModuleSection.status == "active",
                CourseModule.is_active.is_(True),
                CourseMembership.user_id == student_id,
                CourseMembership.role == "student",
                CourseMembership.status == "active",
            )
            .order_by(ModuleSection.order_index.asc())
        )
    ).all()

    section_ids = [r.id for r in section_rows]
    if not section_ids:
        return []

    # materials presence (one query)
    material_section_ids = set(
        (
            await db.execute(
                select(SectionAsset.module_section_id)
                .where(
                    SectionAsset.module_section_id.in_(section_ids),
                    SectionAsset.processing_status == "completed",
                )
                .distinct()
            )
        )
        .scalars()
        .all()
    )

    # active transcripts for these sections (one query); DB index guarantees ≤1 per section.
    active_by_section: dict[UUID, Transcript] = {}
    for transcript in (
        (
            await db.execute(
                select(Transcript).where(
                    Transcript.module_section_id.in_(section_ids),
                    Transcript.lifecycle_state == "active",
                )
            )
        )
        .scalars()
        .all()
    ):
        # last-wins is irrelevant (index guarantees uniqueness); resolve_single_active covers the rest.
        active_by_section[transcript.module_section_id] = transcript

    # latest summary rows for those active transcripts (one query), reduced to latest per (tid, type).
    active_ids = [t.id for t in active_by_section.values()]
    latest_summary: dict[tuple[UUID, str], GeneratedLectureSummary] = {}
    if active_ids:
        for row in (
            (
                await db.execute(
                    select(GeneratedLectureSummary)
                    .where(GeneratedLectureSummary.transcript_id.in_(active_ids))
                    .order_by(GeneratedLectureSummary.generated_at.desc())
                )
            )
            .scalars()
            .all()
        ):
            latest_summary.setdefault((row.transcript_id, row.summary_type), row)

    def _eligible(active: Transcript, summary_type: str) -> bool:
        row = latest_summary.get((active.id, summary_type))
        return (
            row is not None
            and is_summary_eligible(row, active_transcript=active)
            and not _content_is_blank(row.content_json, "brief" if summary_type == "brief" else "detailed_study")
        )

    out: list[StudentSectionListRow] = []
    for r in section_rows:
        if r.type not in SUMMARY_SECTION_TYPES:
            coarse = LIST_NOT_APPLICABLE
        else:
            active = active_by_section.get(r.id)
            if active is None:
                coarse = LIST_NONE
            else:
                brief_ok = _eligible(active, "brief")
                detailed_ok = _eligible(active, "detailed_study")
                if brief_ok and detailed_ok:
                    coarse = LIST_READY
                elif brief_ok or detailed_ok:
                    coarse = LIST_PARTIAL
                elif active.status == "failed":
                    coarse = LIST_NONE
                else:
                    coarse = LIST_GENERATING
        out.append(
            StudentSectionListRow(
                id=r.id,
                title=r.title,
                type=r.type,
                order_index=r.order_index,
                lecturer_notes=r.lecturer_notes,
                has_materials=r.id in material_section_ids,
                summaries_state=coarse,
            )
        )
    return out


# ---- Workspace conversation list (Stage 8.4 — same 4.7 gate, batched, no per-row fan-out) -----------
@dataclass(frozen=True)
class StudentConversationListRow:
    id: UUID
    conversation_kind: str
    title: str | None
    title_source: str
    # 8.6a: section fields are NULL for a module-bound (sectionless) homework conversation; module is
    # always present (a homework conversation binds a module, a lecture conversation's section has one).
    attached_section_id: UUID | None
    module_id: UUID
    module_title: str
    section_title: str | None
    section_type: str | None
    last_activity_at: datetime
    message_count: int
    last_message_preview: str | None


_PREVIEW_MAX_CHARS = 140


def _conversation_preview(content: str | None) -> str | None:
    """A short, whitespace-collapsed preview of the latest content-bearing message (presentation
    shaping only — no policy). Titles/previews render as escaped plain text in the UI."""
    if content is None:
        return None
    collapsed = " ".join(content.split())
    if not collapsed:
        return None
    if len(collapsed) <= _PREVIEW_MAX_CHARS:
        return collapsed
    return collapsed[: _PREVIEW_MAX_CHARS - 1].rstrip() + "…"


async def get_visible_student_conversation_list(
    db: AsyncSession,
    *,
    student_id: UUID,
    limit: int,
    offset: int,
) -> tuple[list[StudentConversationListRow], int]:
    """The Workspace conversation list. Returns the student's OWN, non-soft-deleted conversations that are
    STILL visible — the SAME published+active-module+active-membership predicate as
    ``get_visible_student_section``, so a list row exists iff a direct open would succeed (invariant C is
    STRUCTURAL, not a parallel filter that could drift). Newest-activity-first; ``message_count`` and the
    last-message preview are batched (no per-row fan-out). Read model only (rule 8).

    8.6a: a conversation may be SECTION-bound (lecture chat — visibility via the section) or MODULE-bound
    (homework, no section — visibility via ``attached_module_id``). The section is LEFT-joined and the
    effective module is ``COALESCE(section.course_module_id, attached_module_id)``; the visibility
    predicate keeps the section-bound case BYTE-IDENTICAL (section must be published+active) and adds the
    module-bound case (section NULL + module bound). Module-active + active-membership apply to both."""
    last_activity = func.coalesce(
        AssistantConversation.last_activity_at, AssistantConversation.updated_at
    )
    effective_module_id = func.coalesce(
        ModuleSection.course_module_id, AssistantConversation.attached_module_id
    )
    # Either the section is bound AND published+active (lecture chat), or it is a module-bound homework
    # conversation (no section). The module + membership predicate below applies to both.
    bound_and_visible = or_(
        and_(
            AssistantConversation.attached_section_id.is_not(None),
            ModuleSection.publish_status == "published",
            ModuleSection.status == "active",
        ),
        and_(
            AssistantConversation.attached_section_id.is_(None),
            AssistantConversation.attached_module_id.is_not(None),
        ),
    )
    visibility = (
        AssistantConversation.student_id == student_id,
        AssistantConversation.deleted_at.is_(None),
        bound_and_visible,
        CourseModule.is_active.is_(True),
        CourseMembership.user_id == student_id,
        CourseMembership.role == "student",
        CourseMembership.status == "active",
    )

    total = (
        await db.execute(
            select(func.count())
            .select_from(AssistantConversation)
            .outerjoin(
                ModuleSection, ModuleSection.id == AssistantConversation.attached_section_id
            )
            .join(CourseModule, CourseModule.id == effective_module_id)
            .join(CourseMembership, CourseMembership.module_id == CourseModule.id)
            .where(*visibility)
        )
    ).scalar_one()

    rows = (
        await db.execute(
            select(
                AssistantConversation.id,
                AssistantConversation.conversation_kind,
                AssistantConversation.title,
                AssistantConversation.title_source,
                AssistantConversation.attached_section_id,
                CourseModule.id,
                CourseModule.title,
                ModuleSection.title,
                ModuleSection.type,
                last_activity.label("last_activity_at"),
            )
            .outerjoin(
                ModuleSection, ModuleSection.id == AssistantConversation.attached_section_id
            )
            .join(CourseModule, CourseModule.id == effective_module_id)
            .join(CourseMembership, CourseMembership.module_id == CourseModule.id)
            .where(*visibility)
            .order_by(last_activity.desc(), AssistantConversation.id.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()
    if not rows:
        return [], int(total)

    conv_ids = [r[0] for r in rows]
    counts = dict(
        (
            await db.execute(
                select(AssistantMessage.conversation_id, func.count())
                .where(AssistantMessage.conversation_id.in_(conv_ids))
                .group_by(AssistantMessage.conversation_id)
            )
        ).all()
    )
    # latest content-bearing message per conversation (a pending assistant turn has content=NULL and is
    # skipped, so the preview falls back to the last user/assistant message that actually has text).
    preview_by_conv: dict[UUID, str | None] = {}
    for cid, content in (
        await db.execute(
            select(AssistantMessage.conversation_id, AssistantMessage.content)
            .where(
                AssistantMessage.conversation_id.in_(conv_ids),
                AssistantMessage.content.is_not(None),
            )
            .order_by(
                AssistantMessage.conversation_id,
                AssistantMessage.created_at.desc(),
                AssistantMessage.id.desc(),
            )
            .distinct(AssistantMessage.conversation_id)
        )
    ).all():
        preview_by_conv[cid] = _conversation_preview(content)

    return [
        StudentConversationListRow(
            id=r[0],
            conversation_kind=r[1],
            title=r[2],
            title_source=r[3],
            attached_section_id=r[4],
            module_id=r[5],
            module_title=r[6],
            section_title=r[7],
            section_type=r[8],
            last_activity_at=r[9],
            message_count=int(counts.get(r[0], 0)),
            last_message_preview=preview_by_conv.get(r[0]),
        )
        for r in rows
    ], int(total)


# re-export for the service's step-key iteration
__all__ = [
    "VisibleStudentSection",
    "VisibleStudentModule",
    "StudentMaterialRow",
    "SectionSummaryInputs",
    "StudentSectionListRow",
    "StudentConversationListRow",
    "resolve_single_active",
    "get_visible_student_section",
    "get_visible_student_module",
    "get_student_section_materials",
    "get_section_summary_inputs",
    "get_visible_student_section_list",
    "get_visible_student_conversation_list",
    "SUMMARY_STEP_KEYS",
]
