"""Stage 7b/7c — glossary practice: flashcard Leitner, MCQ deck-sampling, session lifecycle, events.

No AI runs during practice (deterministic). Calls the practice service directly on the request session.
"""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from fastapi import HTTPException
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.glossary import practice_service
from app.domains.glossary.schemas import PracticeAnswerRequest, StartPracticeRequest
from app.platform.auth.context import CurrentUserContext
from app.platform.db.models import (
    AppUser,
    CourseMembership,
    CourseModule,
    GlossaryEntry,
    GlossaryPracticeSession,
    GlossaryReviewState,
    StudentActivityEvent,
)

pytestmark = pytest.mark.anyio


def _ctx(user: AppUser) -> CurrentUserContext:
    return CurrentUserContext(
        user_id=user.id,
        auth_provider_id=user.auth_provider_id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        is_active=True,
        timezone="UTC",
        preferred_language="en",
    )


async def _student(db: AsyncSession) -> AppUser:
    s = AppUser(
        auth_provider_id=f"auth-{uuid4()}",
        email=f"student-{uuid4()}@example.com",
        full_name="Practice Student",
        role="student",
        timezone="UTC",
    )
    db.add(s)
    await db.flush()
    return s


async def _seed(db: AsyncSession, *, terms: int, students: int = 1) -> SimpleNamespace:
    owner = AppUser(
        auth_provider_id=f"auth-{uuid4()}",
        email=f"owner-{uuid4()}@example.com",
        full_name="Owner",
        role="lecturer",
        timezone="UTC",
    )
    db.add(owner)
    await db.flush()
    module = CourseModule(title="Bio", owner_id=owner.id, timezone="UTC", is_active=True)
    db.add(module)
    await db.flush()
    student_users = []
    for _ in range(students):
        s = await _student(db)
        db.add(CourseMembership(user_id=s.id, module_id=module.id, role="student", status="active"))
        student_users.append(s)
    await db.flush()
    # Generated entries belong to the FIRST student.
    for i in range(terms):
        db.add(
            GlossaryEntry(
                student_id=student_users[0].id,
                subject_id=module.id,
                term=f"Term{i}",
                normalized_term=f"term{i}",
                normalize_version="v1",
                entry_type="term",
                language="en",
                cache_key=f"ck-{uuid4()}",
                short_definition=f"Definition of Term{i}.",
                definition_status="generated",
                status="active",
            )
        )
    await db.commit()
    return SimpleNamespace(owner=owner, module=module, students=student_users)


# ── flashcards (7b) ──
async def test_flashcard_known_advances_box_not_known_resets(db_session: AsyncSession):
    seed = await _seed(db_session, terms=3)
    ctx = _ctx(seed.students[0])
    state = await practice_service.start_practice(
        db_session,
        current_user=ctx,
        payload=StartPracticeRequest(scope="course", subject_id=seed.module.id, mode="flashcard"),
    )
    assert state.mode == "flashcard"
    assert len(state.items) == 3
    assert all(item.options is None for item in state.items)  # flashcards have no MCQ options

    first, second = state.items[0], state.items[1]
    await practice_service.answer_practice(
        db_session,
        current_user=ctx,
        session_id=state.session_id,
        payload=PracticeAnswerRequest(entry_id=first.entry_id, outcome="known"),
    )
    await practice_service.answer_practice(
        db_session,
        current_user=ctx,
        session_id=state.session_id,
        payload=PracticeAnswerRequest(entry_id=second.entry_id, outcome="not_known"),
    )

    known_state = (
        await db_session.execute(
            select(GlossaryReviewState).where(
                GlossaryReviewState.glossary_entry_id == first.entry_id
            )
        )
    ).scalar_one()
    assert known_state.box == 1 and known_state.correct_streak == 1
    notknown_state = (
        await db_session.execute(
            select(GlossaryReviewState).where(
                GlossaryReviewState.glossary_entry_id == second.entry_id
            )
        )
    ).scalar_one()
    assert notknown_state.box == 0 and notknown_state.correct_streak == 0

    result = await practice_service.complete_practice(
        db_session, current_user=ctx, session_id=state.session_id
    )
    assert result.status == "completed"
    assert result.total_count == 2 and result.not_known_count == 1

    events = (
        await db_session.execute(
            select(StudentActivityEvent).where(
                StudentActivityEvent.source_id == state.session_id
            )
        )
    ).scalars().all()
    assert [e.event_type for e in events] == ["glossary_practice_completed"]
    assert events[0].module_id == seed.module.id


