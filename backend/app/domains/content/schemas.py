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
