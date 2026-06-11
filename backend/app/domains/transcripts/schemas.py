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
    # Supersession lifecycle (Stage 4.6a): active | pending | superseded. Lets the lecturer UI
    # distinguish a just-uploaded replacement (pending) from the live transcript (active). Internal
    # provenance (storageKey/checksum/supersededAt/lineage) stays unexposed.
    lifecycle_state: str
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
    summary_brief: TranscriptProcessingStep
    summary_detailed: TranscriptProcessingStep


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


# Summary read shapes (Stage 4.5d). These mirror the stored contentJson (already camelCase via
# model_dump(by_alias=True)); a typed API contract lets the lecturer UI render detailed by section.
class BriefSummaryContent(CamelModel):
    text: str


class SummaryDefinition(CamelModel):
    term: str
    definition: str


class DetailedSummaryContent(CamelModel):
    overview: str
    key_concepts: list[str]
    important_definitions: list[SummaryDefinition]
    main_explanations: list[str]
    examples: list[str]
    exam_relevant_points: list[str]
    lab_notes: list[str] | None = None


class TranscriptSummariesRead(CamelModel):
    # The projection is the doneness authority (NOT transcript.status); brief/detailed are null until
    # generated (or when detailed is suppressed / on pre-4.5 transcripts → UI maps gracefully).
    status: TranscriptProcessingStatus
    brief: BriefSummaryContent | None
    detailed: DetailedSummaryContent | None
    brief_generated_at: datetime | None
    detailed_generated_at: datetime | None
