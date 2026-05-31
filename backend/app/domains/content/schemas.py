from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        from_attributes=True,
        populate_by_name=True,
    )


class SectionAssetResponse(CamelModel):
    id: UUID
    module_section_id: UUID
    file_name: str
    mime_type: str
    file_size: int
    checksum_sha256: str
    processing_status: str
    uploaded_by_user_id: UUID
    created_at: datetime
    updated_at: datetime


class SectionAssetListResponse(CamelModel):
    assets: list[SectionAssetResponse]


class SectionListItem(CamelModel):
    id: UUID
    title: str
    type: str
    order_index: int
    has_assets: bool
    has_notes: bool


class StudentAssetMeta(CamelModel):
    id: UUID
    file_name: str
    mime_type: str
    file_size: int


class StudentSectionDetail(CamelModel):
    id: UUID
    title: str
    type: str
    order_index: int
    lecturer_notes: str | None
    assets: list[StudentAssetMeta]


class AssetDownloadUrl(CamelModel):
    url: str
    expires_at: datetime


class UpdateSectionNotesRequest(CamelModel):
    lecturer_notes: str | None


class SectionDetail(CamelModel):
    id: UUID
    course_module_id: UUID
    title: str
    type: str
    publish_status: str
    lecturer_notes: str | None
    updated_at: datetime
