"""DB-level gamification tests (Stage 10b/10c): query primitives, on-read badge evaluation
(idempotent + sticky + anti-farm), topic/module rules, and reconcile == stored."""

from __future__ import annotations

import asyncio
from collections import Counter
from datetime import UTC, date, datetime, time, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.domains.gamification.service import compute_expected_badges, get_gamification
from app.platform.db.models import (
    AppUser,
    CourseMembership,
    CourseModule,
    ModuleSection,
    QuizDefinition,
    StudentActivityEvent,
    StudentBadge,
    StudentTopicMasterySnapshot,
)
from app.platform.events import COMPLETED_QUIZ, PERFECT_QUIZ_SCORE, STUDIED_SECTION
from app.platform.query import gamification_read

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 6, 17, 12, 0, tzinfo=UTC)  # local date (UTC) = 2026-06-17
TODAY = date(2026, 6, 17)


def _day(offset: int) -> date:
    return TODAY + timedelta(days=offset)


def _at(offset: int, hour: int = 12) -> datetime:
    return datetime.combine(_day(offset), time(hour, 0), tzinfo=UTC)


async def _user(db, email: str, role: str = "student") -> AppUser:
    user = AppUser(
        auth_provider_id=email,
        email=email,
        full_name="Test User",
        role=role,
        is_active=True,
        timezone="UTC",
    )
    db.add(user)
    await db.flush()
    return user


async def _module(db, owner_id, title: str) -> CourseModule:
    module = CourseModule(
        title=title,
        description="test",
        owner_id=owner_id,
        timezone="UTC",
        starts_on=date(2026, 6, 1),
        ends_on=date(2026, 8, 1),
        is_active=True,
    )
    db.add(module)
    await db.flush()
    return module


async def _enroll(db, user_id, module_id, role: str = "student") -> None:
    db.add(CourseMembership(user_id=user_id, module_id=module_id, role=role, status="active"))
    await db.flush()


async def _section(
    db, module_id, *, session_date, order_index=1, type_="lecture", publish_status="published"
) -> ModuleSection:
    section = ModuleSection(
        course_module_id=module_id,
        title="Section",
        type=type_,
        order_index=order_index,
        week_number=1,
        session_date=session_date,
        publish_status=publish_status,
        status="active",
    )
    db.add(section)
    await db.flush()
    return section


def _event(student_id, module_id, event_type, *, occurred_at, metadata=None) -> StudentActivityEvent:
    return StudentActivityEvent(
        student_id=student_id,
        module_id=module_id,
        event_type=event_type,
        source_id=uuid4(),
        occurred_at=occurred_at,
        metadata_json=metadata,
    )


def _completed_quiz(student_id, module_id, *, occurred_at, quiz_def_id, section_id=None, mode="post_class"):
    meta = {"quizMode": mode, "quizDefinitionId": str(quiz_def_id)}
    if section_id is not None:
        meta["moduleSectionId"] = str(section_id)
    return _event(student_id, module_id, COMPLETED_QUIZ, occurred_at=occurred_at, metadata=meta)


def _earned_keys(result) -> set[str]:
    return {badge.badge_key for badge in result.earned_badges}


def _earned_scoped(result) -> set[tuple[str, str, str]]:
    return {(b.badge_key, b.scope_type, str(b.scope_id)) for b in result.earned_badges}


async def _student_in_module(db, email: str):
    owner = await _user(db, "owner@example.test", role="lecturer")
    student = await _user(db, email, role="student")
    module = await _module(db, owner.id, "Module")
    await _enroll(db, student.id, module.id)
    return student, module


# ── Query primitives ─────────────────────────────────────────────────────────


async def test_scheduled_days_collapse_same_date_and_union_modules(db_session):
    owner = await _user(db_session, "o@example.test", role="lecturer")
    student = await _user(db_session, "s@example.test")
    m1 = await _module(db_session, owner.id, "M1")
    m2 = await _module(db_session, owner.id, "M2")
    await _enroll(db_session, student.id, m1.id)
    await _enroll(db_session, student.id, m2.id)
    # Two sections on the SAME date in m1 (collapse to one day) + one in m2 (union).
    await _section(db_session, m1.id, session_date=_day(-1), order_index=1)
    await _section(db_session, m1.id, session_date=_day(-1), order_index=2, type_="lab")
    await _section(db_session, m2.id, session_date=_day(0), order_index=1)
    await db_session.commit()

    scheduled = await gamification_read.scheduled_class_days(
        db_session, student_id=student.id, start_date=_day(-5), end_date=_day(0)
    )
    assert scheduled == {_day(-1), _day(0)}


