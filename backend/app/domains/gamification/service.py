"""On-read gamification service (Stage 10).

Computes the unified Learning streak and evaluates badges when a student loads their progress. Streaks
are derived fresh every read; badges are evaluated for not-yet-earned entries, persisted idempotently
(``INSERT … ON CONFLICT DO NOTHING``), and sticky (never revoked). No worker, no AI, no frontend
awarding. The monotonic ``longest_streak`` + a ``last_seen`` marker are the only persisted streak state.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from uuid6 import uuid7

from app.domains.gamification.badges import BadgeMetrics, evaluate_badges, metric_values
from app.domains.gamification.catalog import (
    CATALOG,
    CATALOG_BY_KEY,
    M_LONGEST_STREAK,
    M_MODULE_COMPLETED,
    MODULE,
)
from app.domains.gamification.schemas import (
    EarnedBadgeRead,
    GamificationRead,
    LockedBadgeRead,
    ProgressItemRead,
)
from app.domains.gamification.streak import StreakInputs, StreakResult, derive_streak
from app.platform.auth.context import CurrentUserContext
from app.platform.config import settings
from app.platform.db.models import StudentBadge, StudentStreakState
from app.platform.db.models.student_badge import GLOBAL_SCOPE_ID
from app.platform.query.gamification_read import (
    earliest_scheduled_day,
    engagement_days,
    load_badge_counts,
    next_scheduled_class_day,
    scheduled_class_days,
)

_STREAK_MILESTONES = (3, 7, 30)


def _has_first_week_activity(scheduled: set, engaged: set) -> bool:
    """>=1 engagement day within the 7-day window that starts on the first scheduled class day."""
    if not scheduled:
        return False
    first = min(scheduled)
    window_end = first + timedelta(days=6)
    return any(first <= day <= window_end for day in engaged)


def _next_streak_target(longest: int) -> int:
    for milestone in _STREAK_MILESTONES:
        if longest < milestone:
            return milestone
    return _STREAK_MILESTONES[-1]


async def _compute(
    db: AsyncSession, *, student_id: UUID, now_utc: datetime
) -> tuple[StreakResult, BadgeMetrics, dict, datetime | None]:
    """The shared read-side computation (streak + badge metrics) used by BOTH the on-read service and
    the reconcile tool, so "recompute == stored" compares like with like. No writes."""
    tz = ZoneInfo(settings.COURSE_TIMEZONE)
    today_local = now_utc.astimezone(tz).date()

    earliest = await earliest_scheduled_day(db, student_id=student_id)
    window_start = earliest or today_local
    scheduled = await scheduled_class_days(
        db, student_id=student_id, start_date=window_start, end_date=today_local
    )
    next_scheduled = await next_scheduled_class_day(
        db, student_id=student_id, after_date=today_local
    )
    if next_scheduled is not None:
        scheduled.add(next_scheduled)
    engaged = await engagement_days(
        db, student_id=student_id, start_date=window_start, end_date=today_local, tz=tz
    )

    state = await db.get(StudentStreakState, student_id)
    prior_longest = state.longest_streak if state else 0
    prior_last_seen = state.last_seen_gamification_at if state else None

    streak = derive_streak(
        StreakInputs(
            scheduled_days=frozenset(scheduled),
            engagement_days=frozenset(engaged),
            today_local=today_local,
            prior_longest=prior_longest,
        )
    )

    counts = await load_badge_counts(db, student_id=student_id, tz=tz)
    module_progress: dict[UUID, tuple[int, int]] = counts.pop("module_completion_progress")
    metrics = BadgeMetrics(
        longest_streak=streak.longest_streak,
        has_first_week_activity=_has_first_week_activity(scheduled, engaged),
        **counts,
    )
    return streak, metrics, module_progress, prior_last_seen


async def compute_expected_badges(db: AsyncSession, *, student_id: UUID, now_utc: datetime) -> set:
    """The badge identities a student SHOULD have, recomputed purely from events/snapshots/schedule.
    The reconcile tool compares this to stored ``student_badges`` to prove reproducibility — but note
    earned badges are sticky, so a fair reconcile checks stored ⊇ (would-earn ∩ catalog), never that
    stored == would-earn (data may have changed after an award)."""
    _streak, metrics, _module_progress, _prior_last_seen = await _compute(
        db, student_id=student_id, now_utc=now_utc
    )
    return evaluate_badges(metrics)


async def get_student_gamification(
    db: AsyncSession,
    *,
    current_user: CurrentUserContext,
    now_utc: datetime | None = None,
) -> GamificationRead:
    """Role-gated entry for the HTTP surface (students only; 403 otherwise). The student is always the
    authenticated caller — there is no ``student_id`` parameter to spoof another student."""
    if current_user.role != "student":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    return await get_gamification(db, student_id=current_user.user_id, now_utc=now_utc)


async def get_gamification(
    db: AsyncSession,
    *,
    student_id: UUID,
    now_utc: datetime | None = None,
) -> GamificationRead:
    now_utc = now_utc or datetime.now(UTC)
    streak, metrics, module_progress, prior_last_seen = await _compute(
        db, student_id=student_id, now_utc=now_utc
    )
    values = metric_values(metrics)
    qualified = evaluate_badges(metrics)

    earned_rows = (
        await db.scalars(select(StudentBadge).where(StudentBadge.student_id == student_id))
    ).all()
    earned_keys = {(row.badge_key, row.scope_type, row.scope_id) for row in earned_rows}
    new_keys = qualified - earned_keys
    inserted_badge_ids: set[str] = set()

    # ── Persist new awards (idempotent + sticky) + monotonic streak state ─────
    for badge_key, scope_type, scope_id in new_keys:
        badge_def = CATALOG_BY_KEY.get(badge_key)
        if badge_def is None:
            continue
        qualified_value = _qualified_value(badge_def, values, module_progress, scope_id)
        result = await db.execute(
            pg_insert(StudentBadge)
            .values(
                id=uuid7(),
                student_id=student_id,
                badge_key=badge_key,
                scope_type=scope_type,
                scope_id=scope_id,
                rule_version=badge_def.rule_version,
                qualified_value=qualified_value,
                threshold=badge_def.target,
            )
            .on_conflict_do_nothing(constraint="uq_student_badges_student_key_scope")
            .returning(StudentBadge.badge_key)
        )
        inserted = result.scalar_one_or_none()
        if inserted is not None:
            inserted_badge_ids.add(inserted)

    await db.execute(
        pg_insert(StudentStreakState)
        .values(
            student_id=student_id,
            longest_streak=streak.longest_streak,
            last_seen_gamification_at=now_utc,
        )
        .on_conflict_do_update(
            index_elements=[StudentStreakState.student_id],
            set_={
                "longest_streak": func.greatest(
                    StudentStreakState.longest_streak, streak.longest_streak
                ),
                "last_seen_gamification_at": now_utc,
                "updated_at": now_utc,
            },
        )
    )
    await db.commit()

    # ── Assemble the response (re-read earned so new awards carry earned_at) ──
    earned_rows = (
        await db.scalars(select(StudentBadge).where(StudentBadge.student_id == student_id))
    ).all()
    earned_now = {(row.badge_key, row.scope_type, row.scope_id): row for row in earned_rows}

    earned_badges = _earned_views(earned_now)
    locked_badges = _locked_views(earned_now.keys(), values, module_progress)
    progress_items = _progress_items(streak, values)
    new_badge_ids = sorted(inserted_badge_ids)

    return GamificationRead(
        current_streak=streak.current_streak,
        longest_streak=streak.longest_streak,
        today_is_scheduled=streak.today_is_scheduled,
        today_satisfied=streak.today_satisfied,
        next_scheduled_day=streak.next_scheduled_day,
        streak_status=streak.streak_status,
        earned_badges=earned_badges,
        locked_badges=locked_badges,
        progress_items=progress_items,
        new_badge_ids=new_badge_ids,
        last_seen_at=prior_last_seen,
    )


def _qualified_value(badge_def, values, module_progress, scope_id) -> int | None:
    if badge_def.metric == M_MODULE_COMPLETED:
        progress = module_progress.get(scope_id)
        return progress[0] if progress else None
    return values.get(badge_def.metric)


def _earned_views(earned_now: dict) -> list[EarnedBadgeRead]:
    views: list[EarnedBadgeRead] = []
    for (badge_key, _scope_type, _scope_id), row in earned_now.items():
        badge_def = CATALOG_BY_KEY.get(badge_key)
        if badge_def is None:
            continue  # unknown/legacy key — never surface a badge the catalog can't describe
        views.append(
            EarnedBadgeRead(
                badge_key=row.badge_key,
                family=badge_def.family,
                title=badge_def.title,
                description=badge_def.description,
                icon=badge_def.icon,
                scope_type=row.scope_type,
                scope_id=row.scope_id,
                earned_at=row.earned_at,
                qualified_value=row.qualified_value,
                threshold=row.threshold,
            )
        )
    views.sort(key=lambda view: view.earned_at)
    return views


def _locked_views(earned_keys, values, module_progress) -> list[LockedBadgeRead]:
    earned = set(earned_keys)
    views: list[LockedBadgeRead] = []
    for badge in CATALOG:
        if badge.metric == M_MODULE_COMPLETED:
            continue  # per-module, handled below
        if (badge.badge_key, badge.scope_type, GLOBAL_SCOPE_ID) in earned:
            continue
        current = min(values.get(badge.metric, 0), badge.target)
        views.append(
            LockedBadgeRead(
                badge_key=badge.badge_key,
                family=badge.family,
                title=badge.title,
                description=badge.description,
                icon=badge.icon,
                scope_type=badge.scope_type,
                scope_id=GLOBAL_SCOPE_ID,
                current=current,
                target=badge.target,
            )
        )
    module_badge = CATALOG_BY_KEY["module_completed"]
    for module_id, (done, total) in sorted(module_progress.items(), key=lambda item: str(item[0])):
        if total <= 0:
            continue  # no quiz-bearing sections → not completable
        if ("module_completed", MODULE, module_id) in earned:
            continue
        views.append(
            LockedBadgeRead(
                badge_key=module_badge.badge_key,
                family=module_badge.family,
                title=module_badge.title,
                description=module_badge.description,
                icon=module_badge.icon,
                scope_type=MODULE,
                scope_id=module_id,
                current=done,
                target=total,
            )
        )
    return views


def _progress_items(streak: StreakResult, values: dict) -> list[ProgressItemRead]:
    return [
        ProgressItemRead(
            key="streak",
            label="Longest streak",
            current=values.get(M_LONGEST_STREAK, 0),
            target=_next_streak_target(values.get(M_LONGEST_STREAK, 0)),
        ),
        ProgressItemRead(
            key="quizzes",
            label="Quizzes completed",
            current=values.get("distinct_quiz_definitions", 0),
            target=10,
        ),
        ProgressItemRead(
            key="summaries",
            label="Summaries studied",
            current=values.get("distinct_studied_sections", 0),
            target=10,
        ),
        ProgressItemRead(
            key="flashcard_days",
            label="Flashcard days",
            current=values.get("flashcard_days", 0),
            target=5,
        ),
    ]
