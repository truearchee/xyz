"""Student quiz HTTP service (Stage 5c) — orchestration over the policy gate + scoped reads + 5a/5b.

Flow on every endpoint (spec §HTTP contract): student-only gate (403 before any lookup) → visibility
scoped read (zero rows ⇒ pinned 404 — owner + published + assigned + lecture/lab; the S7 seam) → the
endpoint's own business state (409). Reads use the request session; the mutating endpoints (answer,
complete) commit it once for atomicity. Start delegates to the 5b service (enqueue-after-commit) via a
factory built from the request engine.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domains.quiz.assembly_service import (
    PooledQuizUnavailableError,
    retry_failed_pooled_attempt,
    start_mistakes_bank_attempt,
    start_pooled_attempt,
)
from app.domains.quiz.generation_service import (
    QuizUnavailableError,
    SectionNotFoundError,
    start_post_class_pooled_attempt,
)
from app.domains.quiz.mistakes import upsert_pool_mistake
from app.domains.quiz.schemas import (
    AnswerFeedback,
    AnswerForStudent,
    AnswerSubmission,
    ExamPrepScopeSummary,
    MistakeBankItem,
    QuizAttemptForStudent,
    QuizAttemptResult,
    QuizAttemptsSummary,
    QuizAvailabilityResponse,
    QuizOptionForStudent,
    QuizQuestionForStudent,
    RecapScopeRequest,
    ScopeAvailabilityResponse,
)
from app.domains.quiz.scope_service import (
    EXAM_PREP_MODE,
    MISTAKES_BANK_MODE,
    RECAP_MODE,
    get_or_create_mistakes_bank_definition,
    get_or_create_pooled_definition,
    resolve_exam_prep_scope,
    resolve_recap_scope,
)
from app.platform.auth.context import CurrentUserContext
from app.platform.db.models import (
    AnswerOption,
    AssessmentScope,
    MistakeRecord,
    QuizAttempt,
    QuizQuestion,
    StudentAnswer,
)
from app.platform.events import COMPLETED_QUIZ, PERFECT_QUIZ_SCORE, EventRecorder
from app.platform.query.quiz_availability_read import get_quiz_availability
from app.platform.query.section_eligibility_read import student_is_active_member
from app.platform.query.quiz_read import (
    VisibleAttempt,
    get_attempt_questions_for_student,
    get_attempts_aggregate,
    get_mistake_bank_page,
    get_visible_attempt,
)
from app.platform.query.student_summary_read import get_visible_student_section

SECTION_NOT_FOUND = "SECTION_NOT_FOUND"
ATTEMPT_NOT_FOUND = "ATTEMPT_NOT_FOUND"
QUIZ_FORBIDDEN = "QUIZ_FORBIDDEN"


def _require_student(role: str) -> None:
    """Row R: only a student may use the quiz surface. 403 before any lookup (uniform on all endpoints)."""
    if role != "student":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=QUIZ_FORBIDDEN)


def _now() -> datetime:
    return datetime.now(UTC)


def _correct_option(options: list[AnswerOption]) -> AnswerOption | None:
    for opt in options:
        if opt.is_correct:
            return opt
    return None


def _event_scope_metadata(visible) -> dict:
    """Scope reference for the activity-event metadata. POSITIVELY carries scope so Stages 9/10/11 can
    attribute it — a single-section (post_class) attempt emits ``moduleSectionId``; a MULTI-SECTION
    (recap/exam_prep) attempt (``module_section_id`` is NULL) emits the in-scope ``moduleSectionIds`` (and
    ``assessmentScopeId`` when exam-prep) from the definition's ``source_scope``. Never ``str(None)``."""
    meta: dict = {
        "quizMode": visible.quiz_mode,
        "quizDefinitionId": str(visible.quiz_definition_id),
    }
    if visible.module_section_id is not None:
        meta["moduleSectionId"] = str(visible.module_section_id)
    else:
        scope = visible.source_scope or {}
        meta["moduleSectionIds"] = [str(s) for s in (scope.get("sectionIds") or [])]
        if scope.get("assessmentScopeId"):
            meta["assessmentScopeId"] = str(scope["assessmentScopeId"])
    return meta


