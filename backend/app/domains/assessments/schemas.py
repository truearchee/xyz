"""AssessmentScope HTTP DTOs (Stage 6b)."""

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


class CreateAssessmentScopeRequest(CamelModel):
    name: str
    covered_weeks: list[int]


class UpdateAssessmentScopeRequest(CamelModel):
    name: str | None = None
    covered_weeks: list[int] | None = None


class AssessmentScopeResponse(CamelModel):
    id: UUID
    module_id: UUID
    name: str
    covered_weeks: list[int]
    status: str
    created_at: datetime
    updated_at: datetime
