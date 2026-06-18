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
from app.platform.llm.models.assistant import AssistantAnswer
from app.platform.llm.models.quiz import GeneratedQuizPool, PostClassQuiz
from app.platform.llm.models.summary import BriefSummary, DetailedSummary

BRIEF_MIN_CHARS = 20
BRIEF_MAX_CHARS = 2000

# Assistant chat answer bounds (Stage 8.1). Lower floor than brief: a legitimate
# ``educational_redirect`` ("Let's focus on the lecture — what would you like to review?") is short.
# NO refusal-marker rejection here — a polite redirect is valid output, not a refusal to reject.
ASSISTANT_MIN_CHARS = 1
ASSISTANT_MAX_CHARS = 12000

# Quiz structure + size limits (Stage 5b §5). The validator is the AUTHORITY regardless of the
# generation mechanism. "No HTML" = ESCAPE-ON-DISPLAY, not reject-on-angle-bracket: legitimate
# math/code contains ``<``/``>`` so the validator NEVER rejects content for those — escaping is the
# UI's job at render time. Counts mirror QuizDefinition.question_policy {count:10, optionsPerQuestion:4}.
QUIZ_QUESTION_COUNT = 10
QUIZ_OPTIONS_PER_QUESTION = 4
QUIZ_MAX_PAYLOAD_BYTES = 65536
QUIZ_MAX_QUESTION_CHARS = 1000
QUIZ_MAX_OPTION_CHARS = 500
QUIZ_MAX_EXPLANATION_CHARS = 2000