async def test_engagement_days_use_occurred_at_and_tz_boundary(db_session):
    student, module = await _student_in_module(db_session, "s@example.test")
    # 23:30 on day -1 in America/New_York is 03:30 UTC on day 0 — the LOCAL date must be day -1.
    ny = ZoneInfo("America/New_York")
    occurred = datetime(2026, 6, 16, 23, 30, tzinfo=ny)
    db_session.add(_completed_quiz(student.id, module.id, occurred_at=occurred, quiz_def_id=uuid4()))
    await db_session.commit()

    ny_days = await gamification_read.engagement_days(
        db_session, student_id=student.id, start_date=_day(-3), end_date=_day(0), tz=ny
    )
    utc_days = await gamification_read.engagement_days(
        db_session, student_id=student.id, start_date=_day(-3), end_date=_day(0), tz=ZoneInfo("UTC")
    )
    assert ny_days == {date(2026, 6, 16)}  # local (NY) date
    assert utc_days == {date(2026, 6, 17)}  # same instant, UTC date is the next day


# ── On-read streak + badge awarding ──────────────────────────────────────────


async def test_active_streak_awards_and_reload_is_idempotent(db_session):
    student, module = await _student_in_module(db_session, "s@example.test")
    for off in (-2, -1, 0):
        await _section(db_session, module.id, session_date=_day(off), order_index=off + 3)
        db_session.add(
            _completed_quiz(student.id, module.id, occurred_at=_at(off), quiz_def_id=uuid4())
        )
    await db_session.commit()

    first = await get_gamification(db_session, student_id=student.id, now_utc=NOW)
    assert first.current_streak == 3
    assert first.streak_status == "active"
    assert {"first_quiz", "streak_3"} <= _earned_keys(first)
    assert {"first_quiz", "streak_3"} <= set(first.new_badge_ids)

    second = await get_gamification(db_session, student_id=student.id, now_utc=NOW)
    assert second.new_badge_ids == []  # idempotent: reload awards nothing new
    assert _earned_keys(second) == _earned_keys(first)


async def test_concurrent_first_reads_report_new_badges_once(db_session, migrated_test_database):
    student, module = await _student_in_module(db_session, "concurrent@example.test")
    for off in (-2, -1, 0):
        await _section(db_session, module.id, session_date=_day(off), order_index=off + 3)
        db_session.add(
            _completed_quiz(student.id, module.id, occurred_at=_at(off), quiz_def_id=uuid4())
        )
    await db_session.commit()

    # Force both read paths to overlap at INSERT time. The old implementation returned the pre-insert
    # candidate set, so both racing requests could report the same badge as "new" even though one
    # INSERT was ignored by ON CONFLICT DO NOTHING.
    await db_session.execute(
        text(
            """
            CREATE OR REPLACE FUNCTION test_sleep_student_badge_insert()
            RETURNS trigger AS $$
            BEGIN
                PERFORM pg_sleep(0.25);
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
            """
        )
    )
    await db_session.execute(
        text("DROP TRIGGER IF EXISTS test_sleep_student_badge_insert ON student_badges")
    )
    await db_session.execute(
        text(
            """
            CREATE TRIGGER test_sleep_student_badge_insert
            BEFORE INSERT ON student_badges
            FOR EACH ROW EXECUTE FUNCTION test_sleep_student_badge_insert()
            """
        )
    )
    await db_session.commit()

    engine = create_async_engine(migrated_test_database)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    start = asyncio.Event()

    async def read_once():
        async with session_factory() as session:
            await start.wait()
            return await get_gamification(session, student_id=student.id, now_utc=NOW)

    try:
        tasks = [asyncio.create_task(read_once()), asyncio.create_task(read_once())]
        start.set()
        first, second = await asyncio.gather(*tasks)
        new_counts = Counter([*first.new_badge_ids, *second.new_badge_ids])
        assert new_counts["first_quiz"] == 1
        assert new_counts["streak_3"] == 1
    finally:
        async with session_factory() as cleanup:
            await cleanup.execute(
                text("DROP TRIGGER IF EXISTS test_sleep_student_badge_insert ON student_badges")
            )
            await cleanup.execute(text("DROP FUNCTION IF EXISTS test_sleep_student_badge_insert()"))
            await cleanup.commit()
        await engine.dispose()


