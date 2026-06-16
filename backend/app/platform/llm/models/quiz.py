"""Quiz generation output Pydantic model (Stage 5b, mirrors summary.py / adr-027).

This model IS the JSON Schema the OutputValidator enforces for ``post_class_quiz_generation``. One AI
call per attempt produces all questions (rule 15). The local ``CamelModel`` keeps ``platform`` free of
any dependency on ``domains`` (architecture rule 8). Correctness is carried on the OPTION
(``is_correct``); the gateway never trusts a letter/position. The validator (not this schema) enforces
the counts, one-correct, no-dupes, and size limits.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

QUIZ_SCHEMA_VERSION = "quiz-v1"


class CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        from_attributes=True,
        populate_by_name=True,
    )


class GeneratedQuizOption(CamelModel):
    text: str
    is_correct: bool


class GeneratedQuizQuestion(CamelModel):
    question_text: str
    options: list[GeneratedQuizOption]
    explanation: str


class PostClassQuiz(CamelModel):
    questions: list[GeneratedQuizQuestion]
