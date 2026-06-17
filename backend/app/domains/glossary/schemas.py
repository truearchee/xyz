"""Glossary HTTP DTOs (Stage 7a). camelCase out, matching the generated TS client."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

EntryType = Literal["term", "concept", "formula"]
PreferredLanguage = Literal["en", "ar", "zh", "es", "fr"]


class CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        from_attributes=True,
        populate_by_name=True,
    )


# ── reads ──
class GlossaryEntryRead(CamelModel):
    id: UUID
    subject_id: UUID
    folder_id: UUID | None
    module_section_id: UUID | None
    term: str
    entry_type: str
    language: str
    short_definition: str | None
    detailed_explanation: str | None
    example: str | None
    formula_latex: str | None
    definition_status: str
    status: str
    created_at: datetime
    updated_at: datetime


class GlossarySourceReferenceRead(CamelModel):
    id: UUID
    source_type: str
    module_section_id: UUID | None
    source_summary_id: UUID | None
    source_quiz_attempt_id: UUID | None
    selected_text: str | None
    created_at: datetime


class GlossaryEntryDetail(CamelModel):
    entry: GlossaryEntryRead
    sources: list[GlossarySourceReferenceRead]


class GlossaryFolderRead(CamelModel):
    id: UUID
    name: str
    is_system: bool
    status: str
    entry_count: int


class SaveResponse(CamelModel):
    entry: GlossaryEntryRead
    duplicate: bool


# ── writes ──
class SaveHighlightRequest(CamelModel):
    module_section_id: UUID
    term: str = Field(min_length=1, max_length=200)
    selected_text: str | None = Field(default=None, max_length=2000)
    entry_type: EntryType = "term"


class ManualEntryRequest(CamelModel):
    subject_id: UUID
    term: str = Field(min_length=1, max_length=200)
    folder_id: UUID | None = None
    entry_type: EntryType = "term"


class UpdateEntryRequest(CamelModel):
    folder_id: UUID | None = None
    entry_type: EntryType | None = None


class FolderCreateRequest(CamelModel):
    name: str = Field(min_length=1, max_length=120)


class FolderUpdateRequest(CamelModel):
    name: str = Field(min_length=1, max_length=120)


# ── practice (7b/7c) ──
PracticeMode = Literal["flashcard", "multiple_choice"]
PracticeScope = Literal["course", "all"]


class PracticeOption(CamelModel):
    entry_id: UUID
    term: str


class PracticeItem(CamelModel):
    entry_id: UUID
    display_order: int
    term: str
    definition: str | None
    language: str
    # MCQ only: the 4 shuffled term options (one is the correct entry).
    options: list[PracticeOption] | None
    answered: bool
    selected_entry_id: UUID | None
    is_correct: bool | None
    outcome: str | None


class PracticeSessionState(CamelModel):
    session_id: UUID
    mode: str
    scope: str
    subject_id: UUID | None
    status: str
    items: list[PracticeItem]
    total_count: int | None
    correct_count: int | None
    not_known_count: int | None


class StartPracticeRequest(CamelModel):
    scope: PracticeScope
    subject_id: UUID | None = None
    mode: PracticeMode


class PracticeAnswerRequest(CamelModel):
    entry_id: UUID
    selected_entry_id: UUID | None = None
    outcome: Literal["known", "not_known"] | None = None


class PracticeAnswerFeedback(CamelModel):
    entry_id: UUID
    is_correct: bool | None
    correct_entry_id: UUID | None
    term: str
    definition: str | None
    outcome: str | None


class PracticeResult(CamelModel):
    session_id: UUID
    status: str
    total_count: int | None
    correct_count: int | None
    not_known_count: int | None


class PracticeAvailability(CamelModel):
    mode: str
    available: bool
    reason_code: str | None
    term_count: int