# ── availability ─────────────────────────────────────────────────────────────────────────────────
async def get_availability(
    db: AsyncSession, *, current_user: CurrentUserContext, section_id: UUID
) -> QuizAvailabilityResponse:
    _require_student(current_user.role)
    view = await get_quiz_availability(db, student_id=current_user.user_id, section_id=section_id)
    if view is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=SECTION_NOT_FOUND)
    return QuizAvailabilityResponse(
        availability="available" if view.available else "unavailable",
        reason_code=view.reason_code,
    )


# ── start (= Start Over from a terminal attempt) ─────────────────────────────────────────────────
async def start(
    db: AsyncSession, *, current_user: CurrentUserContext, section_id: UUID
) -> QuizAttemptForStudent:
    _require_student(current_user.role)
    visible = await get_visible_student_section(
        db, student_id=current_user.user_id, section_id=section_id
    )
    if visible is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=SECTION_NOT_FOUND)

    factory = async_sessionmaker(db.bind, class_=AsyncSession, expire_on_commit=False)
    try:
        result = await start_post_class_pooled_attempt(
            factory, student_id=current_user.user_id, section_id=section_id, enqueue=True
        )
    except (QuizUnavailableError, PooledQuizUnavailableError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail={"code": "quiz_unavailable"}
        ) from None
    except SectionNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=SECTION_NOT_FOUND) from None
    return await get_attempt(db, current_user=current_user, attempt_id=result.attempt_id)


# ── attempt detail ───────────────────────────────────────────────────────────────────────────────
async def get_attempt(
    db: AsyncSession, *, current_user: CurrentUserContext, attempt_id: UUID
) -> QuizAttemptForStudent:
    _require_student(current_user.role)
    visible = await get_visible_attempt(db, student_id=current_user.user_id, attempt_id=attempt_id)
    if visible is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=ATTEMPT_NOT_FOUND)
    return await _build_attempt_detail(db, visible)


async def retry_attempt(
    db: AsyncSession, *, current_user: CurrentUserContext, attempt_id: UUID
) -> QuizAttemptForStudent:
    _require_student(current_user.role)
    visible = await get_visible_attempt(db, student_id=current_user.user_id, attempt_id=attempt_id)
    if visible is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=ATTEMPT_NOT_FOUND)
    if visible.status != "failed":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": "not_failed"})

    factory = _scope_factory(db)
    try:
        result = await retry_failed_pooled_attempt(
            factory, student_id=current_user.user_id, attempt_id=attempt_id
        )
    except PooledQuizUnavailableError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail={"code": "retry_unavailable"}
        ) from None
    return await get_attempt(db, current_user=current_user, attempt_id=result.attempt_id)


async def _build_attempt_detail(db: AsyncSession, visible: VisibleAttempt) -> QuizAttemptForStudent:
    rows = await get_attempt_questions_for_student(db, attempt_id=visible.attempt_id)
    questions: list[QuizQuestionForStudent] = []
    for qr in rows:
        answer = None
        if qr.answer is not None:
            correct = _correct_option(qr.options)
            answer = AnswerForStudent(
                selected_answer_option_id=qr.answer.selected_answer_option_id,
                is_correct=qr.answer.is_correct,
                correct_answer_option_id=correct.id if correct is not None else qr.answer.selected_answer_option_id,
                explanation=qr.question.explanation,
            )
        questions.append(
            QuizQuestionForStudent(
                id=qr.question.id,
                question_text=qr.question.question_text,
                display_order=qr.question.display_order,
                question_type=qr.question.question_type,
                options=[
                    QuizOptionForStudent(id=o.id, text=o.text, display_order=o.display_order)
                    for o in qr.options
                ],
                answer=answer,
            )
        )
    return QuizAttemptForStudent(
        id=visible.attempt_id,
        quiz_definition_id=visible.quiz_definition_id,
        status=visible.status,
        attempt_number=visible.attempt_number,
        total_questions=visible.total_questions,
        new_question_count=visible.new_question_count,
        mistake_review_question_count=visible.mistake_review_question_count,
        questions=questions,
    )


