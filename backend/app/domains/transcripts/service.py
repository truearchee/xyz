from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from uuid6 import uuid7

from app.domains.transcripts.schemas import (
    BriefSummaryContent,
    DetailedSummaryContent,
    TranscriptProcessingStatus,
    TranscriptSummariesRead,
)
from app.domains.transcripts.validators import (
    InvalidTranscriptError,
    TranscriptUploadTooLargeError,
    spool_and_validate_transcript,
)
from app.platform.auth.context import CurrentUserContext
from app.platform.config import settings
from app.platform.db.models import ModuleSection, Transcript
from app.platform.query.section_context import (
    AuthorizedSectionContext,
    get_authorized_lecturer_section_context,
)
from app.domains.transcripts.retry import (
    apply_retry,
    enqueue_retry_jobs,
    resolve_retry_scope,
)
from app.platform.query.summary_read import get_latest_transcript_summaries
from app.platform.query.transcript_status import get_transcript_processing_status_read
from app.platform.storage.base import (
    StorageProvider,
    StorageProviderError,
    StorageUnavailableError,
)
from app.platform.storage.keys import generate_transcript_storage_key
from app.workers.queues import enqueue_parse_transcript


logger = logging.getLogger(__name__)

TRANSCRIPT_FORBIDDEN = "TRANSCRIPT_FORBIDDEN"
SECTION_NOT_FOUND = "SECTION_NOT_FOUND"
SECTION_TYPE_UNSUPPORTED = "SECTION_TYPE_UNSUPPORTED"
TRANSCRIPT_ALREADY_EXISTS = "TRANSCRIPT_ALREADY_EXISTS"
TRANSCRIPT_NOT_FOUND = "TRANSCRIPT_NOT_FOUND"
TRANSCRIPT_SUPERSEDED = "TRANSCRIPT_SUPERSEDED"
NO_RETRYABLE_FAILURE = "NO_RETRYABLE_FAILURE"


def _http_error(status_code: int, detail: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail=detail)


def _coded_error(status_code: int, code: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail=code)


def _storage_http_error(exc: StorageProviderError) -> HTTPException:
    if isinstance(exc, StorageUnavailableError):
        return _http_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Storage provider unavailable",
        )
    return _http_error(status.HTTP_502_BAD_GATEWAY, "Storage provider failed")


async def _best_effort_delete(
    storage_provider: StorageProvider,
    *,
    key: str,
    message: str,
) -> None:
    try:
        await storage_provider.delete_object(key=key)
    except Exception:
        logger.warning(message, extra={"storage_key": key})


def _is_active_transcript_conflict(exc: IntegrityError) -> bool:
    return (
        "uq_active_transcript_per_section" in str(exc)
        or "uq_pending_transcript_per_section" in str(exc)
    )


async def prepare_transcript_upload(
    db: AsyncSession,
    *,
    current_user: CurrentUserContext,
    module_id: UUID,
    section_id: UUID,
) -> AuthorizedSectionContext:
    section_context = await _get_lecturer_section_context(
        db,
        current_user=current_user,
        module_id=module_id,
        section_id=section_id,
    )
    if section_context.section_type not in {"lecture", "lab"}:
        raise _coded_error(
            422,
            SECTION_TYPE_UNSUPPORTED,
        )
    # Replacement is allowed (ADR-46-A): a second upload to a section that already has an active
    # transcript no longer 409s — it becomes a `pending` replacement that swaps in atomically on
    # completion. The one-active / one-pending invariants are enforced under a section lock in
    # ``upload_transcript`` (not pre-checked here, which would race).
    return section_context


async def _get_lecturer_section_context(
    db: AsyncSession,
    *,
    current_user: CurrentUserContext,
    module_id: UUID,
    section_id: UUID,
) -> AuthorizedSectionContext:
    if current_user.role != "lecturer":
        raise _coded_error(status.HTTP_403_FORBIDDEN, TRANSCRIPT_FORBIDDEN)

    section_context = await get_authorized_lecturer_section_context(
        db,
        user_id=current_user.user_id,
        module_id=module_id,
        section_id=section_id,
    )
    if section_context is None:
        raise _coded_error(status.HTTP_404_NOT_FOUND, SECTION_NOT_FOUND)
    return section_context


