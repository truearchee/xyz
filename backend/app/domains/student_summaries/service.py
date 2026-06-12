"""Student summary service (Stage 4.7) — orchestration over the policy + scoped reads + precedence.

Flow (spec §4): student-only gate (403 row R, before any lookup) → scoped query (zero rows ⇒ pinned
404 rows D/P/I) → section-type gate + §4 identity guard + §6 precedence → DTO. No fetch-then-branch.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.student_summaries.markdown import summary_to_markdown
from app.domains.student_summaries.policy import StudentSummaryAccessPolicy
from app.domains.student_summaries.precedence import READY, SlotResult, derive_slot_state
from app.domains.student_summaries.schemas import (
    StudentMaterialMeta,
    StudentSectionListItem,
    StudentSectionRead,
    StudentSectionSummariesContent,
    StudentSectionSummariesRead,
    StudentSectionSummaryStates,
    StudentSummarySlot,
    StudentSummarySlotState,
)
from app.platform.auth.context import CurrentUserContext
from app.platform.db.models import GeneratedLectureSummary
from app.platform.query.modules import get_active_module_access
from app.platform.query.student_summary_read import (
    SectionSummaryInputs,
    VisibleStudentSection,
    get_section_summary_inputs,
    get_student_section_materials,
    get_visible_student_section,
    get_visible_student_section_list,
)

# 404 for a module the student is not an active member of (mirrors the Stage 3 content list contract).
MODULE_NOT_FOUND = "MODULE_NOT_FOUND"


def _slot_result(
    section: VisibleStudentSection,
    inputs: SectionSummaryInputs,
    *,
    summary_type: str,
    summary_row: GeneratedLectureSummary | None,
    step_status: str | None,
) -> SlotResult:
    return derive_slot_state(
        section_type=section.type,
        summary_type=summary_type,
        active_transcript=inputs.active_transcript,
        summary_row=summary_row,
        summary_step_status=step_status,
        overall_state=inputs.overall_state,
        section_id=section.id,
    )


async def _resolve_visible_section(
    db: AsyncSession,
    *,
    current_user: CurrentUserContext,
    section_id: UUID,
) -> VisibleStudentSection:
    StudentSummaryAccessPolicy.require_student(current_user.role)  # row R → 403 before any lookup
    visible = await get_visible_student_section(
        db, student_id=current_user.user_id, section_id=section_id
    )
    return StudentSummaryAccessPolicy.require_visible(visible)  # rows D/P/I → pinned 404


async def get_student_section_detail(
    db: AsyncSession,
    *,
    current_user: CurrentUserContext,
    section_id: UUID,
) -> StudentSectionRead:
    """§8.2 endpoint 1 — section shell + per-slot STATE (no content)."""
    section = await _resolve_visible_section(db, current_user=current_user, section_id=section_id)
    materials = await get_student_section_materials(db, section_id=section_id)
    inputs = await get_section_summary_inputs(db, section_id=section_id)
    brief = _slot_result(
        section, inputs, summary_type="brief", summary_row=inputs.brief_row, step_status=inputs.brief_step_status
    )
    detailed = _slot_result(
        section,
        inputs,
        summary_type="detailed_study",
        summary_row=inputs.detailed_row,
        step_status=inputs.detailed_step_status,
    )
    return StudentSectionRead(
        id=section.id,
        title=section.title,
        type=section.type,
        order_index=section.order_index,
        lecturer_notes=section.lecturer_notes,
        materials=[
            StudentMaterialMeta(
                id=m.id, file_name=m.file_name, mime_type=m.mime_type, file_size=m.file_size
            )
            for m in materials
        ],
        summaries=StudentSectionSummaryStates(
            brief=StudentSummarySlotState(state=brief.state),
            detailed=StudentSummarySlotState(state=detailed.state),
        ),
    )


async def get_student_section_summaries(
    db: AsyncSession,
    *,
    current_user: CurrentUserContext,
    section_id: UUID,
) -> StudentSectionSummariesRead:
    """§8.2 endpoint 2 — per-slot {state, content}. Content (server-rendered markdown) is non-null only
    when the slot is READY. assignment/supplementary → 200 with both slots not_applicable (H1)."""
    section = await _resolve_visible_section(db, current_user=current_user, section_id=section_id)
    inputs = await get_section_summary_inputs(db, section_id=section_id)

    def _slot(summary_type: str, summary_row: GeneratedLectureSummary | None, step_status: str | None) -> StudentSummarySlot:
        result = _slot_result(
            section, inputs, summary_type=summary_type, summary_row=summary_row, step_status=step_status
        )
        content = None
        if result.state == READY and summary_row is not None:
            content = summary_to_markdown(summary_type, summary_row.content_json)
        return StudentSummarySlot(state=result.state, content=content)

    return StudentSectionSummariesRead(
        section_id=section.id,
        summaries=StudentSectionSummariesContent(
            brief=_slot("brief", inputs.brief_row, inputs.brief_step_status),
            detailed=_slot("detailed_study", inputs.detailed_row, inputs.detailed_step_status),
        ),
    )


async def list_student_module_sections(
    db: AsyncSession,
    *,
    current_user: CurrentUserContext,
    module_id: UUID,
) -> list[StudentSectionListItem]:
    """§8.1 — published sections of a module the student belongs to, each with a coarse summaries flag.
    Non-student → 403; not an active member → 404 (mirrors the Stage 3 content list)."""
    StudentSummaryAccessPolicy.require_student(current_user.role)
    access = await get_active_module_access(db, current_user.user_id, module_id)
    if access is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=MODULE_NOT_FOUND)
    rows = await get_visible_student_section_list(
        db, student_id=current_user.user_id, module_id=module_id
    )
    return [
        StudentSectionListItem(
            id=r.id,
            title=r.title,
            type=r.type,
            order_index=r.order_index,
            has_notes=bool((r.lecturer_notes or "").strip()),
            has_materials=r.has_materials,
            summaries_state=r.summaries_state,
        )
        for r in rows
    ]
