"""Student-reachable quiz response models (Stage 5 DTO contract / lock 7).

These shapes are structurally incapable of leaking ``AnswerOption.isCorrect`` before a question is
answered: ``QuizOptionForStudent`` has no correctness field at all, and ``QuizQuestionForStudent``
carries correctness/explanation ONLY inside the optional ``answer`` block (present after the student
answers). ``AnswerFeedback.isCorrect`` is the student's OWN graded result, not a pre-answer leak.
Drafts only in 5a — no endpoints are wired here (start/answer/complete land in 5b/5c).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        from_attributes=True,
        populate_by_name=True,
    )


class QuizOptionForStudent(CamelModel):
    """A selectable option. NO ``isCorrect`` — correctness is never serialized pre-answer."""

    id: UUID
    text: str
    display_order: int


class AnswerForStudent(CamelModel):
    """The post-answer result embedded on a question once the student has answered it."""

    selected_answer_option_id: UUID
    is_correct: bool
    correct_answer_option_id: UUID
    explanation: str | None = None


class QuizQuestionForStudent(CamelModel):
    """A question as the student sees it. ``answer`` is null until answered (then it carries the
    correctness + explanation). No top-level ``explanation``/correctness pre-answer."""

    id: UUID
    question_text: str
    display_order: int
    question_type: str
    options: list[QuizOptionForStudent]
    answer: AnswerForStudent | None = None


class AnswerFeedback(CamelModel):
    """Immediate per-answer feedback. ``selectedAnswerOptionId`` is the ORIGINAL selected option, so a
    duplicate submit (``alreadyAnswered=True``) returns the original result, never the resubmitted one."""

    question_id: UUID
    selected_answer_option_id: UUID
    is_correct: bool
    correct_answer_option_id: UUID
    explanation: str | None = None
    already_answered: bool = False
    mistake_saved: bool = False


class QuizAttemptForStudent(CamelModel):
    """An attempt with its snapshot questions (no provenance, no isCorrect pre-answer)."""

    id: UUID
    quiz_definition_id: UUID
    status: str
    attempt_number: int
    total_questions: int | None = None
    questions: list[QuizQuestionForStudent] = []


class QuizAttemptResult(CamelModel):
    """The completed-attempt result view (score + counts)."""

    id: UUID
    status: str
    score_percentage: Decimal | None = None
    correct_count: int | None = None
    incorrect_count: int | None = None
    total_questions: int | None = None
    completed_at: datetime | None = None


class QuizAvailabilityResponse(CamelModel):
    """GET availability wire shape (Stage 5 HTTP contract)."""

    availability: str  # "available" | "unavailable"
    reason_code: str | None = None


class AnswerSubmission(CamelModel):
    """POST answer request — one question at a time."""

    question_id: UUID
    selected_answer_option_id: UUID


class QuizAttemptsSummary(CamelModel):
    """The aggregate panel line (best score · attempt count) — NOT a paginated list (ADR-041)."""

    attempt_count: int
    best_score_percentage: Decimal | None = None
