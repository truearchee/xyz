"""Glossary practice (Stage 7b flashcards + 7c multiple-choice) — HTTP service.

**No AI runs during practice** (rule 15): Multiple-Choice samples its 3 distractors from the student's
OTHER in-scope saved terms; correctness rides on option IDENTITY, never display position. Flashcards
drive a hardcoded-interval Leitner box. The practice session is the entity the
``glossary_practice_completed`` event keys off. Mirrors the quiz HTTP service (role gate → owner-scoped
404 → business state) and commits the request session.
"""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.glossary.policy import (
    ENTRY_NOT_FOUND,
    SESSION_NOT_FOUND,
    SUBJECT_NOT_FOUND,
    conflict,
    not_found,
    require_student,
)
from app.domains.glossary.schemas import (
    PracticeAnswerFeedback,
    PracticeAnswerRequest,
    PracticeAvailability,
    PracticeItem,
    PracticeOption,
    PracticeResult,
    PracticeSessionState,
    StartPracticeRequest,
)
from app.platform.auth.context import CurrentUserContext
from app.platform.db.models import (
    GlossaryEntry,
    GlossaryPracticeAnswer,
    GlossaryPracticeSession,
    GlossaryReviewState,
)
from app.platform.events import GLOSSARY_PRACTICE_COMPLETED, EventRecorder
from app.platform.query.modules import get_active_module_access
from uuid6 import uuid7

# Hardcoded Leitner intervals (days), indexed by box. No adaptive SRS this stage.
BOX_INTERVALS = [0, 1, 3, 7, 16, 35]
DECK_CAP = 20
MCQ_OPTIONS = 4
MCQ_MIN_TERMS = 4  # 1 correct + 3 distractors


def _now() -> datetime:
    return datetime.now(UTC)


async def _validate_scope(
    db: AsyncSession, *, current_user: CurrentUserContext, scope: str, subject_id: UUID | None
) -> UUID | None:
    """Returns the effective subject_id (course scope) or None (all scope). 404 if not enrolled."""
    if scope == "course":
        if subject_id is None:
            raise conflict("subject_required")
        if await get_active_module_access(db, current_user.user_id, subject_id) is None:
            raise not_found(SUBJECT_NOT_FOUND)
        return subject_id
    return None


async def _eligible_entries(
    db: AsyncSession, *, student_id: UUID, scope: str, subject_id: UUID | None
) -> list[GlossaryEntry]:
    conditions = [
        GlossaryEntry.student_id == student_id,
        GlossaryEntry.status == "active",
        GlossaryEntry.definition_status == "generated",
        GlossaryEntry.short_definition.isnot(None),
    ]
    if scope == "course":
        conditions.append(GlossaryEntry.subject_id == subject_id)
    return list((await db.execute(select(GlossaryEntry).where(*conditions))).scalars().all())


async def get_practice_availability(
    db: AsyncSession,
    *,
    current_user: CurrentUserContext,
    scope: str,
    subject_id: UUID | None,
    mode: str,
) -> PracticeAvailability:
    require_student(current_user.role)
    effective_subject = await _validate_scope(
        db, current_user=current_user, scope=scope, subject_id=subject_id
    )
    count = len(
        await _eligible_entries(
            db, student_id=current_user.user_id, scope=scope, subject_id=effective_subject
        )
    )
    if mode == "multiple_choice":
        available = count >= MCQ_MIN_TERMS
        reason = None if available else "insufficient_terms"
    else:
        available = count >= 1
        reason = None if available else "no_terms"
    return PracticeAvailability(mode=mode, available=available, reason_code=reason, term_count=count)


