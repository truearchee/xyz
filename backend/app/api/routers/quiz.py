"""Student-facing quiz HTTP surface (Stage 5c).

Section-scoped + attempt-scoped routes ONLY (no by-question route → IDOR closure). Every response carries
``Cache-Control: private, no-store`` (access-sensitive + user-specific: no cache may preserve a stale 200
after unpublish or membership removal). The role gate (403) and the visibility gate (pinned 404) fire in
the service before any resource work; non-student → 403 uniformly; hidden/not-owner → 404.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.quiz import service
from app.domains.quiz.schemas import (
    AnswerFeedback,
    AnswerSubmission,
    ExamPrepScopeSummary,
    MistakeBankItem,
    QuizAttemptForStudent,
    QuizAttemptResult,
    QuizAttemptsSummary,
    QuizAvailabilityResponse,
    RecapScopeRequest,
    ScopeAvailabilityResponse,
)
from app.platform.auth.context import CurrentUserContext
from app.platform.auth.dependencies import get_current_user
from app.platform.db.session import get_db_session
from app.platform.query.pagination import PaginatedResponse, PaginationMeta

router = APIRouter(tags=["quiz"])

DbSession = Annotated[AsyncSession, Depends(get_db_session)]
CurrentUser = Annotated[CurrentUserContext, Depends(get_current_user)]
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0)]

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
    "/student/quiz/attempts/{attempt_id}/retry",
    response_model=QuizAttemptForStudent,
    operation_id="retryStudentQuizAttempt",
)
async def retry_quiz_attempt(
    attempt_id: UUID, response: Response, db: DbSession, current_user: CurrentUser
) -> QuizAttemptForStudent:
    response.headers["Cache-Control"] = _NO_STORE
    return await service.retry_attempt(db, current_user=current_user, attempt_id=attempt_id)


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


# ── Stage 6b: recap + exam-prep (multi-section, pooled) ───────────────────────────────────────────
@router.post(
    "/student/modules/{module_id}/recap-quiz/availability",
    response_model=ScopeAvailabilityResponse,
    operation_id="getStudentRecapAvailability",
)
async def recap_availability(
    module_id: UUID,
    payload: RecapScopeRequest,
    response: Response,
    db: DbSession,
    current_user: CurrentUser,
) -> ScopeAvailabilityResponse:
    response.headers["Cache-Control"] = _NO_STORE
    return await service.recap_availability(
        db, current_user=current_user, module_id=module_id, payload=payload
    )


@router.post(
    "/student/modules/{module_id}/recap-quiz/start",
    response_model=QuizAttemptForStudent,
    operation_id="startStudentRecapQuiz",
)
async def start_recap_quiz(
    module_id: UUID,
    payload: RecapScopeRequest,
    response: Response,
    db: DbSession,
    current_user: CurrentUser,
) -> QuizAttemptForStudent:
    response.headers["Cache-Control"] = _NO_STORE
    return await service.start_recap(
        db, current_user=current_user, module_id=module_id, payload=payload
    )


@router.get(
    "/student/modules/{module_id}/exam-prep-scopes",
    response_model=list[ExamPrepScopeSummary],
    operation_id="listStudentExamPrepScopes",
)
async def list_exam_prep_scopes(
    module_id: UUID, response: Response, db: DbSession, current_user: CurrentUser
) -> list[ExamPrepScopeSummary]:
    response.headers["Cache-Control"] = _NO_STORE
    return await service.list_exam_prep_scopes(
        db, current_user=current_user, module_id=module_id
    )


@router.post(
    "/student/assessment-scopes/{scope_id}/exam-prep-quiz/start",
    response_model=QuizAttemptForStudent,
    operation_id="startStudentExamPrepQuiz",
)
async def start_exam_prep_quiz(
    scope_id: UUID, response: Response, db: DbSession, current_user: CurrentUser
) -> QuizAttemptForStudent:
    response.headers["Cache-Control"] = _NO_STORE
    return await service.start_exam_prep(db, current_user=current_user, scope_id=scope_id)


# ── Stage 6c: mistakes-bank ──────────────────────────────────────────────────────────────────────
@router.get(
    "/student/modules/{module_id}/mistakes-bank",
    response_model=PaginatedResponse[MistakeBankItem],
    operation_id="listStudentMistakesBank",
)
async def list_mistakes_bank(
    module_id: UUID,
    response: Response,
    db: DbSession,
    current_user: CurrentUser,
    limit: Limit = 50,
    offset: Offset = 0,
) -> PaginatedResponse[MistakeBankItem]:
    response.headers["Cache-Control"] = _NO_STORE
    items, total = await service.list_mistakes_bank(
        db, current_user=current_user, module_id=module_id, limit=limit, offset=offset
    )
    return PaginatedResponse(
        items=items,
        pagination=PaginationMeta(limit=limit, offset=offset, total=total),
    )


@router.post(
    "/student/modules/{module_id}/mistakes-bank/start",
    response_model=QuizAttemptForStudent,
    operation_id="startStudentMistakesBank",
)
async def start_mistakes_bank(
    module_id: UUID, response: Response, db: DbSession, current_user: CurrentUser
) -> QuizAttemptForStudent:
    response.headers["Cache-Control"] = _NO_STORE
    return await service.start_mistakes_bank(db, current_user=current_user, module_id=module_id)
