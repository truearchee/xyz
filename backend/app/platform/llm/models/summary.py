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
# Map-reduce (4.5.1a, F-4.5-51): a per-unit PARTIAL detailed summary. Same shape as DetailedSummary,
# but every section may legitimately be empty for a given portion of the lecture.
DETAILED_PARTIAL_SCHEMA_VERSION = "detailed-partial-v1"


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


class DetailedSummaryPartial(CamelModel):
    """One map-unit's partial extraction (4.5.1a, F-4.5-51).

    Structurally identical to ``DetailedSummary`` but every section DEFAULTS EMPTY: a single portion of
    a lecture may carry no examples/definitions/etc. A distinct TYPE (not just looser validation) is
    required because ``OutputValidator.validate`` dispatches on ``output_schema is DetailedSummary`` —
    the partial must dispatch to the lenient branch while reduce keeps the strict ``DetailedSummary``
    contract untouched. The reduce step MERGES these into one coherent ``DetailedSummary``.
    """

    overview: str = ""
    key_concepts: list[str] = []
    important_definitions: list[Definition] = []
    main_explanations: list[str] = []
    examples: list[str] = []
    exam_relevant_points: list[str] = []
    lab_notes: list[str] | None = None