async def test_next_scheduled_day_surfaces_upcoming_class(db_session):
    student, module = await _student_in_module(db_session, "next-scheduled@example.test")
    await _section(db_session, module.id, session_date=_day(-1), order_index=1)
    await _section(db_session, module.id, session_date=_day(2), order_index=2)
    db_session.add(
        _completed_quiz(student.id, module.id, occurred_at=_at(-1), quiz_def_id=uuid4())
    )
    await db_session.commit()

    result = await get_gamification(db_session, student_id=student.id, now_utc=NOW)
    assert result.current_streak == 1
    assert result.streak_status == "no_scheduled_day"
    assert result.next_scheduled_day == _day(2)


async def test_streak_resets_to_one_after_a_gap_longest_preserved(db_session):
    student, module = await _student_in_module(db_session, "s@example.test")
    for off in (-4, -3, -2, -1, 0):
        await _section(db_session, module.id, session_date=_day(off), order_index=off + 5)
    for off in (-4, -3, -2, 0):  # gap on day -1
        db_session.add(
            _completed_quiz(student.id, module.id, occurred_at=_at(off), quiz_def_id=uuid4())
        )
    await db_session.commit()

    result = await get_gamification(db_session, student_id=student.id, now_utc=NOW)
    assert result.current_streak == 1
    assert result.longest_streak == 3
    assert result.streak_status == "active"


async def test_quizzes_badge_counts_distinct_definitions_not_retakes(db_session):
    student, module = await _student_in_module(db_session, "s@example.test")
    await _section(db_session, module.id, session_date=_day(0))
    shared_def = uuid4()
    for _ in range(10):  # 10 retakes of ONE quiz
        db_session.add(
            _completed_quiz(student.id, module.id, occurred_at=_at(0), quiz_def_id=shared_def)
        )
    await db_session.commit()
    result = await get_gamification(db_session, student_id=student.id, now_utc=NOW)
    assert "quizzes_10" not in _earned_keys(result)  # retakes do not farm the volume badge

    for _ in range(10):  # 10 DISTINCT quizzes
        db_session.add(
            _completed_quiz(student.id, module.id, occurred_at=_at(0), quiz_def_id=uuid4())
        )
    await db_session.commit()
    result = await get_gamification(db_session, student_id=student.id, now_utc=NOW)
    assert "quizzes_10" in _earned_keys(result)


async def test_perfect_quiz_badge(db_session):
    student, module = await _student_in_module(db_session, "s@example.test")
    await _section(db_session, module.id, session_date=_day(0))
    db_session.add(_completed_quiz(student.id, module.id, occurred_at=_at(0), quiz_def_id=uuid4()))
    db_session.add(
        _event(student.id, module.id, PERFECT_QUIZ_SCORE, occurred_at=_at(0), metadata={"attemptNumber": 1})
    )
    await db_session.commit()
    result = await get_gamification(db_session, student_id=student.id, now_utc=NOW)
    assert "perfect_quiz" in _earned_keys(result)


async def test_topic_mastered_uses_strong_status_label(db_session):
    student, module = await _student_in_module(db_session, "s@example.test")
    section = await _section(db_session, module.id, session_date=_day(0))
    db_session.add(
        StudentTopicMasterySnapshot(
            student_id=student.id,
            module_id=module.id,
            module_section_id=section.id,
            mastery_percentage=95,
            status_label="strong",
        )
    )
    await db_session.commit()
    result = await get_gamification(db_session, student_id=student.id, now_utc=NOW)
    assert "topic_mastered" in _earned_keys(result)


def _mastery(student_id, module_id, section_id, *, status_label="strong"):
    return StudentTopicMasterySnapshot(
        student_id=student_id,
        module_id=module_id,
        module_section_id=section_id,
        mastery_percentage=95,
        status_label=status_label,
    )


async def test_topic_mastered_excludes_unpublished_section(db_session):
    # Security: a topic mastered on a section the student cannot see (unpublished) must NOT grant the
    # badge — otherwise it leaks that hidden content exists. This is the case the all-published Stage 10
    # fixtures never exercised.
    student, module = await _student_in_module(db_session, "s@example.test")
    section = await _section(
        db_session, module.id, session_date=_day(0), publish_status="unpublished"
    )
    db_session.add(_mastery(student.id, module.id, section.id))
    await db_session.commit()
    result = await get_gamification(db_session, student_id=student.id, now_utc=NOW)
    assert "topic_mastered" not in _earned_keys(result)


async def test_topic_mastered_excludes_inactive_module(db_session):
    # Same leak class via a deactivated module — the section is published but the module is no longer
    # active, so it is not student-visible and must not grant the badge.
    student, module = await _student_in_module(db_session, "s@example.test")
    section = await _section(db_session, module.id, session_date=_day(0))
    db_session.add(_mastery(student.id, module.id, section.id))
    module.is_active = False
    await db_session.commit()
    result = await get_gamification(db_session, student_id=student.id, now_utc=NOW)
    assert "topic_mastered" not in _earned_keys(result)


