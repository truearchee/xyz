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


class TranscriptMeta(CamelModel):
    id: UUID
    module_section_id: UUID
    source_type: str
    original_file_name: str
    mime_type: str
    file_size: int
    language: str | None
    status: str
    uploaded_by_user_id: UUID | None
    created_at: datetime
    updated_at: datetime


class TranscriptProcessingStep(CamelModel):
    status: str
    started_at: datetime | None
    completed_at: datetime | None


class TranscriptProcessingSteps(CamelModel):
    upload: TranscriptProcessingStep
    parse: TranscriptProcessingStep
    chunk: TranscriptProcessingStep
    embed: TranscriptProcessingStep


class TranscriptProcessingStatus(CamelModel):
    active_transcript_id: UUID
    transcript_status: str
    overall_state: str
    current_phase: str | None
    failed_step: str | None
    steps: TranscriptProcessingSteps
    segment_count: int
    chunk_count: int
    embedded_chunk_count: int
    safe_failure_message: str | None
    updated_at: datetime
