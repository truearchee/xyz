from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import UploadFile as StarletteUploadFile

from app.domains.transcripts.schemas import TranscriptMeta, TranscriptProcessingStatus
from app.domains.transcripts.service import (
    get_active_transcript,
    get_transcript_processing_status,
    prepare_transcript_upload,
    upload_transcript,
)
from app.platform.auth.context import CurrentUserContext
from app.platform.auth.dependencies import get_current_user
from app.platform.db.session import get_db_session
from app.platform.storage import StorageProvider, get_storage_provider


router = APIRouter(tags=["transcripts"])

DbSession = Annotated[AsyncSession, Depends(get_db_session)]
CurrentUser = Annotated[CurrentUserContext, Depends(get_current_user)]
Storage = Annotated[StorageProvider, Depends(get_storage_provider)]

_MULTIPART_FILE_OPENAPI = {
    "requestBody": {
        "required": True,
        "content": {
            "multipart/form-data": {
                "schema": {
                    "type": "object",
                    "required": ["file"],
                    "properties": {
                        "file": {
                            "type": "string",
                            "format": "binary",
                        }
                    },
                }
            }
        },
    }
}


async def _extract_transcript_multipart_file(request: Request) -> UploadFile:
    form = await request.form()
    file_parts: list[UploadFile] = []
    unexpected_file_parts: list[str] = []

    for key, value in form.multi_items():
        if isinstance(value, StarletteUploadFile):
            if key == "file":
                file_parts.append(value)
            else:
                unexpected_file_parts.append(key)

    if len(file_parts) != 1 or unexpected_file_parts:
        raise HTTPException(
            status_code=422,
            detail="Exactly one multipart file field named 'file' is required",
        )
    return file_parts[0]


@router.post(
    "/modules/{module_id}/sections/{section_id}/transcript",
    response_model=TranscriptMeta,
    status_code=status.HTTP_201_CREATED,
    operation_id="uploadSectionTranscript",
    openapi_extra=_MULTIPART_FILE_OPENAPI,
)
async def upload_section_transcript(
    module_id: UUID,
    section_id: UUID,
    request: Request,
    db: DbSession,
    current_user: CurrentUser,
    storage_provider: Storage,
) -> TranscriptMeta:
    section_context = await prepare_transcript_upload(
        db,
        current_user=current_user,
        module_id=module_id,
        section_id=section_id,
    )
    file = await _extract_transcript_multipart_file(request)
    return await upload_transcript(
        db,
        current_user=current_user,
        storage_provider=storage_provider,
        section_context=section_context,
        upload=file,
    )


@router.get(
    "/modules/{module_id}/sections/{section_id}/transcript",
    response_model=TranscriptMeta,
    operation_id="getSectionTranscript",
)
async def get_section_transcript(
    module_id: UUID,
    section_id: UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> TranscriptMeta:
    return await get_active_transcript(
        db,
        current_user=current_user,
        module_id=module_id,
        section_id=section_id,
    )


@router.get(
    "/modules/{module_id}/sections/{section_id}/transcript-processing-status",
    response_model=TranscriptProcessingStatus,
    operation_id="getSectionTranscriptProcessingStatus",
)
async def get_section_transcript_processing_status(
    module_id: UUID,
    section_id: UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> TranscriptProcessingStatus:
    return await get_transcript_processing_status(
        db,
        current_user=current_user,
        module_id=module_id,
        section_id=section_id,
    )
