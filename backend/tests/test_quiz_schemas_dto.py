"""Stage 5a — student DTO no-leak contract (lock 7).

The student-facing option/question DTOs are structurally incapable of serializing ``AnswerOption.isCorrect``
or an explanation before the question is answered. Correctness/explanation appear ONLY inside the optional
``answer`` block (post-answer) and on ``AnswerFeedback`` (the student's own result). Pure unit tests — no DB.
"""

from __future__ import annotations

from uuid import uuid4

from app.domains.quiz.schemas import (
    AnswerFeedback,
    QuizOptionForStudent,
    QuizQuestionForStudent,
)


def _all_keys(value: object) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        for k, v in value.items():
            keys.add(k)
            keys |= _all_keys(v)
    elif isinstance(value, list):
        for item in value:
            keys |= _all_keys(item)
    return keys


def test_student_option_dto_excludes_is_correct() -> None:
    assert "is_correct" not in QuizOptionForStudent.model_fields
    properties = QuizOptionForStudent.model_json_schema()["properties"]
    assert "isCorrect" not in properties
    assert not any("correct" in key.lower() for key in properties)


def test_pre_answer_question_dump_has_no_correctness_or_explanation() -> None:
    question = QuizQuestionForStudent(
        id=uuid4(),
        question_text="What is 2 + 2? Note: 3 < x < 5.",
        display_order=0,
        question_type="multiple_choice",
        options=[
            QuizOptionForStudent(id=uuid4(), text="3", display_order=0),
            QuizOptionForStudent(id=uuid4(), text="4", display_order=1),
        ],
        answer=None,
    )
    dumped = question.model_dump(by_alias=True)
    keys = _all_keys(dumped)
    # Pre-answer: no correctness signal and no explanation anywhere in the payload.
    assert "isCorrect" not in keys
    assert "is_correct" not in keys
    assert "explanation" not in keys
    assert "correctAnswerOptionId" not in keys
    # The raw question text (with < >) is preserved faithfully (escape-on-display, not reject).
    assert dumped["questionText"] == "What is 2 + 2? Note: 3 < x < 5."


def test_answer_feedback_exposes_is_correct() -> None:
    # Positive control: the guard is targeted, not blanket — the student's OWN result IS exposed.
    assert "is_correct" in AnswerFeedback.model_fields
    properties = AnswerFeedback.model_json_schema()["properties"]
    assert "isCorrect" in properties
    assert "correctAnswerOptionId" in properties
