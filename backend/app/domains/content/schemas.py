from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator
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


class SectionMetadataPatchRequest(CamelModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        from_attributes=True,
        populate_by_name=True,
        extra="forbid",
    )

    week_number: int | None = Field(default=None, ge=1)
    session_date: date | None = None
    due_at: datetime | None = None

    @model_validator(mode="after")
    def _validate_metadata_patch(self) -> SectionMetadataPatchRequest:
        fields = self.model_fields_set
        if not fields:
            raise ValueError("At least one metadata field is required")
        if "week_number" in fields and self.week_number is None:
            raise ValueError("weekNumber must be a positive integer")
        if "session_date" in fields and self.session_date is None:
            raise ValueError("sessionDate must be a valid calendar date")
        return self


class SectionMetadataDetail(CamelModel):
    id: UUID
    course_module_id: UUID
    title: str
    type: str
    order_index: int
    publish_status: str
    lecturer_notes: str | None
    week_number: int | None
    session_date: date | None
    due_at: datetime | None
    updated_at: datetime