async def upload_transcript(
    db: AsyncSession,
    *,
    current_user: CurrentUserContext,
    storage_provider: StorageProvider,
    section_context: AuthorizedSectionContext,
    upload: UploadFile,
) -> Transcript:
    try:
        validated = await spool_and_validate_transcript(
            upload,
            max_bytes=settings.MAX_TRANSCRIPT_UPLOAD_BYTES,
        )
    except TranscriptUploadTooLargeError as exc:
        raise _http_error(413, str(exc)) from exc
    except InvalidTranscriptError as exc:
        raise _http_error(422, str(exc)) from exc

    transcript_id = uuid7()
    storage_key = generate_transcript_storage_key(
        module_id=section_context.module_id,
        section_id=section_context.section_id,
        transcript_id=transcript_id,
        safe_file_name=validated.safe_file_name,
    )

    try:
        await storage_provider.put_object(
            key=storage_key,
            content=validated.content,
            content_type=validated.effective_mime_type,
            content_length=validated.size_bytes,
            metadata={
                "transcript_id": str(transcript_id),
                "section_id": str(section_context.section_id),
            },
            overwrite=False,
        )
    except StorageProviderError as exc:
        validated.content.close()
        raise _storage_http_error(exc) from exc

    try:
        transcript = await _create_transcript_under_section_lock(
            db,
            section_id=section_context.section_id,
            transcript_id=transcript_id,
            storage_key=storage_key,
            validated=validated,
            uploaded_by_user_id=current_user.user_id,
        )
    except IntegrityError as exc:
        await db.rollback()
        await _best_effort_delete(
            storage_provider,
            key=storage_key,
            message="Failed to clean up transcript object after integrity failure",
        )
        if _is_active_transcript_conflict(exc):
            raise _coded_error(status.HTTP_409_CONFLICT, TRANSCRIPT_ALREADY_EXISTS) from exc
        raise _http_error(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Could not persist transcript metadata",
        ) from exc
    except SQLAlchemyError as exc:
        await db.rollback()
        await _best_effort_delete(
            storage_provider,
            key=storage_key,
            message="Failed to clean up transcript object after DB failure",
        )
        raise _http_error(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Could not persist transcript metadata",
        ) from exc
    finally:
        validated.content.close()

    await db.refresh(transcript)
    await _enqueue_parse_job(db, transcript_id=transcript.id)
    await db.refresh(transcript)
    return transcript


async def _create_transcript_under_section_lock(
    db: AsyncSession,
    *,
    section_id: UUID,
    transcript_id: UUID,
    storage_key: str,
    validated,
    uploaded_by_user_id: UUID,
) -> Transcript:
    """Create the transcript row inside a ``moduleSectionId``-scoped lock (ADR-46-A).

    The lock serializes concurrent uploads to the same section (double-click, client retry, two
    co-lecturers) so the one-active / one-pending invariants surface as ordered state transitions
    rather than constraint-violation 500s. With a prior active present the new transcript is created
    ``pending`` (a replacement); a pre-existing pending is discarded (``discarded_pending``) before the
    new one is inserted so the one-pending partial-unique index always holds. First-ever upload (no
    active) is created ``active`` immediately — unchanged behaviour.
    """
    # Lock the section row; concurrent uploads to this section block here until we commit.
    await db.execute(
        select(ModuleSection.id).where(ModuleSection.id == section_id).with_for_update()
    )

    active = (
        await db.execute(
            select(Transcript).where(
                Transcript.module_section_id == section_id,
                Transcript.lifecycle_state == "active",
            )
        )
    ).scalar_one_or_none()
    pending = (
        await db.execute(
            select(Transcript).where(
                Transcript.module_section_id == section_id,
                Transcript.lifecycle_state == "pending",
            )
        )
    ).scalar_one_or_none()

    now = datetime.now(UTC)
    if pending is not None:
        # Discard the prior pending (one-pending invariant). Demote it FIRST with a NULL lineage
        # pointer and flush, so the new pending insert never collides with it on the one-pending
        # partial-unique index (the unit of work does not preserve assignment order), and so the
        # lineage FK is not set to a transcript row that does not exist yet.
        pending.lifecycle_state = "superseded"
        pending.supersession_reason = "discarded_pending"
        pending.superseded_at = now
        pending.superseded_by_transcript_id = None
        await db.flush()

    if active is not None:
        lifecycle_state = "pending"
        replacement_of_transcript_id: UUID | None = active.id
    else:
        lifecycle_state = "active"
        replacement_of_transcript_id = None

    transcript = Transcript(
        id=transcript_id,
        module_section_id=section_id,
        source_type="manual_upload",
        original_file_name=validated.original_file_name,
        storage_key=storage_key,
        mime_type=validated.effective_mime_type,
        file_size=validated.size_bytes,
        checksum=validated.sha256,
        language=None,
        status="uploaded",
        uploaded_by_user_id=uploaded_by_user_id,
        lifecycle_state=lifecycle_state,
        replacement_of_transcript_id=replacement_of_transcript_id,
    )
    db.add(transcript)
    await db.flush()

    if pending is not None:
        # Back-fill the lineage now that the new row exists (FK satisfiable; old pending already
        # demoted so this UPDATE cannot reintroduce a second pending).
        pending.superseded_by_transcript_id = transcript_id

    await db.commit()
    return transcript


async def get_active_transcript(
    db: AsyncSession,
    *,
    current_user: CurrentUserContext,
    module_id: UUID,
    section_id: UUID,
) -> Transcript:
    section_context = await _get_lecturer_section_context(
        db,
        current_user=current_user,
        module_id=module_id,
        section_id=section_id,
    )
    result = await db.execute(
        select(Transcript).where(
            Transcript.module_section_id == section_context.section_id,
            Transcript.lifecycle_state == "active",
        )
    )
    transcript = result.scalar_one_or_none()
    if transcript is None:
        raise _coded_error(status.HTTP_404_NOT_FOUND, TRANSCRIPT_NOT_FOUND)
    return transcript


