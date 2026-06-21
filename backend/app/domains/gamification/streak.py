"""Pure streak derivation (Stage 10) — no DB, no clock, no global config.

``derive_streak`` is a pure function over the two ``platform/query`` primitives plus "now" (already
converted to the configured course timezone by the caller). It is the single place the exact streak
rules live, and it is exhaustively unit-tested for the edges where flaky logic hides:

- A scheduled day is "missed" only AFTER its local calendar day fully ends, so **today, if scheduled
  but not yet satisfied, does NOT break the streak** — it is ``needs_activity_today``.
- **No-class days are neutral**: the walk iterates the sorted set of *scheduled* days, so a gap of
  non-class days between two scheduled days never breaks a streak.
- **Future scheduled days are ignored** (filtered to ``<= today``).
- **`longest_streak` is the maximum run ever** — the max of the stored monotonic value and the longest
  engaged run visible in the window (so a best run that broke before the student ever loaded is still
  captured), and it never decreases.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

# streakStatus vocabulary (mirrors the spec).
ACTIVE = "active"
NEEDS_ACTIVITY_TODAY = "needs_activity_today"
BROKEN = "broken"
NO_SCHEDULED_DAY = "no_scheduled_day"


@dataclass(frozen=True)
class StreakInputs:
    scheduled_days: frozenset[date]
    engagement_days: frozenset[date]
    today_local: date
    prior_longest: int = 0


@dataclass(frozen=True)
class StreakResult:
    current_streak: int
    longest_streak: int
    today_is_scheduled: bool
    today_satisfied: bool
    next_scheduled_day: date | None
    streak_status: str


def derive_streak(inputs: StreakInputs) -> StreakResult:
    scheduled = inputs.scheduled_days
    engaged = inputs.engagement_days
    today = inputs.today_local

    today_is_scheduled = today in scheduled
    today_satisfied = today in engaged

    # Scheduled days up to and including today (future days are ignored), ascending.
    past_or_today = sorted(d for d in scheduled if d <= today)
    next_scheduled_day = min((d for d in scheduled if d > today), default=None)

    # The most recent fully-ended scheduled day (strictly before today) and whether it was missed.
    ended = [d for d in past_or_today if d < today]
    last_ended = ended[-1] if ended else None
    last_ended_missed = last_ended is not None and last_ended not in engaged

    # Current streak: the trailing run of engaged scheduled days. Today, if scheduled-but-unsatisfied,
    # is skipped (it has not ended) rather than breaking the run.
    current = 0
    idx = len(past_or_today) - 1
    if idx >= 0 and past_or_today[idx] == today:
        if today_satisfied:
            current += 1
        idx -= 1
    while idx >= 0:
        if past_or_today[idx] in engaged:
            current += 1
            idx -= 1
        else:
            break

    # Longest engaged run visible in the window (consecutive scheduled days, neutral days skipped).
    max_run = 0
    run = 0
    for day in past_or_today:
        if day in engaged:
            run += 1
            max_run = max(max_run, run)
        else:
            run = 0
    longest = max(inputs.prior_longest, max_run, current)

    if today_is_scheduled and today_satisfied:
        status = ACTIVE
    elif current == 0 and last_ended_missed:
        status = BROKEN
    elif today_is_scheduled:
        status = NEEDS_ACTIVITY_TODAY
    else:
        status = NO_SCHEDULED_DAY

    return StreakResult(
        current_streak=current,
        longest_streak=longest,
        today_is_scheduled=today_is_scheduled,
        today_satisfied=today_satisfied,
        next_scheduled_day=next_scheduled_day,
        streak_status=status,
    )
