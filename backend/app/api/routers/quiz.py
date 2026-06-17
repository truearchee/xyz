"""Student-facing quiz HTTP surface (Stage 5c).

Section-scoped + attempt-scoped routes ONLY (no by-question route → IDOR closure). Every response carries
``Cache-Control: private, no-store`` (access-sensitive + user-specific: no cache may preserve a stale 200
after unpublish or membership removal). The role gate (403) and the visibility gate (pinned 404) fire in
the service before any resource work; non-student → 403 uniformly; hidden/not-owner → 404.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.quiz import service
from app.domains.quiz.schemas import (
    AnswerFeedback,
    AnswerSubmission,
    QuizAttemptForStudent,
    QuizAttemptResult,
    QuizAttemptsSummary,
    QuizAvailabilityResponse,
)
from app.platform.auth.context import CurrentUserContext
from app.platform.auth.dependencies import get_current_user
from app.platform.db.session import get_db_session

router = APIRouter(tags=["quiz"])

DbSession = Annotated[AsyncSession, Depends(get_db_session)]
CurrentUser = Annotated[CurrentUserContext, Depends(get_current_user)]

_NO_STORE = "private, no-store"


@router.get(
    "/student/sections/{section_id}/quiz/availability",
    response_model=QuizAvailabilityResponse,
    operation_id="getStudentQuizAvailability",
)
async def get_quiz_availability(
    section_id: UUID, response: Response, db: DbSession, current_user: CurrentUser
) -> QuizAvailabilityResponse:
    response.headers["Cache-Control"] = _NO_STORE
    return await service.get_availability(db, current_user=current_user, section_id=section_id)


@router.post(
    "/student/sections/{section_id}/quiz/start",
    response_model=QuizAttemptForStudent,
    operation_id="startStudentQuiz",
)
async def start_quiz(
    section_id: UUID, response: Response, db: DbSession, current_user: CurrentUser
) -> QuizAttemptForStudent:
    response.headers["Cache-Control"] = _NO_STORE
    return await service.start(db, current_user=current_user, section_id=section_id)


@router.get(
    "/student/quiz/attempts/{attempt_id}",
    response_model=QuizAttemptForStudent,
    operation_id="getStudentQuizAttempt",
)
async def get_quiz_attempt(
    attempt_id: UUID, response: Response, db: DbSession, current_user: CurrentUser
) -> QuizAttemptForStudent:
    response.headers["Cache-Control"] = _NO_STORE
    return await service.get_attempt(db, current_user=current_user, attempt_id=attempt_id)


@router.post(
    "/student/quiz/attempts/{attempt_id}/answer",
    response_model=AnswerFeedback,
    operation_id="answerStudentQuizQuestion",
)
async def answer_quiz_question(
    attempt_id: UUID,
    payload: AnswerSubmission,
    response: Response,
    db: DbSession,
    current_user: CurrentUser,
) -> AnswerFeedback:
    response.headers["Cache-Control"] = _NO_STORE
    return await service.answer(
        db, current_user=current_user, attempt_id=attempt_id, payload=payload
    )


@router.post(
    "/student/quiz/attempts/{attempt_id}/complete",
    response_model=QuizAttemptResult,
    operation_id="completeStudentQuiz",
)
async def complete_quiz(
    attempt_id: UUID, response: Response, db: DbSession, current_user: CurrentUser
) -> QuizAttemptResult:
    response.headers["Cache-Control"] = _NO_STORE
    return await service.complete(db, current_user=current_user, attempt_id=attempt_id)


@router.get(
    "/student/sections/{section_id}/quiz/attempts",
    response_model=QuizAttemptsSummary,
    operation_id="getStudentQuizAttemptsSummary",
)
async def get_quiz_attempts_summary(
    section_id: UUID, response: Response, db: DbSession, current_user: CurrentUser
) -> QuizAttemptsSummary:
    response.headers["Cache-Control"] = _NO_STORE
    return await service.attempts_summary(db, current_user=current_user, section_id=section_id)