# ── multiple-choice (7c) ──
async def test_mcq_unavailable_below_four_terms(db_session: AsyncSession):
    seed = await _seed(db_session, terms=3)
    ctx = _ctx(seed.students[0])
    avail = await practice_service.get_practice_availability(
        db_session, current_user=ctx, scope="course", subject_id=seed.module.id, mode="multiple_choice"
    )
    assert avail.available is False and avail.reason_code == "insufficient_terms"
    with pytest.raises(HTTPException) as exc:
        await practice_service.start_practice(
            db_session,
            current_user=ctx,
            payload=StartPracticeRequest(
                scope="course", subject_id=seed.module.id, mode="multiple_choice"
            ),
        )
    assert exc.value.status_code == 409


async def test_mcq_correct_wrong_and_dont_know(db_session: AsyncSession):
    seed = await _seed(db_session, terms=5)
    ctx = _ctx(seed.students[0])
    state = await practice_service.start_practice(
        db_session,
        current_user=ctx,
        payload=StartPracticeRequest(
            scope="course", subject_id=seed.module.id, mode="multiple_choice"
        ),
    )
    assert len(state.items) == 5
    for item in state.items:
        assert item.options is not None and len(item.options) == 4
        # the correct option's identity is the prompt entry id
        assert any(o.entry_id == item.entry_id for o in item.options)

    # Correct pick.
    correct = await practice_service.answer_practice(
        db_session,
        current_user=ctx,
        session_id=state.session_id,
        payload=PracticeAnswerRequest(
            entry_id=state.items[0].entry_id, selected_entry_id=state.items[0].entry_id
        ),
    )
    assert correct.is_correct is True and correct.correct_entry_id == state.items[0].entry_id

    # Wrong pick (a distractor option).
    distractor = next(
        o for o in state.items[1].options if o.entry_id != state.items[1].entry_id
    )
    wrong = await practice_service.answer_practice(
        db_session,
        current_user=ctx,
        session_id=state.session_id,
        payload=PracticeAnswerRequest(
            entry_id=state.items[1].entry_id, selected_entry_id=distractor.entry_id
        ),
    )
    assert wrong.is_correct is False

    # "Don't know?" → recorded not-known.
    dont_know = await practice_service.answer_practice(
        db_session,
        current_user=ctx,
        session_id=state.session_id,
        payload=PracticeAnswerRequest(entry_id=state.items[2].entry_id, selected_entry_id=None),
    )
    assert dont_know.is_correct is False and dont_know.outcome == "not_known"

    result = await practice_service.complete_practice(
        db_session, current_user=ctx, session_id=state.session_id
    )
    assert result.total_count == 3 and result.correct_count == 1 and result.not_known_count == 2


async def test_practice_resume_returns_same_session(db_session: AsyncSession):
    seed = await _seed(db_session, terms=2)
    ctx = _ctx(seed.students[0])
    a = await practice_service.start_practice(
        db_session,
        current_user=ctx,
        payload=StartPracticeRequest(scope="course", subject_id=seed.module.id, mode="flashcard"),
    )
    b = await practice_service.start_practice(
        db_session,
        current_user=ctx,
        payload=StartPracticeRequest(scope="course", subject_id=seed.module.id, mode="flashcard"),
    )
    assert a.session_id == b.session_id
    sessions = await db_session.scalar(
        select(func.count()).select_from(GlossaryPracticeSession)
    )
    assert sessions == 1


async def test_complete_is_idempotent_single_event(db_session: AsyncSession):
    seed = await _seed(db_session, terms=2)
    ctx = _ctx(seed.students[0])
    state = await practice_service.start_practice(
        db_session,
        current_user=ctx,
        payload=StartPracticeRequest(scope="course", subject_id=seed.module.id, mode="flashcard"),
    )
    await practice_service.answer_practice(
        db_session,
        current_user=ctx,
        session_id=state.session_id,
        payload=PracticeAnswerRequest(entry_id=state.items[0].entry_id, outcome="known"),
    )
    await practice_service.complete_practice(db_session, current_user=ctx, session_id=state.session_id)
    await practice_service.complete_practice(db_session, current_user=ctx, session_id=state.session_id)
    events = await db_session.scalar(
        select(func.count())
        .select_from(StudentActivityEvent)
        .where(StudentActivityEvent.source_id == state.session_id)
    )
    assert events == 1


async def test_practice_session_personal_scoping_404(db_session: AsyncSession):
    seed = await _seed(db_session, terms=4, students=2)
    owner_ctx = _ctx(seed.students[0])
    state = await practice_service.start_practice(
        db_session,
        current_user=owner_ctx,
        payload=StartPracticeRequest(scope="course", subject_id=seed.module.id, mode="flashcard"),
    )
    with pytest.raises(HTTPException) as exc:
        await practice_service.get_practice_session(
            db_session, current_user=_ctx(seed.students[1]), session_id=state.session_id
        )
    assert exc.value.status_code == 404