async def test_topic_mastered_excludes_lost_membership(db_session):
    # Same leak class via a dropped enrollment — visible content requires an active student membership.
    student, module = await _student_in_module(db_session, "s@example.test")
    section = await _section(db_session, module.id, session_date=_day(0))
    db_session.add(_mastery(student.id, module.id, section.id))
    membership = await db_session.scalar(
        select(CourseMembership).where(
            CourseMembership.user_id == student.id, CourseMembership.module_id == module.id
        )
    )
    membership.status = "archived"
    await db_session.commit()
    result = await get_gamification(db_session, student_id=student.id, now_utc=NOW)
    assert "topic_mastered" not in _earned_keys(result)


async def test_topic_mastered_still_granted_for_published_section(db_session):
    # Positive guard: the fix must not over-correct — a published+visible mastered section still earns it.
    student, module = await _student_in_module(db_session, "s@example.test")
    section = await _section(db_session, module.id, session_date=_day(0))
    db_session.add(_mastery(student.id, module.id, section.id))
    await db_session.commit()
    result = await get_gamification(db_session, student_id=student.id, now_utc=NOW)
    assert "topic_mastered" in _earned_keys(result)


async def test_module_completed_denominator_excludes_unpublished_section(db_session):
    # Security: an unpublished quiz-bearing section must NOT count toward the module_completed
    # denominator — otherwise the progress bar (e.g. 1/2) leaks that a hidden section exists, and the
    # badge becomes un-earnable. Visible section alone → denominator 1, completing it earns the badge.
    student, module = await _student_in_module(db_session, "s@example.test")
    visible = await _section(db_session, module.id, session_date=_day(-1), order_index=1)
    hidden = await _section(
        db_session, module.id, session_date=_day(0), order_index=2, publish_status="unpublished"
    )
    for section in (visible, hidden):
        db_session.add(
            QuizDefinition(
                module_id=module.id,
                module_section_id=section.id,
                quiz_mode="post_class",
                question_policy={"count": 10},
                source_scope={},
            )
        )
    await db_session.flush()
    # Complete only the visible section's quiz.
    db_session.add(
        _completed_quiz(student.id, module.id, occurred_at=_at(-1), quiz_def_id=uuid4(), section_id=visible.id)
    )
    await db_session.commit()
    result = await get_gamification(db_session, student_id=student.id, now_utc=NOW)
    # Denominator counts ONLY the visible section → 1/1 → badge earned; hidden section never surfaces.
    assert ("module_completed", "module", str(module.id)) in _earned_scoped(result)
    locked = [b for b in result.locked_badges if b.badge_key == "module_completed"]
    assert not locked  # earned, so not shown as locked — and target never leaked the hidden section


async def test_module_completed_requires_all_quiz_bearing_sections(db_session):
    student, module = await _student_in_module(db_session, "s@example.test")
    sec_a = await _section(db_session, module.id, session_date=_day(-1), order_index=1)
    sec_b = await _section(db_session, module.id, session_date=_day(0), order_index=2)
    for section in (sec_a, sec_b):
        db_session.add(
            QuizDefinition(
                module_id=module.id,
                module_section_id=section.id,
                quiz_mode="post_class",
                question_policy={"count": 10},
                source_scope={},
            )
        )
    await db_session.flush()
    # Only section A completed → not yet earned; B is locked with progress 1/2.
    db_session.add(
        _completed_quiz(student.id, module.id, occurred_at=_at(-1), quiz_def_id=uuid4(), section_id=sec_a.id)
    )
    await db_session.commit()
    partial = await get_gamification(db_session, student_id=student.id, now_utc=NOW)
    assert ("module_completed", "module", str(module.id)) not in _earned_scoped(partial)
    locked = [b for b in partial.locked_badges if b.badge_key == "module_completed"]
    assert locked and locked[0].current == 1 and locked[0].target == 2

    # Complete section B too → earned for this module.
    db_session.add(
        _completed_quiz(student.id, module.id, occurred_at=_at(0), quiz_def_id=uuid4(), section_id=sec_b.id)
    )
    await db_session.commit()
    full = await get_gamification(db_session, student_id=student.id, now_utc=NOW)
    assert ("module_completed", "module", str(module.id)) in _earned_scoped(full)