# Stage 6a — section POOL bounds (the validator is the authority regardless of mechanism). A pool holds
# MORE than one quiz needs; the count is a RANGE, not exactly-N, so a reasoning model over/undershooting
# the requested target does not fail the whole generation. The per-question rules (4 options, one correct,
# length/dup caps) are identical to post_class. Larger payload cap because there are more questions.
# Floor lowered 16→12 (F-6e): the prompt's requested count was trimmed 24→16 to bound live wall-clock, so
# the floor must sit BELOW the target to keep the over/undershoot tolerance — 12 still exceeds the largest
# single draw (post_class = 10), preserving "the pool holds more than one quiz needs".
QUIZ_POOL_MIN_COUNT = 12
QUIZ_POOL_MAX_COUNT = 40
QUIZ_POOL_MAX_PAYLOAD_BYTES = 262144
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
        output_schema: type[BriefSummary]
        | type[DetailedSummary]
        | type[PostClassQuiz]
        | type[GeneratedQuizPool]
        | type[AssistantAnswer],
        section_type: str,
    ) -> BriefSummary | DetailedSummary | PostClassQuiz | GeneratedQuizPool | AssistantAnswer:
        if output_schema is BriefSummary:
            return self._validate_brief(raw_text)
        if output_schema is DetailedSummary:
            return self._validate_detailed(raw_text, section_type=section_type)
        if output_schema is PostClassQuiz:
            return self._validate_quiz(raw_text)
        if output_schema is GeneratedQuizPool:
            return self._validate_quiz_pool(raw_text)
        if output_schema is AssistantAnswer:
            return self._validate_assistant(raw_text)
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

    # ── assistant chat (Stage 8.1) ───────────────────────────────────────────────────────────────
    def _validate_assistant(self, raw_text: str) -> AssistantAnswer:
        # Same tolerant extract + last-valid selection as summaries (K2-Think may think inline and put
        # its real JSON last). Schema-match filters; "last" tiebreaks.
        return _select_last_valid(_candidate_objects(raw_text), self._validate_assistant_object)

    def _validate_assistant_object(self, data: dict) -> AssistantAnswer:
        try:
            message = AssistantAnswer.model_validate(data)
        except ValidationError as exc:
            raise InvalidOutput(
                f"assistant answer failed schema validation: {exc.error_count()} error(s)",
                error_code="schema",
            ) from exc
        answer = message.answer.strip()
        if len(answer) < ASSISTANT_MIN_CHARS:
            raise InvalidOutput("assistant answer is empty", error_code="too_short")
        if len(answer) > ASSISTANT_MAX_CHARS:
            raise InvalidOutput("assistant answer is too long", error_code="too_long")
        # NB: NO refusal-marker check — a polite educational_redirect is legitimate assistant output.
        return message

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

    def _validate_quiz(self, raw_text: str) -> PostClassQuiz:
        # Same tolerant extract + last-valid selection as summaries (a reasoning model puts its answer
        # last). Schema-match filters; "last" tiebreaks.
        return _select_last_valid(_candidate_objects(raw_text), self._validate_quiz_object)

    def _validate_quiz_object(self, data: dict) -> PostClassQuiz:
        try:
            quiz = PostClassQuiz.model_validate(data)
        except ValidationError as exc:
            raise InvalidOutput(
                f"quiz failed schema validation: {exc.error_count()} error(s)",
                error_code="schema",
            ) from exc

        # Overall: exactly QUIZ_QUESTION_COUNT questions; no duplicate questionText.
        if len(quiz.questions) != QUIZ_QUESTION_COUNT:
            raise InvalidOutput(
                f"quiz must have exactly {QUIZ_QUESTION_COUNT} questions, got {len(quiz.questions)}",
                error_code="wrong_question_count",
            )
        seen_questions: set[str] = set()
        for index, question in enumerate(quiz.questions):
            q_text = question.question_text.strip()
            if not q_text:
                raise InvalidOutput(
                    f"question {index} has empty questionText", error_code="empty_question_text"
                )
            if len(q_text) > QUIZ_MAX_QUESTION_CHARS:
                raise InvalidOutput(
                    f"question {index} questionText exceeds {QUIZ_MAX_QUESTION_CHARS} chars",
                    error_code="question_too_long",
                )
            key = q_text.lower()
            if key in seen_questions:
                raise InvalidOutput(
                    f"duplicate questionText at question {index}", error_code="duplicate_question"
                )
            seen_questions.add(key)

            # Per question: exactly N options; exactly one correct; no empty/duplicate option text.
            if len(question.options) != QUIZ_OPTIONS_PER_QUESTION:
                raise InvalidOutput(
                    f"question {index} must have exactly {QUIZ_OPTIONS_PER_QUESTION} options, "
                    f"got {len(question.options)}",
                    error_code="wrong_option_count",
                )
            correct = [opt for opt in question.options if opt.is_correct]
            if len(correct) != 1:
                raise InvalidOutput(
                    f"question {index} must have exactly one correct option, got {len(correct)}",
                    error_code="wrong_correct_count",
                )
            seen_options: set[str] = set()
            for opt in question.options:
                o_text = opt.text.strip()
                if not o_text:
                    raise InvalidOutput(
                        f"question {index} has an empty option", error_code="empty_option_text"
                    )
                if len(o_text) > QUIZ_MAX_OPTION_CHARS:
                    raise InvalidOutput(
                        f"question {index} option exceeds {QUIZ_MAX_OPTION_CHARS} chars",
                        error_code="option_too_long",
                    )
                o_key = o_text.lower()
                if o_key in seen_options:
                    raise InvalidOutput(
                        f"question {index} has duplicate option text",
                        error_code="duplicate_option",
                    )
                seen_options.add(o_key)

            explanation = question.explanation.strip()
            if not explanation:
                raise InvalidOutput(
                    f"question {index} is missing an explanation", error_code="missing_explanation"
                )
            if len(explanation) > QUIZ_MAX_EXPLANATION_CHARS:
                raise InvalidOutput(
                    f"question {index} explanation exceeds {QUIZ_MAX_EXPLANATION_CHARS} chars",
                    error_code="explanation_too_long",
                )

        # Size: the validated quiz payload must fit the cap (configurable).
        payload_bytes = len(json.dumps(quiz.model_dump(by_alias=True)).encode("utf-8"))
        if payload_bytes > QUIZ_MAX_PAYLOAD_BYTES:
            raise InvalidOutput(
                f"quiz payload {payload_bytes} bytes exceeds {QUIZ_MAX_PAYLOAD_BYTES}",
                error_code="payload_too_large",
            )
        return quiz

    # ── pool generation (Stage 6a) ───────────────────────────────────────────────────────────────
    # Deliberately a SEPARATE validator from _validate_quiz / _validate_quiz_object: the shipped
    # post_class path (exactly-10) is left byte-for-byte untouched. The per-question rules below mirror
    # _validate_quiz_object; only the COUNT is a range (a pool holds more than one quiz) and the payload
    # cap is larger. Reuses the same tolerant-extract + last-valid machinery.
    def _validate_quiz_pool(self, raw_text: str) -> GeneratedQuizPool:
        return _select_last_valid(_candidate_objects(raw_text), self._validate_quiz_pool_object)

    def _validate_quiz_pool_object(self, data: dict) -> GeneratedQuizPool:
        try:
            pool = GeneratedQuizPool.model_validate(data)
        except ValidationError as exc:
            raise InvalidOutput(
                f"quiz pool failed schema validation: {exc.error_count()} error(s)",
                error_code="schema",
            ) from exc

        if not (QUIZ_POOL_MIN_COUNT <= len(pool.questions) <= QUIZ_POOL_MAX_COUNT):
            raise InvalidOutput(
                f"quiz pool must have between {QUIZ_POOL_MIN_COUNT} and {QUIZ_POOL_MAX_COUNT} "
                f"questions, got {len(pool.questions)}",
                error_code="wrong_question_count",
            )
        seen_questions: set[str] = set()
        for index, question in enumerate(pool.questions):
            q_text = question.question_text.strip()
            if not q_text:
                raise InvalidOutput(
                    f"question {index} has empty questionText", error_code="empty_question_text"
                )
            if len(q_text) > QUIZ_MAX_QUESTION_CHARS:
                raise InvalidOutput(
                    f"question {index} questionText exceeds {QUIZ_MAX_QUESTION_CHARS} chars",
                    error_code="question_too_long",
                )
            key = q_text.lower()
            if key in seen_questions:
                raise InvalidOutput(
                    f"duplicate questionText at question {index}", error_code="duplicate_question"
                )
            seen_questions.add(key)

            if len(question.options) != QUIZ_OPTIONS_PER_QUESTION:
                raise InvalidOutput(
                    f"question {index} must have exactly {QUIZ_OPTIONS_PER_QUESTION} options, "
                    f"got {len(question.options)}",
                    error_code="wrong_option_count",
                )
            correct = [opt for opt in question.options if opt.is_correct]
            if len(correct) != 1:
                raise InvalidOutput(
                    f"question {index} must have exactly one correct option, got {len(correct)}",
                    error_code="wrong_correct_count",
                )
            seen_options: set[str] = set()
            for opt in question.options:
                o_text = opt.text.strip()
                if not o_text:
                    raise InvalidOutput(
                        f"question {index} has an empty option", error_code="empty_option_text"
                    )
                if len(o_text) > QUIZ_MAX_OPTION_CHARS:
                    raise InvalidOutput(
                        f"question {index} option exceeds {QUIZ_MAX_OPTION_CHARS} chars",
                        error_code="option_too_long",
                    )
                o_key = o_text.lower()
                if o_key in seen_options:
                    raise InvalidOutput(
                        f"question {index} has duplicate option text",
                        error_code="duplicate_option",
                    )
                seen_options.add(o_key)

            explanation = question.explanation.strip()
            if not explanation:
                raise InvalidOutput(
                    f"question {index} is missing an explanation", error_code="missing_explanation"
                )
            if len(explanation) > QUIZ_MAX_EXPLANATION_CHARS:
                raise InvalidOutput(
                    f"question {index} explanation exceeds {QUIZ_MAX_EXPLANATION_CHARS} chars",
                    error_code="explanation_too_long",
                )

        payload_bytes = len(json.dumps(pool.model_dump(by_alias=True)).encode("utf-8"))
        if payload_bytes > QUIZ_POOL_MAX_PAYLOAD_BYTES:
            raise InvalidOutput(
                f"quiz pool payload {payload_bytes} bytes exceeds {QUIZ_POOL_MAX_PAYLOAD_BYTES}",
                error_code="payload_too_large",
            )
        return pool
