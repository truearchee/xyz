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
from app.platform.llm.models.summary import BriefSummary, DetailedSummary, DetailedSummaryPartial

BRIEF_MIN_CHARS = 20
BRIEF_MAX_CHARS = 2000
# A valid map-PARTIAL must carry every standard section key (the prompt contract: "use these keys
# exactly"), even where the value is empty for this portion. Requiring the keys PRESENT is what lets
# the last-valid-object selection still skip a reasoning model's brace-bearing thinking fragments
# (F-4.5-48) — a permissive schema alone would match `{}` and pick the wrong object.
_DETAILED_PARTIAL_REQUIRED_KEYS = (
    "overview",
    "keyConcepts",
    "importantDefinitions",
    "mainExplanations",
    "examples",
    "examRelevantPoints",
)
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


def _iter_balanced_objects(text: str) -> list[str]:
    """Return every top-level brace-balanced ``{...}`` substring, in order. String-aware so a ``}``
    inside a JSON string does not close the object early."""
    objects: list[str] = []
    index = 0
    length = len(text)
    while index < length:
        if text[index] != "{":
            index += 1
            continue
        depth = 0
        in_string = False
        escaped = False
        closed_at: int | None = None
        scan = index
        while scan < length:
            char = text[scan]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
            elif char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    closed_at = scan
                    break
            scan += 1
        if closed_at is None:
            break  # unbalanced tail; nothing more to extract
        objects.append(text[index : closed_at + 1])
        index = closed_at + 1
    return objects


def _candidate_objects(raw_text: str) -> list[dict]:
    """Tolerant extract → every parseable JSON object, in document order (§7). A reasoning-lineage
    model (K2-Think) thinks inline in ``content`` and may emit brace-like fragments and a narrated
    ``{"text": "<your paragraph>"}`` example BEFORE its real answer, which it places LAST. The caller
    selects the last object that fully validates against the target schema — neither "first" nor
    "longest" is safe, because the reasoning is itself long and brace-bearing (F-4.5-48)."""
    text = _strip_code_fences(raw_text)
    # Fast path: the whole (fence-stripped) body is a single object.
    try:
        whole = json.loads(text)
        if isinstance(whole, dict):
            return [whole]
    except (json.JSONDecodeError, ValueError):
        pass
    candidates: list[dict] = []
    for candidate in _iter_balanced_objects(text):
        try:
            parsed = json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(parsed, dict):
            candidates.append(parsed)
    return candidates


def _select_last_valid(candidates: list[dict], validate_one):
    """Return the LAST candidate that fully validates (a reasoning model puts its answer last).
    Schema-match is the filter, "last" the tiebreak. If none validate, re-raise the last failure so
    the error_code is informative (e.g. ``too_short`` when only a placeholder echo was present)."""
    last_error: InvalidOutput | None = None
    for data in reversed(candidates):
        try:
            return validate_one(data)
        except InvalidOutput as exc:
            last_error = exc
    if last_error is not None:
        raise last_error
    raise InvalidOutput("no parseable JSON object found in response", error_code="not_json")


class OutputValidator:
    def validate(
        self,
        *,
        raw_text: str,
        output_schema: type[BriefSummary] | type[DetailedSummary] | type[DetailedSummaryPartial],
        section_type: str,
    ) -> BriefSummary | DetailedSummary | DetailedSummaryPartial:
        if output_schema is BriefSummary:
            return self._validate_brief(raw_text)
        if output_schema is DetailedSummary:
            return self._validate_detailed(raw_text, section_type=section_type)
        if output_schema is DetailedSummaryPartial:
            # Map phase (4.5.1a): lenient — sections may be empty; reduce keeps the strict path.
            return self._validate_detailed_partial(raw_text)
        raise InvalidOutput(
            f"unsupported output schema: {getattr(output_schema, '__name__', output_schema)!r}",
            error_code="unsupported_schema",
        )

    def _validate_brief(self, raw_text: str) -> BriefSummary:
        # Tolerant extract → strict shape; select the LAST object that fully validates, so a
        # reasoning model's inline thinking + narrated example never reaches the student (§7).
        return _select_last_valid(_candidate_objects(raw_text), self._validate_brief_object)

    def _validate_brief_object(self, data: dict) -> BriefSummary:
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

    def _validate_detailed_partial(self, raw_text: str) -> DetailedSummaryPartial:
        # Same last-valid-object selection as the strict paths, so a reasoning model's inline thinking
        # never wins (§7). Lenient on CONTENT (sections may be empty for this portion), strict on SHAPE
        # (all standard keys present) so the selection can still discriminate the real answer.
        return _select_last_valid(
            _candidate_objects(raw_text), self._validate_detailed_partial_object
        )

    def _validate_detailed_partial_object(self, data: dict) -> DetailedSummaryPartial:
        missing = [k for k in _DETAILED_PARTIAL_REQUIRED_KEYS if k not in data]
        if missing:
            raise InvalidOutput(
                f"detailed partial missing required keys: {missing}",
                error_code="partial_missing_keys",
            )
        try:
            partial = DetailedSummaryPartial.model_validate(data)
        except ValidationError as exc:
            raise InvalidOutput(
                f"detailed partial failed schema validation: {exc.error_count()} error(s)",
                error_code="schema",
            ) from exc
        lowered = partial.overview.strip().lower()
        if lowered and any(marker in lowered for marker in _REFUSAL_MARKERS):
            raise InvalidOutput("detailed partial looks like a refusal", error_code="refusal")
        return partial

    def _validate_detailed(self, raw_text: str, *, section_type: str) -> DetailedSummary:
        # Detailed runs on the reasoning-lineage K2-Think-v2; same last-valid-object selection (§4/§7).
        return _select_last_valid(
            _candidate_objects(raw_text),
            lambda data: self._validate_detailed_object(data, section_type=section_type),
        )

    def _validate_detailed_object(self, data: dict, *, section_type: str) -> DetailedSummary:
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
