"""Saving a glossary term (Stage 7a) — the synchronous request-path orchestration.

All of normalize → server-side dedup → create entry → cache check → (winner) enqueue → emit
``glossary_term_saved`` happens in the request transaction; the AI-queue enqueue happens AFTER commit
(a rollback can never leave a phantom job, mirroring ``start_quiz_attempt``). Authorization + scope
resolution (which course a term belongs to) is the caller's (``service.py``) job.

The cross-student collapse lives here: a cache MISS inserts a ``pending`` cache row with
``ON CONFLICT DO NOTHING`` on ``(cache_key, prompt_version)``; only the row's creator (the "winner")
enqueues a generation job, so two students racing the same term/subject/language produce ONE model call.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import logging
from uuid import UUID

from sqlalchemy import select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from uuid6 import uuid7

from app.domains.glossary.cache_keys import definition_cache_key
from app.domains.glossary.normalize import NORMALIZE_VERSION, normalize_term
from app.domains.glossary.specs import (
    CONTEXT_CHAR_CAP,
    GLOSSARY_DEFINITION_PROMPT_VERSION,
)
from app.platform.db.models import (
    GlossaryDefinitionCache,
    GlossaryEntry,
    GlossaryFolder,
    GlossarySourceReference,
)
from app.platform.events import GLOSSARY_TERM_SAVED, EventRecorder
from app.workers.queues import enqueue_generate_glossary_definition

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SaveOutcome:
    entry_id: UUID
    duplicate: bool


def _now() -> datetime:
    return datetime.now(UTC)


async def ensure_unsorted_folder(db: AsyncSession, *, student_id: UUID) -> UUID:
    """Get-or-create the student's system 'Unsorted' inbox (partial-unique-guarded singleton)."""
    existing = (
        await db.execute(
            select(GlossaryFolder.id).where(
                GlossaryFolder.student_id == student_id,
                GlossaryFolder.is_system.is_(True),
                GlossaryFolder.status == "active",
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    await db.execute(
        pg_insert(GlossaryFolder)
        .values(
            id=uuid7(),
            student_id=student_id,
            name="Unsorted",
            is_system=True,
            status="active",
        )
        .on_conflict_do_nothing(
            index_elements=["student_id"],
            index_where=text("is_system AND status = 'active'"),
        )
    )
    return (
        await db.execute(
            select(GlossaryFolder.id).where(
                GlossaryFolder.student_id == student_id,
                GlossaryFolder.is_system.is_(True),
                GlossaryFolder.status == "active",
            )
        )
    ).scalar_one()


async def _resolve_folder(db: AsyncSession, *, student_id: UUID, folder_id: UUID | None) -> UUID:
    """Return the folder to file the entry in. ``None`` → the student's 'Unsorted' inbox. A provided
    folder_id is trusted to have been ownership-checked by the caller."""
    if folder_id is not None:
        return folder_id
    return await ensure_unsorted_folder(db, student_id=student_id)


async def save_term(
    db: AsyncSession,
    *,
    student_id: UUID,
    subject_id: UUID,
    term: str,
    language: str,
    entry_type: str,
    folder_id: UUID | None,
    module_section_id: UUID | None,
    source_type: str,
    selected_text: str | None,
    source_summary_id: UUID | None = None,
    source_quiz_attempt_id: UUID | None = None,
) -> SaveOutcome:
    normalized = normalize_term(term)
    cache_key = definition_cache_key(
        normalized_term=normalized,
        subject_id=subject_id,
        entry_type=entry_type,
        language=language,
    )

    # --- dedup + create in one shot (partial-unique on active rows) ---
    entry_id = uuid7()
    inserted_entry_id = (
        await db.execute(
            pg_insert(GlossaryEntry)
            .values(
                id=entry_id,
                student_id=student_id,
                subject_id=subject_id,
                folder_id=await _resolve_folder(db, student_id=student_id, folder_id=folder_id),
                module_section_id=module_section_id,
                term=term,
                normalized_term=normalized,
                normalize_version=NORMALIZE_VERSION,
                entry_type=entry_type,
                language=language,
                cache_key=cache_key,
                definition_status="pending",
                status="active",
            )
            .on_conflict_do_nothing(
                index_elements=["student_id", "subject_id", "normalized_term"],
                index_where=text("status = 'active'"),
            )
            .returning(GlossaryEntry.id)
        )
    ).scalar_one_or_none()

    if inserted_entry_id is None:
        # Duplicate: the student already has this term in this subject. Attach a NEW source reference
        # to the existing entry; create no second entry, emit no event (already saved). If a previous
        # enqueue failed, this duplicate save is the user's retry and re-enqueues the failed cache row.
        existing = (
            await db.execute(
                select(GlossaryEntry).where(
                    GlossaryEntry.student_id == student_id,
                    GlossaryEntry.subject_id == subject_id,
                    GlossaryEntry.normalized_term == normalized,
                    GlossaryEntry.status == "active",
                )
            )
        ).scalar_one()
        db.add(
            GlossarySourceReference(
                glossary_entry_id=existing.id,
                source_type=source_type,
                module_section_id=module_section_id,
                source_summary_id=source_summary_id,
                source_quiz_attempt_id=source_quiz_attempt_id,
                selected_text=selected_text,
            )
        )
        cache_row_id_to_enqueue = await _recover_failed_definition(db, cache_key=existing.cache_key)
        await db.commit()
        if cache_row_id_to_enqueue is not None:
            await _enqueue_definition_after_commit(db, cache_row_id_to_enqueue)
        return SaveOutcome(entry_id=existing.id, duplicate=True)

    # New entry. Record its source reference.
    db.add(
        GlossarySourceReference(
            glossary_entry_id=entry_id,
            source_type=source_type,
            module_section_id=module_section_id,
            source_summary_id=source_summary_id,
            source_quiz_attempt_id=source_quiz_attempt_id,
            selected_text=selected_text,
        )
    )

    # --- cache check / concurrent-miss collapse ---
    cache_row_id_to_enqueue = await _resolve_definition(
        db,
        entry_id=entry_id,
        cache_key=cache_key,
        normalized_term=normalized,
        subject_id=subject_id,
        entry_type=entry_type,
        language=language,
        term=term,
        selected_text=selected_text,
    )

    # --- glossary_term_saved in the SAME transaction as the save (rule 7) ---
    await EventRecorder().record(
        db,
        student_id=student_id,
        module_id=subject_id,
        event_type=GLOSSARY_TERM_SAVED,
        source_id=entry_id,
        metadata={"subjectId": str(subject_id), "language": language, "entryType": entry_type},
    )

    await db.commit()

    # --- enqueue AFTER commit (winner only) ---
    if cache_row_id_to_enqueue is not None:
        await _enqueue_definition_after_commit(db, cache_row_id_to_enqueue)

    return SaveOutcome(entry_id=entry_id, duplicate=False)


async def _enqueue_definition_after_commit(db: AsyncSession, cache_row_id: UUID) -> None:
    """Queue the committed definition job, compensating to a retryable failed state on queue errors."""
    try:
        enqueue_generate_glossary_definition(cache_row_id)
    except Exception:
        logger.exception("glossary definition enqueue failed; compensating to failed")
        await _mark_definition_enqueue_failed(db, cache_row_id=cache_row_id)


async def _mark_definition_enqueue_failed(db: AsyncSession, *, cache_row_id: UUID) -> None:
    row = (
        await db.execute(
            select(GlossaryDefinitionCache)
            .where(GlossaryDefinitionCache.id == cache_row_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if row is None or row.status == "generated":
        await db.commit()
        return
    now = _now()
    row.status = "failed"
    row.updated_at = now
    await db.execute(
        update(GlossaryEntry)
        .where(
            GlossaryEntry.cache_key == row.cache_key,
            GlossaryEntry.status == "active",
            GlossaryEntry.definition_status == "pending",
        )
        .values(definition_status="failed", updated_at=now)
    )
    await db.commit()


async def _recover_failed_definition(db: AsyncSession, *, cache_key: str) -> UUID | None:
    row = (
        await db.execute(
            select(GlossaryDefinitionCache)
            .where(
                GlossaryDefinitionCache.cache_key == cache_key,
                GlossaryDefinitionCache.prompt_version == GLOSSARY_DEFINITION_PROMPT_VERSION,
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if row is None or row.status != "failed":
        return None
    now = _now()
    row.status = "pending"
    row.updated_at = now
    await db.execute(
        update(GlossaryEntry)
        .where(
            GlossaryEntry.cache_key == row.cache_key,
            GlossaryEntry.status == "active",
            GlossaryEntry.definition_status == "failed",
        )
        .values(definition_status="pending", updated_at=now)
    )
    return row.id


async def _resolve_definition(
    db: AsyncSession,
    *,
    entry_id: UUID,
    cache_key: str,
    normalized_term: str,
    subject_id: UUID,
    entry_type: str,
    language: str,
    term: str,
    selected_text: str | None,
) -> UUID | None:
    """Apply the shared cache to the new entry. Returns the cache row id to enqueue (winner of a miss),
    or None (cache hit, or an in-flight job already owns the generation)."""
    context_text = (selected_text or "").strip()[:CONTEXT_CHAR_CAP]
    cache_row_id = uuid7()
    inserted_cache_id = (
        await db.execute(
            pg_insert(GlossaryDefinitionCache)
            .values(
                id=cache_row_id,
                cache_key=cache_key,
                prompt_version=GLOSSARY_DEFINITION_PROMPT_VERSION,
                normalized_term=normalized_term,
                subject_id=subject_id,
                entry_type=entry_type,
                language=language,
                term=term,
                context_text=context_text or None,
                status="pending",
            )
            .on_conflict_do_nothing(index_elements=["cache_key", "prompt_version"])
            .returning(GlossaryDefinitionCache.id)
        )
    ).scalar_one_or_none()

    if inserted_cache_id is not None:
        return inserted_cache_id  # we created the cache row → we enqueue (the collapse winner)

    # Cache row already exists — look at its state.
    existing = (
        await db.execute(
            select(GlossaryDefinitionCache)
            .where(
                GlossaryDefinitionCache.cache_key == cache_key,
                GlossaryDefinitionCache.prompt_version == GLOSSARY_DEFINITION_PROMPT_VERSION,
            )
            .with_for_update()
        )
    ).scalar_one()

    if existing.status == "generated":
        # Cache HIT → copy the definition + provenance onto the new entry; no model call.
        entry = await db.get(GlossaryEntry, entry_id)
        if entry is not None:
            entry.short_definition = existing.short_definition
            entry.definition_status = "generated"
            entry.model_id = existing.model_id
            entry.prompt_version = existing.prompt_version
            entry.prompt_content_hash = existing.prompt_content_hash
            entry.backend_used = existing.backend_used
            entry.source_content_hash = existing.source_content_hash
            entry.ai_request_log_id = existing.ai_request_log_id
            entry.definition_generated_at = existing.generated_at
            entry.updated_at = _now()
        return None

    if existing.status == "failed":
        # The prior generation failed terminally; this save retriggers it (re-enqueue this row).
        existing.status = "pending"
        existing.updated_at = _now()
        return existing.id

    # status == 'pending': an in-flight job already owns this generation; our entry will be fanned
    # out when it completes. Attach, do not enqueue a second job.
    return None
