"""Summary output Pydantic models (D1, adr-027).

These models ARE the JSON Schema the OutputValidator enforces. A local ``CamelModel`` base keeps
``platform`` free of any dependency on ``domains`` (architecture rule 8). ``content_json`` is
stored with ``model_dump(by_alias=True)`` so the persisted shape matches the spec's camelCase
``contentJson``.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

BRIEF_SCHEMA_VERSION = "brief-v1"
DETAILED_SCHEMA_VERSION = "detailed-v1"


class CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        from_attributes=True,
        populate_by_name=True,
    )


class BriefSummary(CamelModel):
    """`{"text": "..."}` — a short, length-bounded paragraph."""

    text: str


class Definition(CamelModel):
    term: str
    definition: str


class DetailedSummary(CamelModel):
    """Structured study summary keyed by section (§7.1)."""

    overview: str
    key_concepts: list[str]
    important_definitions: list[Definition]
    main_explanations: list[str]
    examples: list[str]
    exam_relevant_points: list[str]
    # Required only when the section type is `lab`; enforced by DetailedSummaryValidator.
    lab_notes: list[str] | None = None
