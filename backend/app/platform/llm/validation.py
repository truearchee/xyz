"""OutputValidator (spec §6.7).

Structure is the contract, not "non-empty text". The validator parses the raw provider text to the
``output_schema`` Pydantic model and enforces:
  - brief: non-empty ``text`` within length bounds; reject obvious refusals/chatter.
  - detailed: required sections present and non-empty; ``labNotes`` required only for lab sections.
Any failure raises ``InvalidOutput`` (retryable, bounded).
"""

from __future__ import annotations

import json

from pydantic import ValidationError

from app.platform.llm.errors import InvalidOutput
from app.platform.llm.models.summary import BriefSummary, DetailedSummary

BRIEF_MIN_CHARS = 20
BRIEF_MAX_CHARS = 2000
_REFUSAL_MARKERS = (
    "i cannot",
    "i can't",
    "i am unable",
    "i'm unable",
    "as an ai",
    "i'm sorry, but",
)


def _strip_code_fences(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _parse_json_object(raw_text: str) -> dict:
    text = _strip_code_fences(raw_text)
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError) as exc:
        raise InvalidOutput(
            f"response is not valid JSON: {exc}", error_code="not_json"
        ) from exc
    if not isinstance(data, dict):
        raise InvalidOutput("response JSON must be an object", error_code="not_object")
    return data


class OutputValidator:
    def validate(
        self,
        *,
        raw_text: str,
        output_schema: type[BriefSummary] | type[DetailedSummary],
        section_type: str,
    ) -> BriefSummary | DetailedSummary:
        if output_schema is BriefSummary:
            return self._validate_brief(raw_text)
        if output_schema is DetailedSummary:
            return self._validate_detailed(raw_text, section_type=section_type)
        raise InvalidOutput(
            f"unsupported output schema: {getattr(output_schema, '__name__', output_schema)!r}",
            error_code="unsupported_schema",
        )

    def _validate_brief(self, raw_text: str) -> BriefSummary:
        data = _parse_json_object(raw_text)
        try:
            brief = BriefSummary.model_validate(data)
        except ValidationError as exc:
            raise InvalidOutput(
                f"brief summary failed schema validation: {exc.error_count()} error(s)",
                error_code="schema",
            ) from exc
        text = brief.text.strip()
        if len(text) < BRIEF_MIN_CHARS:
            raise InvalidOutput("brief summary text is too short", error_code="too_short")
        if len(text) > BRIEF_MAX_CHARS:
            raise InvalidOutput("brief summary text is too long", error_code="too_long")
        lowered = text.lower()
        if any(marker in lowered for marker in _REFUSAL_MARKERS):
            raise InvalidOutput("brief summary looks like a refusal", error_code="refusal")
        return brief

    def _validate_detailed(self, raw_text: str, *, section_type: str) -> DetailedSummary:
        data = _parse_json_object(raw_text)
        try:
            detailed = DetailedSummary.model_validate(data)
        except ValidationError as exc:
            raise InvalidOutput(
                f"detailed summary failed schema validation: {exc.error_count()} error(s)",
                error_code="schema",
            ) from exc

        required_lists = {
            "keyConcepts": detailed.key_concepts,
            "importantDefinitions": detailed.important_definitions,
            "mainExplanations": detailed.main_explanations,
            "examples": detailed.examples,
            "examRelevantPoints": detailed.exam_relevant_points,
        }
        if not detailed.overview.strip():
            raise InvalidOutput("detailed summary overview is empty", error_code="missing_overview")
        empty = [name for name, value in required_lists.items() if not value]
        if empty:
            raise InvalidOutput(
                f"detailed summary missing required sections: {empty}",
                error_code="missing_section",
            )
        if section_type == "lab" and not detailed.lab_notes:
            raise InvalidOutput(
                "lab section requires non-empty labNotes",
                error_code="missing_lab_notes",
            )
        return detailed