async def start_practice(
    db: AsyncSession, *, current_user: CurrentUserContext, payload: StartPracticeRequest
) -> PracticeSessionState:
    require_student(current_user.role)
    effective_subject = await _validate_scope(
        db, current_user=current_user, scope=payload.scope, subject_id=payload.subject_id
    )

    # Resume an existing active session for this mode (one active per mode).
    existing = (
        await db.execute(
            select(GlossaryPracticeSession).where(
                GlossaryPracticeSession.student_id == current_user.user_id,
                GlossaryPracticeSession.mode == payload.mode,
                GlossaryPracticeSession.status == "in_progress",
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return await _session_state(db, existing)

    eligible = await _eligible_entries(
        db, student_id=current_user.user_id, scope=payload.scope, subject_id=effective_subject
    )
    if payload.mode == "multiple_choice" and len(eligible) < MCQ_MIN_TERMS:
        raise conflict("insufficient_terms")
    if not eligible:
        raise conflict("no_terms")

    random.shuffle(eligible)
    deck = eligible[:DECK_CAP]

    session = GlossaryPracticeSession(
        student_id=current_user.user_id,
        scope=payload.scope,
        subject_id=effective_subject,
        mode=payload.mode,
        status="in_progress",
    )
    try:
        async with db.begin_nested():
            db.add(session)
            await db.flush()
    except IntegrityError:
        # Concurrent start won the one-active-per-mode index — resume the winner.
        winner = (
            await db.execute(
                select(GlossaryPracticeSession).where(
                    GlossaryPracticeSession.student_id == current_user.user_id,
                    GlossaryPracticeSession.mode == payload.mode,
                    GlossaryPracticeSession.status == "in_progress",
                )
            )
        ).scalar_one()
        return await _session_state(db, winner)

    for index, entry in enumerate(deck):
        row = GlossaryPracticeAnswer(
            practice_session_id=session.id,
            glossary_entry_id=entry.id,
            display_order=index,
        )
        if payload.mode == "multiple_choice":
            others = [e for e in eligible if e.id != entry.id]
            distractors = random.sample(others, k=min(MCQ_OPTIONS - 1, len(others)))
            row.correct_entry_id = entry.id
            row.distractor_entry_ids = [str(d.id) for d in distractors]
        db.add(row)

    await db.commit()
    return await _session_state(db, session)


async def get_practice_session(
    db: AsyncSession, *, current_user: CurrentUserContext, session_id: UUID
) -> PracticeSessionState:
    require_student(current_user.role)
    session = await _owned_session(db, student_id=current_user.user_id, session_id=session_id)
    return await _session_state(db, session)


async def answer_practice(
    db: AsyncSession,
    *,
    current_user: CurrentUserContext,
    session_id: UUID,
    payload: PracticeAnswerRequest,
) -> PracticeAnswerFeedback:
    require_student(current_user.role)
    session = await _owned_session(db, student_id=current_user.user_id, session_id=session_id)
    if session.status != "in_progress":
        raise conflict("not_in_progress")

    row = (
        await db.execute(
            select(GlossaryPracticeAnswer).where(
                GlossaryPracticeAnswer.practice_session_id == session_id,
                GlossaryPracticeAnswer.glossary_entry_id == payload.entry_id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise not_found(ENTRY_NOT_FOUND)  # not a card in this session
    prompt = await db.get(GlossaryEntry, row.glossary_entry_id)
    if prompt is None:  # pragma: no cover - FK guarantees it
        raise not_found(ENTRY_NOT_FOUND)

    if row.answered_at is not None:
        # Idempotent re-submit: return the original feedback; do not re-apply review state.
        return _feedback(prompt, row, mode=session.mode)

    now = _now()
    if session.mode == "flashcard":
        if payload.outcome not in ("known", "not_known"):
            raise conflict("outcome_required")
        row.outcome = payload.outcome
        row.is_correct = payload.outcome == "known"
    else:  # multiple_choice
        if payload.selected_entry_id is None:
            row.selected_entry_id = None
            row.is_correct = False
            row.outcome = "not_known"  # "Don't know?" → recorded not-known
        else:
            row.selected_entry_id = payload.selected_entry_id
            row.is_correct = payload.selected_entry_id == row.correct_entry_id
            row.outcome = "known" if row.is_correct else "not_known"
    row.answered_at = now

    await _apply_review(
        db, student_id=session.student_id, entry=prompt, known=row.outcome == "known", now=now
    )
    await db.commit()
    return _feedback(prompt, row, mode=session.mode)


async def complete_practice(
    db: AsyncSession, *, current_user: CurrentUserContext, session_id: UUID
) -> PracticeResult:
    require_student(current_user.role)
    session = (
        await db.execute(
            select(GlossaryPracticeSession)
            .where(
                GlossaryPracticeSession.id == session_id,
                GlossaryPracticeSession.student_id == current_user.user_id,
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if session is None:
        raise not_found(SESSION_NOT_FOUND)
    if session.status == "completed":
        return _result(session)  # idempotent — no new event

    rows = (
        await db.execute(
            select(GlossaryPracticeAnswer)
            .where(GlossaryPracticeAnswer.practice_session_id == session_id)
            .order_by(GlossaryPracticeAnswer.display_order.asc())
        )
    ).scalars().all()
    answered = [r for r in rows if r.answered_at is not None]
    total = len(answered)
    correct = sum(1 for r in answered if r.is_correct)
    not_known = sum(1 for r in answered if r.outcome == "not_known")

    now = _now()
    session.status = "completed"
    session.total_count = total
    session.correct_count = correct
    session.not_known_count = not_known
    session.completed_at = now
    session.updated_at = now

    # module_id for the event: the course (course scope) or the first card's subject (all scope —
    # student_activity_events.module_id is NOT NULL, so resolve a deterministic module).
    module_id = session.subject_id
    if module_id is None and rows:
        first = await db.get(GlossaryEntry, rows[0].glossary_entry_id)
        module_id = first.subject_id if first is not None else None
    if module_id is not None:
        await EventRecorder().record(
            db,
            student_id=session.student_id,
            module_id=module_id,
            event_type=GLOSSARY_PRACTICE_COMPLETED,
            source_id=session.id,
            metadata={
                "mode": session.mode,
                "scope": session.scope,
                "totalCount": total,
                "correctCount": correct,
                "notKnownCount": not_known,
            },
        )
    await db.commit()
    return _result(session)


# ── helpers ──
async def _owned_session(
    db: AsyncSession, *, student_id: UUID, session_id: UUID
) -> GlossaryPracticeSession:
    session = (
        await db.execute(
            select(GlossaryPracticeSession).where(
                GlossaryPracticeSession.id == session_id,
                GlossaryPracticeSession.student_id == student_id,
            )
        )
    ).scalar_one_or_none()
    if session is None:
        raise not_found(SESSION_NOT_FOUND)
    return session


async def _apply_review(
    db: AsyncSession, *, student_id: UUID, entry: GlossaryEntry, known: bool, now: datetime
) -> None:
    await db.execute(
        pg_insert(GlossaryReviewState)
        .values(
            id=uuid7(),
            glossary_entry_id=entry.id,
            student_id=student_id,
            subject_id=entry.subject_id,
        )
        .on_conflict_do_nothing(index_elements=["glossary_entry_id"])
    )
    state = (
        await db.execute(
            select(GlossaryReviewState).where(GlossaryReviewState.glossary_entry_id == entry.id)
        )
    ).scalar_one()
    if known:
        state.box = min(state.box + 1, len(BOX_INTERVALS) - 1)
        state.correct_streak += 1
    else:
        state.box = 0
        state.correct_streak = 0
    state.due_at = now + timedelta(days=BOX_INTERVALS[state.box])
    state.last_reviewed_at = now
    state.total_reviews += 1
    state.updated_at = now


def _feedback(
    prompt: GlossaryEntry, row: GlossaryPracticeAnswer, *, mode: str
) -> PracticeAnswerFeedback:
    return PracticeAnswerFeedback(
        entry_id=prompt.id,
        # Flashcards have no right/wrong (just known/not-known); MCQ reveals correctness.
        is_correct=row.is_correct if mode == "multiple_choice" else None,
        correct_entry_id=row.correct_entry_id if mode == "multiple_choice" else None,
        term=prompt.term,
        definition=prompt.short_definition,
        outcome=row.outcome,
    )


def _result(session: GlossaryPracticeSession) -> PracticeResult:
    return PracticeResult(
        session_id=session.id,
        status=session.status,
        total_count=session.total_count,
        correct_count=session.correct_count,
        not_known_count=session.not_known_count,
    )


async def _session_state(
    db: AsyncSession, session: GlossaryPracticeSession
) -> PracticeSessionState:
    rows = (
        await db.execute(
            select(GlossaryPracticeAnswer)
            .where(GlossaryPracticeAnswer.practice_session_id == session.id)
            .order_by(GlossaryPracticeAnswer.display_order.asc())
        )
    ).scalars().all()

    needed: set[UUID] = set()
    for r in rows:
        needed.add(r.glossary_entry_id)
        if r.correct_entry_id is not None:
            needed.add(r.correct_entry_id)
        for d in r.distractor_entry_ids or []:
            needed.add(UUID(d))
    entries = {
        e.id: e
        for e in (
            await db.execute(select(GlossaryEntry).where(GlossaryEntry.id.in_(needed)))
        ).scalars().all()
    } if needed else {}

    items: list[PracticeItem] = []
    for r in rows:
        prompt = entries.get(r.glossary_entry_id)
        if prompt is None:
            continue
        options = None
        if session.mode == "multiple_choice":
            option_ids = [r.correct_entry_id] + [UUID(d) for d in (r.distractor_entry_ids or [])]
            opts = [
                PracticeOption(entry_id=eid, term=entries[eid].term)
                for eid in option_ids
                if eid is not None and eid in entries
            ]
            # Stable per-card shuffle (same across reloads, position unpredictable) — identity, not slot.
            random.Random(f"{session.id}:{r.display_order}").shuffle(opts)
            options = opts
        items.append(
            PracticeItem(
                entry_id=prompt.id,
                display_order=r.display_order,
                term=prompt.term,
                definition=prompt.short_definition,
                language=prompt.language,
                options=options,
                answered=r.answered_at is not None,
                selected_entry_id=r.selected_entry_id,
                is_correct=r.is_correct,
                outcome=r.outcome,
            )
        )
    return PracticeSessionState(
        session_id=session.id,
        mode=session.mode,
        scope=session.scope,
        subject_id=session.subject_id,
        status=session.status,
        items=items,
        total_count=session.total_count,
        correct_count=session.correct_count,
        not_known_count=session.not_known_count,
    )
