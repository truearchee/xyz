"""Recommendation-copy output schema (Stage 11.2).

The model produces wording only. Deterministic eligibility, reasons, numbers, and visibility are
validated in the analytics domain before any AI text is persisted or returned.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

RECOMMENDATION_COPY_SCHEMA_VERSION = "recommendation-copy-v1"


class CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        from_attributes=True,
        populate_by_name=True,
    )


class RecommendationCopy(CamelModel):
    lecturer_draft: str
    student_nudge: str
