"""Pure unit tests for ``derive_streak`` (Stage 10a) — no DB, no clock.

These pin the exact streak rules where flaky logic hides: reset-after-an-ended-miss, neutral no-class
days, today-not-yet-broken, future days ignored, and the monotonic longest surviving a break.
"""

from __future__ import annotations

from datetime import date, timedelta

from app.domains.gamification.streak import (
    ACTIVE,
    BROKEN,
    NEEDS_ACTIVITY_TODAY,
    NO_SCHEDULED_DAY,
    StreakInputs,
    derive_streak,
)

TODAY = date(2026, 6, 20)


def _d(offset: int) -> date:
    return TODAY + timedelta(days=offset)


def _inputs(scheduled, engaged, *, today=TODAY, prior_longest=0) -> StreakInputs:
    return StreakInputs(
        scheduled_days=frozenset(scheduled),
        engagement_days=frozenset(engaged),
        today_local=today,
        prior_longest=prior_longest,
    )


def test_active_today_satisfied_extends_streak():
    # Three consecutive scheduled days all engaged, today included.
    scheduled = {_d(-2), _d(-1), _d(0)}
    result = derive_streak(_inputs(scheduled, scheduled))
    assert result.current_streak == 3
    assert result.streak_status == ACTIVE
    assert result.today_is_scheduled is True
    assert result.today_satisfied is True
    assert result.longest_streak == 3


def test_needs_activity_today_keeps_live_streak():
    # Two prior scheduled days engaged; today scheduled but not yet satisfied — streak NOT broken.
    scheduled = {_d(-2), _d(-1), _d(0)}
    engaged = {_d(-2), _d(-1)}
    result = derive_streak(_inputs(scheduled, engaged))
    assert result.current_streak == 2  # today is skipped, not counted, not breaking
    assert result.streak_status == NEEDS_ACTIVITY_TODAY
    assert result.today_is_scheduled is True
    assert result.today_satisfied is False


def test_broken_after_ended_missed_day_even_with_today_scheduled():
    # A prior scheduled day (yesterday) fully ended with no activity; today scheduled, not yet done.
    scheduled = {_d(-3), _d(-2), _d(-1), _d(0)}
    engaged = {_d(-3)}  # the -2 and -1 scheduled days were missed
    result = derive_streak(_inputs(scheduled, engaged))
    assert result.current_streak == 0
    assert result.streak_status == BROKEN


def test_scenario_b_reset_to_one_after_gap():
    # The roadmap's Scenario B: a 3-run that ended 3 days ago, then two missed scheduled days, then
    # activity today → current resets to 1 (not 4), longest preserved at 3.
    scheduled = {_d(-5), _d(-4), _d(-3), _d(-2), _d(-1), _d(0)}
    engaged = {_d(-5), _d(-4), _d(-3), _d(0)}  # gap at -2 and -1
    result = derive_streak(_inputs(scheduled, engaged))
    assert result.current_streak == 1
    assert result.longest_streak == 3
    assert result.streak_status == ACTIVE


def test_neutral_no_class_days_do_not_break():
    # Scheduled Mon/Wed/Fri (gaps are non-class days), all engaged → a 3-day streak.
    scheduled = {_d(-4), _d(-2), _d(0)}
    result = derive_streak(_inputs(scheduled, scheduled))
    assert result.current_streak == 3
    assert result.streak_status == ACTIVE


def test_future_scheduled_days_are_ignored():
    scheduled = {_d(-1), _d(0), _d(2), _d(5)}
    engaged = {_d(-1), _d(0)}
    result = derive_streak(_inputs(scheduled, engaged))
    assert result.current_streak == 2
    assert result.next_scheduled_day == _d(2)
    assert result.streak_status == ACTIVE


def test_no_scheduled_day_today_keeps_streak_safe():
    # Today is not a class day; a live streak ended on the last scheduled day (yesterday).
    scheduled = {_d(-2), _d(-1)}
    result = derive_streak(_inputs(scheduled, scheduled))
    assert result.current_streak == 2
    assert result.today_is_scheduled is False
    assert result.streak_status == NO_SCHEDULED_DAY


def test_no_scheduled_day_but_last_ended_missed_is_broken():
    # Today not a class day, but the most recent scheduled day was missed → broken, not "safe".
    scheduled = {_d(-2), _d(-1)}
    engaged = {_d(-2)}  # -1 missed
    result = derive_streak(_inputs(scheduled, engaged))
    assert result.current_streak == 0
    assert result.streak_status == BROKEN


def test_brand_new_first_scheduled_day_today_unsatisfied():
    # The very first scheduled day is today and nothing is missed yet → needs activity, not broken.
    scheduled = {_d(0)}
    result = derive_streak(_inputs(scheduled, set()))
    assert result.current_streak == 0
    assert result.streak_status == NEEDS_ACTIVITY_TODAY


def test_no_schedule_at_all_is_no_scheduled_day():
    result = derive_streak(_inputs(set(), set()))
    assert result.current_streak == 0
    assert result.streak_status == NO_SCHEDULED_DAY
    assert result.next_scheduled_day is None


def test_longest_survives_a_break_via_window():
    # A 5-run that broke a while ago; current is just today. Longest reflects the historical 5-run
    # purely from the visible window even with prior_longest=0.
    scheduled = {_d(-8), _d(-7), _d(-6), _d(-5), _d(-4), _d(-1), _d(0)}
    engaged = {_d(-8), _d(-7), _d(-6), _d(-5), _d(-4), _d(0)}  # gap at -1
    result = derive_streak(_inputs(scheduled, engaged))
    assert result.current_streak == 1
    assert result.longest_streak == 5


def test_longest_uses_prior_when_window_is_shorter():
    # The window no longer contains the best run, but the stored monotonic value remembers it.
    scheduled = {_d(-1), _d(0)}
    result = derive_streak(_inputs(scheduled, scheduled, prior_longest=9))
    assert result.current_streak == 2
    assert result.longest_streak == 9  # never decreases below the stored max


def test_missed_non_adjacent_scheduled_day_breaks_trailing_run():
    # Scheduled -2,-1,0 ; engaged -2 and 0 but -1 missed → trailing run is just today.
    scheduled = {_d(-2), _d(-1), _d(0)}
    engaged = {_d(-2), _d(0)}
    result = derive_streak(_inputs(scheduled, engaged))
    assert result.current_streak == 1
    assert result.longest_streak == 1
    assert result.streak_status == ACTIVE
