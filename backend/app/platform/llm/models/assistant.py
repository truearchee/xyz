"""Assistant output Pydantic models (Stage 8.1 + 8.2).

These models ARE the JSON Schema the OutputValidator enforces for the interactive study-assistant chat.
A local ``CamelModel`` base keeps ``platform`` free of any dependency on ``domains`` (architecture
rule 8).

- 8.1 ``AssistantAnswer`` = ``{"answer": "..."}`` (left untouched).
- 8.2 ``AssistantGroundedAnswer`` adds the single structured grounding flag ``isStudyRelated``. The
  backend combines that flag with the retrieval-threshold result (``decide_grounding``) to set
  ``groundingStatus`` DETERMINISTICALLY — never parsed from the model's prose. The flag is REQUIRED:
  if the model omits it, validation fails (``invalid_output``) and the turn is marked failed/retryable
  rather than silently defaulting to grounded or general (review #4, fail-safe).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


# Stable label that the generation service stamps immediately before the student's latest question when
# it composes the v2 ``{{transcript}}`` blob (retrieved-context + history + latest-question). It lives in
# platform so BOTH the domain composer and the platform deterministic test double reference one literal
# (rule 8: domain imports platform). The v2 prompt's static system text must never contain this literal.
ASSISTANT_LATEST_QUESTION_MARKER = "STUDENT'S LATEST QUESTION:"


class CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        from_attributes=True,
        populate_by_name=True,
    )


class AssistantAnswer(CamelModel):
    """`{"answer": "..."}` — the assistant's reply as markdown text (Stage 8.1)."""

    answer: str


class AssistantGroundedAnswer(CamelModel):
    """`{"answer": "...", "isStudyRelated": true|false}` — Stage 8.2.

    ``isStudyRelated`` is the ONLY model-judged grounding signal; it is REQUIRED (no default). All other
    grounding inputs (visibility, readiness, has-relevant-chunk) are backend-derived. ``decide_grounding``
    combines them into the final ``groundingStatus``."""

    answer: str
    is_study_related: bool
