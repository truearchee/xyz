from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import UploadFile as StarletteUploadFile

from app.domains.content.schemas import (
    SectionAssetListResponse,
    SectionAssetResponse,
    SectionDetail,
    UpdateSectionNotesRequest,
)
from app.domains.content.service import (
    authorize_lecturer_section,
    list_section_assets,
    publish_section,
    replace_section_asset,
    unpublish_section,
    update_section_notes,
    upload_section_asset,
)
from app.platform.auth.context import CurrentUserContext
from app.platform.auth.dependencies import get_current_user
from app.platform.db.session import get_db_session
from app.platform.storage import StorageProvider, get_storage_provider


router = APIRouter(tags=["content"])

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


async def _extract_multipart_file(request: Request) -> UploadFile:
    form = await request.form()
    file = form.get("file")
    if not isinstance(file, StarletteUploadFile):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Multipart field 'file' is required",
        )
    return file


@router.get(
    "/modules/{module_id}/sections/{section_id}/assets",
    response_model=SectionAssetListResponse,
)
async def list_assets(
    module_id: UUID,
    section_id: UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> SectionAssetListResponse:
    assets = await list_section_assets(
        db,
        current_user=current_user,
        module_id=module_id,
        section_id=section_id,
    )
    return SectionAssetListResponse(assets=assets)


@router.post(
    "/modules/{module_id}/sections/{section_id}/assets",
    response_model=SectionAssetResponse,
    status_code=status.HTTP_201_CREATED,
    openapi_extra=_MULTIPART_FILE_OPENAPI,
)
async def upload_asset(
    module_id: UUID,
    section_id: UUID,
    request: Request,
    db: DbSession,
    current_user: CurrentUser,
    storage_provider: Storage,
) -> SectionAssetResponse:
    await authorize_lecturer_section(
        db,
        current_user=current_user,
        module_id=module_id,
        section_id=section_id,
    )
    file = await _extract_multipart_file(request)
    return await upload_section_asset(
        db,
        current_user=current_user,
        storage_provider=storage_provider,
        module_id=module_id,
        section_id=section_id,
        upload=file,
        authorize=False,
    )


@router.put(
    "/modules/{module_id}/sections/{section_id}/assets/{asset_id}",
    response_model=SectionAssetResponse,
    openapi_extra=_MULTIPART_FILE_OPENAPI,
)
async def replace_asset(
    module_id: UUID,
    section_id: UUID,
    asset_id: UUID,
    request: Request,
    db: DbSession,
    current_user: CurrentUser,
    storage_provider: Storage,
) -> SectionAssetResponse:
    await authorize_lecturer_section(
        db,
        current_user=current_user,
        module_id=module_id,
        section_id=section_id,
    )
    file = await _extract_multipart_file(request)
    return await replace_section_asset(
        db,
        current_user=current_user,
        storage_provider=storage_provider,
        module_id=module_id,
        section_id=section_id,
        asset_id=asset_id,
        upload=file,
        authorize=False,
    )


@router.patch(
    "/modules/{module_id}/sections/{section_id}/notes",
    response_model=SectionDetail,
)
async def update_notes(
    module_id: UUID,
    section_id: UUID,
    payload: UpdateSectionNotesRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> SectionDetail:
    return await update_section_notes(
        db,
        current_user=current_user,
        module_id=module_id,
        section_id=section_id,
        lecturer_notes=payload.lecturer_notes,
    )


@router.post(
    "/modules/{module_id}/sections/{section_id}/publish",
    response_model=SectionDetail,
)
async def publish(
    module_id: UUID,
    section_id: UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> SectionDetail:
    return await publish_section(
        db,
        current_user=current_user,
        module_id=module_id,
        section_id=section_id,
    )


@router.post(
    "/modules/{module_id}/sections/{section_id}/unpublish",
    response_model=SectionDetail,
)
async def unpublish(
    module_id: UUID,
    section_id: UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> SectionDetail:
    return await unpublish_section(
        db,
        current_user=current_user,
        module_id=module_id,
        section_id=section_id,
    )
