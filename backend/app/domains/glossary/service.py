"""Glossary HTTP service (Stage 7a) — orchestration over the policy gate + scoped reads + save flow.

Every endpoint: student-only gate (403 before any lookup) → owner-scoped resource resolution (a miss is
the pinned 404) → the action. Saving derives the subject from the source (highlight) or validates the
chosen course is one the student is enrolled in (manual). Reads use the request session; writes commit it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.glossary.policy import (
    ENTRY_NOT_FOUND,
    ENTRY_TYPE_IMMUTABLE,
    FOLDER_NAME_EXISTS,
    FOLDER_NOT_FOUND,
    FOLDER_SYSTEM_IMMUTABLE,
    SECTION_NOT_FOUND,
    SUBJECT_NOT_FOUND,
    conflict,
    not_found,
    require_student,
    validation_error,
)
from app.domains.glossary.save_service import ensure_unsorted_folder, save_term
from app.domains.glossary.schemas import (
    GlossaryEntryDetail,
    GlossaryEntryRead,
    GlossaryFolderRead,
    GlossarySourceReferenceRead,
    ManualEntryRequest,
    SaveHighlightRequest,
    SaveResponse,
    UpdateEntryRequest,
)
from app.platform.auth.context import CurrentUserContext
from app.platform.db.models import GlossaryEntry, GlossaryFolder, ModuleSection
from app.platform.query.glossary_read import (
    get_entry_sources,
    get_glossary_entry,
    get_glossary_folder,
    list_glossary_entries,
    list_glossary_folders,
)
from app.platform.query.modules import get_active_module_access
from app.platform.query.pagination import PaginatedResponse, PaginationMeta


def _now() -> datetime:
    return datetime.now(UTC)


async def _save_response(
    db: AsyncSession, *, current_user: CurrentUserContext, entry_id: UUID, duplicate: bool
) -> SaveResponse:
    entry = await get_glossary_entry(db, student_id=current_user.user_id, entry_id=entry_id)
    if entry is None:  # pragma: no cover - just-saved row must exist
        raise not_found(ENTRY_NOT_FOUND)
    return SaveResponse(entry=GlossaryEntryRead.model_validate(entry), duplicate=duplicate)


# ── save ──
async def save_from_highlight(
    db: AsyncSession, *, current_user: CurrentUserContext, payload: SaveHighlightRequest
) -> SaveResponse:
    require_student(current_user.role)
    section = await db.get(ModuleSection, payload.module_section_id)
    if section is None:
        raise not_found(SECTION_NOT_FOUND)
    subject_id = section.course_module_id
    # Enrollment is the personal-scope gate; a non-member sees the same pinned 404 (no info leak).
    if await get_active_module_access(db, current_user.user_id, subject_id) is None:
        raise not_found(SECTION_NOT_FOUND)
    outcome = await save_term(
        db,
        student_id=current_user.user_id,
        subject_id=subject_id,
        term=payload.term,
        language=current_user.preferred_language,
        entry_type=payload.entry_type,
        folder_id=None,
        module_section_id=payload.module_section_id,
        source_type="summary",
        selected_text=payload.selected_text,
    )
    return await _save_response(
        db, current_user=current_user, entry_id=outcome.entry_id, duplicate=outcome.duplicate
    )


async def save_manual(
    db: AsyncSession, *, current_user: CurrentUserContext, payload: ManualEntryRequest
) -> SaveResponse:
    require_student(current_user.role)
    if await get_active_module_access(db, current_user.user_id, payload.subject_id) is None:
        raise not_found(SUBJECT_NOT_FOUND)
    if payload.folder_id is not None:
        folder = await get_glossary_folder(
            db, student_id=current_user.user_id, folder_id=payload.folder_id
        )
        if folder is None or folder.status != "active":
            raise not_found(FOLDER_NOT_FOUND)
    outcome = await save_term(
        db,
        student_id=current_user.user_id,
        subject_id=payload.subject_id,
        term=payload.term,
        language=current_user.preferred_language,
        entry_type=payload.entry_type,
        folder_id=payload.folder_id,
        module_section_id=None,
        source_type="manual",
        selected_text=None,
    )
    return await _save_response(
        db, current_user=current_user, entry_id=outcome.entry_id, duplicate=outcome.duplicate
    )


# ── entries ──
async def list_entries(
    db: AsyncSession,
    *,
    current_user: CurrentUserContext,
    subject_id: UUID | None,
    folder_id: UUID | None,
    entry_status: str,
    limit: int,
    offset: int,
) -> PaginatedResponse[GlossaryEntryRead]:
    require_student(current_user.role)
    rows, total = await list_glossary_entries(
        db,
        student_id=current_user.user_id,
        subject_id=subject_id,
        folder_id=folder_id,
        status=entry_status,
        limit=limit,
        offset=offset,
    )
    return PaginatedResponse[GlossaryEntryRead](
        items=[GlossaryEntryRead.model_validate(r) for r in rows],
        pagination=PaginationMeta(limit=limit, offset=offset, total=total),
    )


async def get_entry(
    db: AsyncSession, *, current_user: CurrentUserContext, entry_id: UUID
) -> GlossaryEntryDetail:
    require_student(current_user.role)
    entry = await get_glossary_entry(db, student_id=current_user.user_id, entry_id=entry_id)
    if entry is None:
        raise not_found(ENTRY_NOT_FOUND)
    sources = await get_entry_sources(db, entry_id=entry_id)
    return GlossaryEntryDetail(
        entry=GlossaryEntryRead.model_validate(entry),
        sources=[GlossarySourceReferenceRead.model_validate(s) for s in sources],
    )


async def update_entry(
    db: AsyncSession,
    *,
    current_user: CurrentUserContext,
    entry_id: UUID,
    payload: UpdateEntryRequest,
) -> GlossaryEntryRead:
    require_student(current_user.role)
    entry = await get_glossary_entry(db, student_id=current_user.user_id, entry_id=entry_id)
    if entry is None or entry.status != "active":
        raise not_found(ENTRY_NOT_FOUND)
    if payload.folder_id is not None:
        folder = await get_glossary_folder(
            db, student_id=current_user.user_id, folder_id=payload.folder_id
        )
        if folder is None or folder.status != "active":
            raise not_found(FOLDER_NOT_FOUND)
        entry.folder_id = payload.folder_id
    if payload.entry_type is not None:
        raise validation_error(ENTRY_TYPE_IMMUTABLE)
    entry.updated_at = _now()
    await db.commit()
    return GlossaryEntryRead.model_validate(entry)


async def archive_entry(
    db: AsyncSession, *, current_user: CurrentUserContext, entry_id: UUID
) -> None:
    """"Delete" = soft archive (status → archived; row + events preserved)."""
    require_student(current_user.role)
    entry = await get_glossary_entry(db, student_id=current_user.user_id, entry_id=entry_id)
    if entry is None or entry.status != "active":
        raise not_found(ENTRY_NOT_FOUND)
    entry.status = "archived"
    entry.updated_at = _now()
    await db.commit()


# ── folders ──
async def list_folders(
    db: AsyncSession, *, current_user: CurrentUserContext
) -> list[GlossaryFolderRead]:
    require_student(current_user.role)
    folders = await list_glossary_folders(db, student_id=current_user.user_id)
    return [
        GlossaryFolderRead(
            id=f.id,
            name=f.name,
            is_system=f.is_system,
            status=f.status,
            entry_count=f.entry_count,
        )
        for f in folders
    ]


async def create_folder(
    db: AsyncSession, *, current_user: CurrentUserContext, name: str
) -> GlossaryFolderRead:
    require_student(current_user.role)
    folder = GlossaryFolder(
        student_id=current_user.user_id, name=name.strip(), is_system=False, status="active"
    )
    db.add(folder)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise conflict(FOLDER_NAME_EXISTS) from None
    await db.refresh(folder)
    return GlossaryFolderRead(
        id=folder.id, name=folder.name, is_system=folder.is_system, status=folder.status, entry_count=0
    )


async def update_folder(
    db: AsyncSession, *, current_user: CurrentUserContext, folder_id: UUID, name: str
) -> GlossaryFolderRead:
    require_student(current_user.role)
    folder = await get_glossary_folder(db, student_id=current_user.user_id, folder_id=folder_id)
    if folder is None or folder.status != "active":
        raise not_found(FOLDER_NOT_FOUND)
    if folder.is_system:
        raise conflict(FOLDER_SYSTEM_IMMUTABLE)
    folder.name = name.strip()
    folder.updated_at = _now()
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise conflict(FOLDER_NAME_EXISTS) from None
    summaries = await list_glossary_folders(db, student_id=current_user.user_id)
    count = next((s.entry_count for s in summaries if s.id == folder.id), 0)
    return GlossaryFolderRead(
        id=folder.id, name=folder.name, is_system=folder.is_system, status=folder.status, entry_count=count
    )


async def archive_folder(
    db: AsyncSession, *, current_user: CurrentUserContext, folder_id: UUID
) -> None:
    require_student(current_user.role)
    folder = await get_glossary_folder(db, student_id=current_user.user_id, folder_id=folder_id)
    if folder is None or folder.status != "active":
        raise not_found(FOLDER_NOT_FOUND)
    if folder.is_system:
        raise conflict(FOLDER_SYSTEM_IMMUTABLE)
    unsorted_id = await ensure_unsorted_folder(db, student_id=current_user.user_id)
    # Move the folder's entries to Unsorted, then archive the folder.
    await db.execute(
        update(GlossaryEntry)
        .where(
            GlossaryEntry.student_id == current_user.user_id,
            GlossaryEntry.folder_id == folder_id,
        )
        .values(folder_id=unsorted_id, updated_at=_now())
    )
    folder.status = "archived"
    folder.updated_at = _now()
    await db.commit()
