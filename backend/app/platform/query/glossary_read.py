"""Glossary read models (Stage 7a) — read-only, no cross-domain imports (rule 8).

Every read is owner-scoped on ``student_id`` (the glossary is personal; another student's row resolves
to "not found" → the caller returns 404, never 403). Entry lists use the Stage 5 pagination envelope.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.db.models import GlossaryEntry, GlossaryFolder, GlossarySourceReference


@dataclass(frozen=True)
class FolderSummary:
    id: UUID
    name: str
    is_system: bool
    status: str
    entry_count: int


async def list_glossary_entries(
    db: AsyncSession,
    *,
    student_id: UUID,
    subject_id: UUID | None = None,
    folder_id: UUID | None = None,
    status: str = "active",
    limit: int,
    offset: int,
) -> tuple[list[GlossaryEntry], int]:
    conditions = [GlossaryEntry.student_id == student_id, GlossaryEntry.status == status]
    if subject_id is not None:
        conditions.append(GlossaryEntry.subject_id == subject_id)
    if folder_id is not None:
        conditions.append(GlossaryEntry.folder_id == folder_id)

    total = await db.scalar(
        select(func.count()).select_from(GlossaryEntry).where(*conditions)
    )
    rows = (
        await db.execute(
            select(GlossaryEntry)
            .where(*conditions)
            .order_by(GlossaryEntry.created_at.desc(), GlossaryEntry.id.desc())
            .limit(limit)
            .offset(offset)
        )
    ).scalars().all()
    return list(rows), int(total or 0)


async def get_glossary_entry(
    db: AsyncSession, *, student_id: UUID, entry_id: UUID
) -> GlossaryEntry | None:
    return (
        await db.execute(
            select(GlossaryEntry).where(
                GlossaryEntry.id == entry_id,
                GlossaryEntry.student_id == student_id,
            )
        )
    ).scalar_one_or_none()


async def get_entry_sources(
    db: AsyncSession, *, entry_id: UUID
) -> list[GlossarySourceReference]:
    return list(
        (
            await db.execute(
                select(GlossarySourceReference)
                .where(GlossarySourceReference.glossary_entry_id == entry_id)
                .order_by(GlossarySourceReference.created_at.asc())
            )
        ).scalars().all()
    )


async def get_glossary_folder(
    db: AsyncSession, *, student_id: UUID, folder_id: UUID
) -> GlossaryFolder | None:
    return (
        await db.execute(
            select(GlossaryFolder).where(
                GlossaryFolder.id == folder_id,
                GlossaryFolder.student_id == student_id,
            )
        )
    ).scalar_one_or_none()


async def list_glossary_folders(
    db: AsyncSession, *, student_id: UUID
) -> list[FolderSummary]:
    count_rows = (
        await db.execute(
            select(GlossaryEntry.folder_id, func.count())
            .where(GlossaryEntry.student_id == student_id, GlossaryEntry.status == "active")
            .group_by(GlossaryEntry.folder_id)
        )
    ).all()
    counts = {folder_id: int(n) for folder_id, n in count_rows}

    folders = (
        await db.execute(
            select(GlossaryFolder)
            .where(GlossaryFolder.student_id == student_id, GlossaryFolder.status == "active")
            # System "Unsorted" first, then alphabetical.
            .order_by(GlossaryFolder.is_system.desc(), GlossaryFolder.name.asc())
        )
    ).scalars().all()
    return [
        FolderSummary(
            id=f.id,
            name=f.name,
            is_system=f.is_system,
            status=f.status,
            entry_count=counts.get(f.id, 0),
        )
        for f in folders
    ]
