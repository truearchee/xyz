from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import UploadFile as StarletteUploadFile

from app.domains.content.schemas import (
    AssetDownloadUrl,
    SectionAssetListResponse,
    SectionAssetResponse,
    SectionDetail,
    SectionListItem,
    SectionMetadataDetail,
    SectionMetadataPatchRequest,
    StudentSectionDetail,
    UpdateSectionNotesRequest,
)
from app.domains.content.service import (
    authorize_lecturer_section,
    create_asset_download_url,
    get_module_section_detail,
    list_section_assets,
    list_module_sections,
    publish_section,
    replace_section_asset,
    unpublish_section,
    update_section_metadata,
    update_section_notes,
    upload_section_asset,
)
from app.platform.auth.context import CurrentUserContext, ModuleAccessContext
from app.platform.auth.dependencies import get_current_user
from app.platform.auth.guards import require_module_access
from app.platform.db.session import get_db_session
from app.platform.storage import StorageProvider, get_storage_provider


router = APIRouter(tags=["content"])

DbSession = Annotated[AsyncSession, Depends(get_db_session)]
CurrentUser = Annotated[CurrentUserContext, Depends(get_current_user)]
ModuleAccess = Annotated[ModuleAccessContext, Depends(require_module_access)]
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


@router.get("/modules/{module_id}/sections", response_model=list[SectionListItem])
async def list_sections(
    module_id: UUID,
    db: DbSession,
    module_access: ModuleAccess,
) -> list[SectionListItem]:
    return await list_module_sections(db, module_access=module_access)


@router.get(
    "/modules/{module_id}/sections/{section_id}",
    response_model=SectionDetail | StudentSectionDetail,
)
async def get_section(
    module_id: UUID,
    section_id: UUID,
    db: DbSession,
    module_access: ModuleAccess,
) -> SectionDetail | StudentSectionDetail:
    return await get_module_section_detail(
        db,
        module_access=module_access,
        section_id=section_id,
    )


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


@router.get(
    "/modules/{module_id}/sections/{section_id}/assets/{asset_id}/download-url",
    response_model=AssetDownloadUrl,
)
async def get_asset_download_url(
    module_id: UUID,
    section_id: UUID,
    asset_id: UUID,
    response: Response,
    db: DbSession,
    module_access: ModuleAccess,
    storage_provider: Storage,
) -> AssetDownloadUrl:
    download_url = await create_asset_download_url(
        db,
        module_access=module_access,
        storage_provider=storage_provider,
        section_id=section_id,
        asset_id=asset_id,
    )
    response.headers["Cache-Control"] = "no-store"
    return download_url


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


@router.patch(
    "/modules/{module_id}/sections/{section_id}/metadata",
    response_model=SectionMetadataDetail,
)
async def update_metadata(
    module_id: UUID,
    section_id: UUID,
    payload: SectionMetadataPatchRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> SectionMetadataDetail:
    return await update_section_metadata(
        db,
        current_user=current_user,
        module_id=module_id,
        section_id=section_id,
        payload=payload,
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