# ── answer (the load-bearing ordering) ───────────────────────────────────────────────────────────
async def answer(
    db: AsyncSession,
    *,
    current_user: CurrentUserContext,
    attempt_id: UUID,
    payload: AnswerSubmission,
) -> AnswerFeedback:
    _require_student(current_user.role)
    # 1. visibility
    visible = await get_visible_attempt(db, student_id=current_user.user_id, attempt_id=attempt_id)
    if visible is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=ATTEMPT_NOT_FOUND)
    # 2. status
    if visible.status != "in_progress":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": "not_in_progress"})
    # 3. three-way integrity — question belongs to the attempt
    question = await db.get(QuizQuestion, payload.question_id)
    if question is None or question.quiz_attempt_id != attempt_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=ATTEMPT_NOT_FOUND)
    options = (
        await db.execute(
            select(AnswerOption)
            .where(AnswerOption.quiz_question_id == question.id)
            .order_by(AnswerOption.display_order.asc())
        )
    ).scalars().all()
    selected = next((o for o in options if o.id == payload.selected_answer_option_id), None)
    if selected is None:
        # the option exists for a different question (or not at all) → 422
        raise HTTPException(status_code=422, detail="OPTION_NOT_IN_QUESTION")
    correct = _correct_option(options)
    correct_id = correct.id if correct is not None else selected.id
    is_correct = bool(selected.is_correct)

    # 4. insert StudentAnswer; UNIQUE(attempt,question) is the idempotency backstop.
    try:
        async with db.begin_nested():
            db.add(
                StudentAnswer(
                    quiz_attempt_id=attempt_id,
                    quiz_question_id=question.id,
                    selected_answer_option_id=selected.id,
                    is_correct=is_correct,
                )
            )
    except IntegrityError:
        # Double-tap / two-tab: return the ORIGINAL feedback; the re-submitted option is irrelevant.
        original = (
            await db.execute(
                select(StudentAnswer).where(
                    StudentAnswer.quiz_attempt_id == attempt_id,
                    StudentAnswer.quiz_question_id == question.id,
                )
            )
        ).scalar_one()
        mistake_exists = (
            await db.scalar(
                select(func.count())
                .select_from(MistakeRecord)
                .where(
                    MistakeRecord.source_quiz_attempt_id == attempt_id,
                    MistakeRecord.source_question_id == question.id,
                )
            )
        ) or 0
        return AnswerFeedback(
            question_id=question.id,
            selected_answer_option_id=original.selected_answer_option_id,
            is_correct=original.is_correct,
            correct_answer_option_id=correct_id,
            explanation=question.explanation,
            already_answered=True,
            mistake_saved=bool(mistake_exists),
        )

    await _apply_retake_prefix_progress(
        db,
        current_user=current_user,
        visible=visible,
        question=question,
        is_correct=is_correct,
    )

    # 5/6. on incorrect NEW questions → MistakeRecord (idempotent snapshot of DISPLAY-TIME state). A
    # mistake_review question already IS a bank/prefix mistake, so a wrong practice answer must not create a
    # duplicate MistakeRecord.
    mistake_saved = False
    if not is_correct and question.source_type != "mistake_review":
        mistake_saved = True
        snapshot_options = [
            {
                "id": str(o.id),
                "text": o.text,
                "displayOrder": o.display_order,
                "isCorrect": o.is_correct,
            }
            for o in options
        ]
        question_snapshot = {
            "questionText": question.question_text,
            "displayOrder": question.display_order,
            "explanation": question.explanation,
        }
        answer_options_snapshot = {"options": snapshot_options}
        # Stage 6b: a pooled question's mistake lives at its SOURCE section (a multi-section attempt has a
        # NULL definition section); a post_class question's source_section_id equals its single section.
        mistake_section_id = question.source_section_id or visible.module_section_id
        correct_answer = correct.text if correct is not None else ""
        if question.source_pool_question_id is not None and mistake_section_id is not None:
            # Pooled question → durable upsert identity (6a): re-missing the same pool question in the same
            # QuizDefinition across attempts updates ONE record (the answer insert above already fenced the
            # double-submit, so the (attempt, question) pair here is always new — only the pool key conflicts).
            await upsert_pool_mistake(
                db,
                student_id=current_user.user_id,
                module_id=visible.module_id,
                module_section_id=mistake_section_id,
                source_quiz_definition_id=visible.quiz_definition_id,
                source_quiz_attempt_id=attempt_id,
                source_question_id=question.id,
                source_pool_question_id=question.source_pool_question_id,
                question_snapshot=question_snapshot,
                answer_options_snapshot=answer_options_snapshot,
                selected_wrong_answer=selected.text,
                correct_answer=correct_answer,
                explanation=question.explanation,
            )
        else:
            # Pre-pool (post_class / mistake_review) → Stage 5 identity on (attempt, question).
            try:
                async with db.begin_nested():
                    db.add(
                        MistakeRecord(
                            student_id=current_user.user_id,
                            module_id=visible.module_id,
                            module_section_id=mistake_section_id,
                            source_quiz_definition_id=visible.quiz_definition_id,
                            source_quiz_attempt_id=attempt_id,
                            source_question_id=question.id,
                            question_snapshot=question_snapshot,
                            answer_options_snapshot=answer_options_snapshot,
                            selected_wrong_answer=selected.text,
                            correct_answer=correct_answer,
                            explanation=question.explanation,
                        )
                    )
            except IntegrityError:
                pass  # already recorded for this (attempt, question) — idempotent

    await db.commit()
    # 7. feedback (no score, no event)
    return AnswerFeedback(
        question_id=question.id,
        selected_answer_option_id=selected.id,
        is_correct=is_correct,
        correct_answer_option_id=correct_id,
        explanation=question.explanation,
        already_answered=False,
        mistake_saved=mistake_saved,
    )


