from __future__ import annotations

import logging
from uuid import UUID

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from uuid6 import uuid7

from app.domains.transcripts.validators import (
    InvalidTranscriptError,
    TranscriptUploadTooLargeError,
    spool_and_validate_transcript,
)
from app.platform.auth.context import CurrentUserContext
from app.platform.config import settings
from app.platform.db.models import Transcript
from app.platform.query.section_context import (
    AuthorizedSectionContext,
    get_authorized_lecturer_section_context,
)
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
    return "uq_active_transcript_per_section" in str(exc)


async def _ensure_no_active_transcript(
    db: AsyncSession,
    *,
    section_id: UUID,
) -> None:
    result = await db.execute(
        select(Transcript.id)
        .where(
            Transcript.module_section_id == section_id,
            Transcript.is_active.is_(True),
        )
        .limit(1)
    )
    if result.first() is not None:
        raise _coded_error(status.HTTP_409_CONFLICT, TRANSCRIPT_ALREADY_EXISTS)


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
    await _ensure_no_active_transcript(db, section_id=section_context.section_id)
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

    transcript = Transcript(
        id=transcript_id,
        module_section_id=section_context.section_id,
        source_type="manual_upload",
        original_file_name=validated.original_file_name,
        storage_key=storage_key,
        mime_type=validated.effective_mime_type,
        file_size=validated.size_bytes,
        checksum=validated.sha256,
        language=None,
        status="uploaded",
        uploaded_by_user_id=current_user.user_id,
        is_active=True,
    )
    db.add(transcript)

    try:
        await db.commit()
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
            Transcript.is_active.is_(True),
        )
    )
    transcript = result.scalar_one_or_none()
    if transcript is None:
        raise _coded_error(status.HTTP_404_NOT_FOUND, TRANSCRIPT_NOT_FOUND)
    return transcript


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
