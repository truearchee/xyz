"""Assistant output Pydantic model (Stage 8.1).

This model IS the JSON Schema the OutputValidator enforces for the interactive study-assistant chat.
A local ``CamelModel`` base keeps ``platform`` free of any dependency on ``domains`` (architecture
rule 8). 8.1 needs only the answer text; 8.2 may add structured grounding flags (e.g.
``usedLectureContext``, ``isStudyRelated``) that the backend combines with the retrieval-threshold
result to set ``groundingStatus`` deterministically — never parsed from the model's prose.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        from_attributes=True,
        populate_by_name=True,
    )


class AssistantAnswer(CamelModel):
    """`{"answer": "..."}` — the assistant's reply as markdown text."""

    answer: str