async def _apply_retake_prefix_progress(
    db: AsyncSession,
    *,
    current_user: CurrentUserContext,
    visible: VisibleAttempt,
    question: QuizQuestion,
    is_correct: bool,
) -> None:
    """D2 default: only correct answers to source-quiz retake prefix questions advance the counter.

    Bank practice is pure practice (no progress), and this is called only after the first successful answer
    insert, so duplicate submits cannot double-count.
    """
    if (
        not is_correct
        or visible.quiz_mode == MISTAKES_BANK_MODE
        or question.source_type != "mistake_review"
        or question.source_mistake_record_id is None
    ):
        return
    mistake = (
        await db.execute(
            select(MistakeRecord)
            .where(
                MistakeRecord.id == question.source_mistake_record_id,
                MistakeRecord.student_id == current_user.user_id,
                MistakeRecord.source_quiz_definition_id == visible.quiz_definition_id,
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if mistake is None:
        return
    mistake.retake_correct_count += 1
    mistake.show_in_retake_prefix = mistake.retake_correct_count < 2
    mistake.updated_at = _now()


# ── complete (the atomic unit) ───────────────────────────────────────────────────────────────────
async def complete(
    db: AsyncSession, *, current_user: CurrentUserContext, attempt_id: UUID
) -> QuizAttemptResult:
    _require_student(current_user.role)
    # Visibility BEFORE the lock — never lock a row we are about to 404 (and no event fires while hidden).
    visible = await get_visible_attempt(db, student_id=current_user.user_id, attempt_id=attempt_id)
    if visible is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=ATTEMPT_NOT_FOUND)

    attempt = (
        await db.execute(
            select(QuizAttempt).where(QuizAttempt.id == attempt_id).with_for_update()
        )
    ).scalar_one()

    if attempt.status == "completed":
        return _result_dto(attempt)  # idempotent re-complete — no new event
    # Strict: only an in_progress attempt may complete (a generating-with-questions edge → 409).
    if attempt.status != "in_progress":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": "not_in_progress"})

    total = attempt.total_questions or (
        await db.scalar(
            select(func.count()).select_from(QuizQuestion).where(
                QuizQuestion.quiz_attempt_id == attempt_id
            )
        )
    )
    answered = await db.scalar(
        select(func.count()).select_from(StudentAnswer).where(
            StudentAnswer.quiz_attempt_id == attempt_id
        )
    )
    if total == 0 or answered < total:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": "incomplete"})

    correct = await db.scalar(
        select(func.count()).select_from(StudentAnswer).where(
            StudentAnswer.quiz_attempt_id == attempt_id,
            StudentAnswer.is_correct.is_(True),
        )
    )
    correct = int(correct or 0)
    score = (Decimal(correct) / Decimal(total) * Decimal(100)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    now = _now()
    attempt.status = "completed"
    attempt.total_questions = total
    attempt.correct_count = correct
    attempt.incorrect_count = total - correct
    attempt.score_percentage = score
    attempt.completed_at = now
    attempt.updated_at = now

    scope_meta = _event_scope_metadata(visible)
    recorder = EventRecorder()
    await recorder.record(
        db,
        student_id=current_user.user_id,
        module_id=visible.module_id,
        event_type=COMPLETED_QUIZ,
        source_id=attempt.id,
        metadata={
            **scope_meta,
            "attemptNumber": attempt.attempt_number,
            "correctCount": correct,
            "totalQuestions": total,
            "scorePercentage": float(score),
        },
    )
    # Perfect score from COUNTS (never float equality). No student-visible celebration until Stage 10.
    if correct == total:
        await recorder.record(
            db,
            student_id=current_user.user_id,
            module_id=visible.module_id,
            event_type=PERFECT_QUIZ_SCORE,
            source_id=attempt.id,
            metadata={
                **scope_meta,
                "attemptNumber": attempt.attempt_number,
            },
        )
    await db.commit()
    await db.refresh(attempt)
    return _result_dto(attempt)


def _result_dto(attempt: QuizAttempt) -> QuizAttemptResult:
    return QuizAttemptResult(
        id=attempt.id,
        status=attempt.status,
        score_percentage=attempt.score_percentage,
        correct_count=attempt.correct_count,
        incorrect_count=attempt.incorrect_count,
        total_questions=attempt.total_questions,
        completed_at=attempt.completed_at,
    )


# ── attempts aggregate ───────────────────────────────────────────────────────────────────────────
async def attempts_summary(
    db: AsyncSession, *, current_user: CurrentUserContext, section_id: UUID
) -> QuizAttemptsSummary:
    _require_student(current_user.role)
    visible = await get_visible_student_section(
        db, student_id=current_user.user_id, section_id=section_id
    )
    if visible is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=SECTION_NOT_FOUND)
    agg = await get_attempts_aggregate(db, student_id=current_user.user_id, section_id=section_id)
    return QuizAttemptsSummary(
        attempt_count=agg.attempt_count, best_score_percentage=agg.best_score_percentage
    )


# ── recap + exam-prep (Stage 6b) ──────────────────────────────────────────────────────────────────
MODULE_NOT_FOUND = "MODULE_NOT_FOUND"
SCOPE_NOT_FOUND = "ASSESSMENT_SCOPE_NOT_FOUND"


def _scope_factory(db: AsyncSession) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(db.bind, class_=AsyncSession, expire_on_commit=False)


async def recap_availability(
    db: AsyncSession,
    *,
    current_user: CurrentUserContext,
    module_id: UUID,
    payload: RecapScopeRequest,
) -> ScopeAvailabilityResponse:
    _require_student(current_user.role)
    if not await student_is_active_member(
        db, student_id=current_user.user_id, module_id=module_id
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=MODULE_NOT_FOUND)
    resolution = await resolve_recap_scope(
        db,
        module_id=module_id,
        student_id=current_user.user_id,
        weeks=payload.weeks,
        start_date=payload.start_date,
        end_date=payload.end_date,
    )
    return ScopeAvailabilityResponse(
        available=resolution.available,
        reason_code=resolution.reason_code,
        ready_section_count=len(resolution.ready_section_ids),
        processing_section_count=len(resolution.processing_section_ids),
    )


async def start_recap(
    db: AsyncSession,
    *,
    current_user: CurrentUserContext,
    module_id: UUID,
    payload: RecapScopeRequest,
) -> QuizAttemptForStudent:
    _require_student(current_user.role)
    if not await student_is_active_member(
        db, student_id=current_user.user_id, module_id=module_id
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=MODULE_NOT_FOUND)
    resolution = await resolve_recap_scope(
        db,
        module_id=module_id,
        student_id=current_user.user_id,
        weeks=payload.weeks,
        start_date=payload.start_date,
        end_date=payload.end_date,
    )
    if not resolution.available:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": resolution.reason_code or "recap_unavailable"},
        )
    factory = _scope_factory(db)
    definition_id = await get_or_create_pooled_definition(
        factory,
        module_id=module_id,
        quiz_mode=RECAP_MODE,
        scope_key=resolution.scope_key,
        section_ids=resolution.ready_section_ids,
    )
    start = await start_pooled_attempt(
        factory, student_id=current_user.user_id, quiz_definition_id=definition_id
    )
    return await get_attempt(db, current_user=current_user, attempt_id=start.attempt_id)


async def list_exam_prep_scopes(
    db: AsyncSession, *, current_user: CurrentUserContext, module_id: UUID
) -> list[ExamPrepScopeSummary]:
    _require_student(current_user.role)
    if not await student_is_active_member(
        db, student_id=current_user.user_id, module_id=module_id
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=MODULE_NOT_FOUND)
    scopes = (
        await db.scalars(
            select(AssessmentScope)
            .where(AssessmentScope.module_id == module_id)
            .order_by(AssessmentScope.created_at.desc(), AssessmentScope.id.desc())
        )
    ).all()
    summaries: list[ExamPrepScopeSummary] = []
    for scope in scopes:
        resolution = await resolve_exam_prep_scope(
            db, scope=scope, student_id=current_user.user_id
        )
        summaries.append(
            ExamPrepScopeSummary(
                id=scope.id,
                name=scope.name,
                covered_weeks=[int(w) for w in (scope.covered_weeks or [])],
                available=resolution.available,
                reason_code=resolution.reason_code,
            )
        )
    return summaries


async def start_exam_prep(
    db: AsyncSession, *, current_user: CurrentUserContext, scope_id: UUID
) -> QuizAttemptForStudent:
    _require_student(current_user.role)
    scope = await db.get(AssessmentScope, scope_id)
    # A scope the student is not assigned to (or that does not exist) is a pinned 404 — never reveal it.
    if scope is None or not await student_is_active_member(
        db, student_id=current_user.user_id, module_id=scope.module_id
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=SCOPE_NOT_FOUND)
    resolution = await resolve_exam_prep_scope(db, scope=scope, student_id=current_user.user_id)
    if not resolution.available:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": resolution.reason_code or "exam_prep_unavailable"},
        )
    factory = _scope_factory(db)
    definition_id = await get_or_create_pooled_definition(
        factory,
        module_id=scope.module_id,
        quiz_mode=EXAM_PREP_MODE,
        scope_key=resolution.scope_key,
        section_ids=resolution.ready_section_ids,
        assessment_scope_id=scope.id,
    )
    start = await start_pooled_attempt(
        factory, student_id=current_user.user_id, quiz_definition_id=definition_id
    )
    return await get_attempt(db, current_user=current_user, attempt_id=start.attempt_id)


