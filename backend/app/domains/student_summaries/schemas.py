"""Student-reachable response models (Stage 4.7 §8.3).

These models are deliberately the WHOLE student-facing contract: a student response is structurally
incapable of serializing transcript/segment/chunk text, provenance (checksum, modelId, promptVersion,
tokens), job ids, error messages, storage keys, the raw transcript filename, or overallState/steps
internals. Summary ``content`` is a server-rendered markdown string (markdown.py), non-null only when
``state == ready``. Flat ``{state, content:nullable}`` (H2, ratified) — not a discriminated union — so
the generated TS client (rule 3) stays clean.
"""

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


# ---- summaries sub-resource (content + state) — §8.2 endpoint 2 -------------------------------------
class StudentSummarySlot(CamelModel):
    """One slot's state + content. ``content`` is non-null ONLY when ``state == 'ready'``."""

    state: str  # ready | generating | unavailable | not_applicable
    content: str | None = None


class StudentSectionSummariesContent(CamelModel):
    brief: StudentSummarySlot
    detailed: StudentSummarySlot


class StudentSectionSummariesRead(CamelModel):
    section_id: UUID
    summaries: StudentSectionSummariesContent


# ---- section detail (state only, no content) — §8.2 endpoint 1 -------------------------------------
class StudentSummarySlotState(CamelModel):
    state: str  # ready | generating | unavailable | not_applicable  (no content)


class StudentSectionSummaryStates(CamelModel):
    brief: StudentSummarySlotState
    detailed: StudentSummarySlotState


class StudentMaterialMeta(CamelModel):
    """Published learning material (the lecturer-uploaded asset) — same safe shape as Stage 3."""

    id: UUID
    file_name: str
    mime_type: str
    file_size: int
    asset_kind: str


class StudentSectionRead(CamelModel):
    id: UUID
    title: str
    type: str
    order_index: int
    due_at: datetime | None
    lecturer_notes: str | None
    materials: list[StudentMaterialMeta]
    summaries: StudentSectionSummaryStates


# ---- module section list with the coarse summaries flag — §8.1 --------------------------------------
class StudentSectionListItem(CamelModel):
    id: UUID
    title: str
    type: str
    order_index: int
    has_notes: bool
    has_materials: bool
    summaries_state: str  # ready | partial | generating | none | not_applicable