async def get_transcript_processing_status(
    db: AsyncSession,
    *,
    current_user: CurrentUserContext,
    module_id: UUID,
    section_id: UUID,
) -> TranscriptProcessingStatus:
    transcript = await get_active_transcript(
        db,
        current_user=current_user,
        module_id=module_id,
        section_id=section_id,
    )
    projection = await get_transcript_processing_status_read(db, transcript=transcript)
    return TranscriptProcessingStatus.model_validate(projection)


async def retry_transcript_processing(
    db: AsyncSession,
    *,
    current_user: CurrentUserContext,
    module_id: UUID,
    section_id: UUID,
    transcript_id: UUID,
) -> TranscriptProcessingStatus:
    """Lecturer-triggered retry of failed processing (ADR-46-B). Resumes from the earliest failed step
    over the DAG; the worker does the fenced delete-and-regenerate when the re-enqueued job runs.

    Authz is the existing assigned-lecturer section authz (403 non-lecturer / 404 unassigned). The
    transcriptId targets the active transcript OR a failed pending replacement; a superseded transcript
    is rejected (409). 409 when nothing is in a retryable failed state.
    """
    section_context = await _get_lecturer_section_context(
        db,
        current_user=current_user,
        module_id=module_id,
        section_id=section_id,
    )

    transcript = (
        await db.execute(select(Transcript).where(Transcript.id == transcript_id))
    ).scalar_one_or_none()
    if transcript is None or transcript.module_section_id != section_context.section_id:
        raise _coded_error(status.HTTP_404_NOT_FOUND, TRANSCRIPT_NOT_FOUND)
    if transcript.lifecycle_state == "superseded":
        raise _coded_error(status.HTTP_409_CONFLICT, TRANSCRIPT_SUPERSEDED)

    projection = await get_transcript_processing_status_read(db, transcript=transcript)
    scope = resolve_retry_scope(projection)
    if not scope:
        raise _coded_error(status.HTTP_409_CONFLICT, NO_RETRYABLE_FAILURE)

    to_enqueue = await apply_retry(db, transcript=transcript, scope=scope)
    await db.commit()
    if not to_enqueue:
        # The targeted jobs were no longer failed (lost a race to a concurrent retry).
        raise _coded_error(status.HTTP_409_CONFLICT, NO_RETRYABLE_FAILURE)

    enqueue_retry_jobs(transcript_id, to_enqueue)

    refreshed = (
        await db.execute(select(Transcript).where(Transcript.id == transcript_id))
    ).scalar_one()
    projection = await get_transcript_processing_status_read(db, transcript=refreshed)
    return TranscriptProcessingStatus.model_validate(projection)


async def get_transcript_summaries(
    db: AsyncSession,
    *,
    current_user: CurrentUserContext,
    module_id: UUID,
    section_id: UUID,
) -> TranscriptSummariesRead:
    """Lecturer read surface (Stage 4.5d): the projection status + the brief and detailed summaries.

    Authz is identical to the other transcript reads (assigned lecturer → 200; non-lecturer → 403;
    unassigned/cross-tenant → 404) — ``get_active_transcript`` enforces it. ``brief``/``detailed`` are
    null until generated (or when detailed is suppressed / for pre-4.5 transcripts); the UI maps that
    gracefully rather than erroring.
    """
    transcript = await get_active_transcript(
        db,
        current_user=current_user,
        module_id=module_id,
        section_id=section_id,
    )
    projection = await get_transcript_processing_status_read(db, transcript=transcript)
    brief_row, detailed_row = await get_latest_transcript_summaries(
        db, transcript_id=transcript.id
    )
    return TranscriptSummariesRead(
        status=TranscriptProcessingStatus.model_validate(projection),
        brief=(
            BriefSummaryContent.model_validate(brief_row.content_json)
            if brief_row is not None
            else None
        ),
        detailed=(
            DetailedSummaryContent.model_validate(detailed_row.content_json)
            if detailed_row is not None
            else None
        ),
        brief_generated_at=(brief_row.generated_at if brief_row is not None else None),
        detailed_generated_at=(detailed_row.generated_at if detailed_row is not None else None),
    )


async def _enqueue_parse_job(db: AsyncSession, *, transcript_id: UUID) -> None:
    try:
        enqueue_parse_transcript(transcript_id)
    except Exception:
        logger.warning(
            "Failed to enqueue transcript parse job",
            extra={"transcript_id": str(transcript_id), "job_type": "parse"},
        )
        return

    try:
        await db.execute(
            update(Transcript)
            .where(
                Transcript.id == transcript_id,
                Transcript.status == "uploaded",
            )
            .values(status="queued")
        )
        await db.commit()
    except SQLAlchemyError:
        await db.rollback()
        logger.warning(
            "Failed to mark transcript queued after parse enqueue",
            extra={"transcript_id": str(transcript_id), "job_type": "parse"},
        )