async def test_streak_milestone_keys_off_longest_held_after_later_break(db_session):
    # The subtle trap: a milestone reached while the streak was live must STAY earned after a later
    # scheduled day is missed — streak badges key off longest_streak (max ever), never current.
    student, module = await _student_in_module(db_session, "s@example.test")
    base = date(2026, 6, 10)
    for off in range(3):  # 3 consecutive scheduled days, all engaged
        await _section(db_session, module.id, session_date=base + timedelta(days=off), order_index=off + 1)
        db_session.add(
            _completed_quiz(
                student.id, module.id,
                occurred_at=datetime.combine(base + timedelta(days=off), time(12, 0), tzinfo=UTC),
                quiz_def_id=uuid4(),
            )
        )
    await db_session.commit()

    # Phase 1: load on the 3rd day → 3-day streak, streak_3 earned.
    now1 = datetime.combine(base + timedelta(days=2), time(13, 0), tzinfo=UTC)
    phase1 = await get_gamification(db_session, student_id=student.id, now_utc=now1)
    assert phase1.current_streak == 3
    assert "streak_3" in _earned_keys(phase1)

    # Time passes: a later scheduled day (base+5) goes by with NO activity (missed), today = base+6.
    await _section(db_session, module.id, session_date=base + timedelta(days=5), order_index=10)
    await _section(db_session, module.id, session_date=base + timedelta(days=6), order_index=11)
    await db_session.commit()
    now2 = datetime.combine(base + timedelta(days=6), time(13, 0), tzinfo=UTC)
    phase2 = await get_gamification(db_session, student_id=student.id, now_utc=now2)
    assert phase2.current_streak == 0  # broken by the missed (ended) base+5
    assert phase2.streak_status == "broken"
    assert phase2.longest_streak >= 3  # monotonic longest preserved
    assert "streak_3" in _earned_keys(phase2)  # milestone STILL held — keyed off longest, sticky


async def test_badges_are_sticky_after_events_removed(db_session):
    student, module = await _student_in_module(db_session, "s@example.test")
    for off in (-2, -1, 0):
        await _section(db_session, module.id, session_date=_day(off), order_index=off + 3)
        db_session.add(
            _completed_quiz(student.id, module.id, occurred_at=_at(off), quiz_def_id=uuid4())
        )
    await db_session.commit()
    earned_first = _earned_keys(await get_gamification(db_session, student_id=student.id, now_utc=NOW))
    assert "streak_3" in earned_first

    # Data changes: every event is deleted. Earned badges must NOT be revoked.
    await db_session.execute(
        delete(StudentActivityEvent).where(StudentActivityEvent.student_id == student.id)
    )
    await db_session.commit()
    after = await get_gamification(db_session, student_id=student.id, now_utc=NOW)
    assert "streak_3" in _earned_keys(after)  # sticky
    assert after.current_streak == 0  # but the live streak honestly reads 0
    assert after.longest_streak >= 3  # monotonic longest preserved


async def test_reconcile_matches_stored_after_on_read(db_session):
    student, module = await _student_in_module(db_session, "s@example.test")
    for off in (-2, -1, 0):
        await _section(db_session, module.id, session_date=_day(off), order_index=off + 3)
        db_session.add(
            _completed_quiz(student.id, module.id, occurred_at=_at(off), quiz_def_id=uuid4())
        )
    db_session.add(_event(student.id, module.id, STUDIED_SECTION, occurred_at=_at(0), metadata={"sectionId": str(uuid4())}))
    await db_session.commit()

    await get_gamification(db_session, student_id=student.id, now_utc=NOW)
    expected = await compute_expected_badges(db_session, student_id=student.id, now_utc=NOW)
    stored_rows = (
        await db_session.scalars(select(StudentBadge).where(StudentBadge.student_id == student.id))
    ).all()
    stored = {(r.badge_key, r.scope_type, r.scope_id) for r in stored_rows}
    assert expected - stored == set()  # nothing currently-qualified is missing from stored


async def test_studied_section_counts_as_engagement_and_first_summary(db_session):
    student, module = await _student_in_module(db_session, "s@example.test")
    await _section(db_session, module.id, session_date=_day(0))
    db_session.add(
        _event(student.id, module.id, STUDIED_SECTION, occurred_at=_at(0), metadata={"sectionId": str(uuid4())})
    )
    await db_session.commit()
    result = await get_gamification(db_session, student_id=student.id, now_utc=NOW)
    assert result.current_streak == 1  # opening a summary keeps the streak alive
    assert result.streak_status == "active"
    assert "first_summary" in _earned_keys(result)