# ── mistakes-bank (Stage 6c) ─────────────────────────────────────────────────────────────────────
async def list_mistakes_bank(
    db: AsyncSession,
    *,
    current_user: CurrentUserContext,
    module_id: UUID,
    limit: int,
    offset: int,
) -> tuple[list[MistakeBankItem], int]:
    _require_student(current_user.role)
    items, total = await get_mistake_bank_page(
        db,
        student_id=current_user.user_id,
        module_id=module_id,
        limit=limit,
        offset=offset,
    )
    if total < 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=MODULE_NOT_FOUND)
    return ([MistakeBankItem.model_validate(item) for item in items], total)


async def start_mistakes_bank(
    db: AsyncSession,
    *,
    current_user: CurrentUserContext,
    module_id: UUID,
) -> QuizAttemptForStudent:
    _require_student(current_user.role)
    if not await student_is_active_member(
        db, student_id=current_user.user_id, module_id=module_id
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=MODULE_NOT_FOUND)
    factory = _scope_factory(db)
    definition_id = await get_or_create_mistakes_bank_definition(factory, module_id=module_id)
    try:
        start = await start_mistakes_bank_attempt(
            factory,
            student_id=current_user.user_id,
            module_id=module_id,
            quiz_definition_id=definition_id,
        )
    except PooledQuizUnavailableError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": "no_mistakes"}) from None
    return await get_attempt(db, current_user=current_user, attempt_id=start.attempt_id)
