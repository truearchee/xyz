"""Pure badge evaluation (Stage 10) — shared by the on-read service AND the reconcile tool.

``evaluate_badges`` returns the FULL set of badge identities a student currently qualifies for, computed
only from a ``BadgeMetrics`` snapshot (no DB, no clock). The service intersects this with the
already-stored set to decide what to INSERT (sticky + idempotent persistence lives in the service, not
here); the reconcile tool compares it to stored state to prove "reproducible from events". Because both
call this same function, "recompute == stored" is a meaningful equality.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.domains.gamification.catalog import CATALOG, M_MODULE_COMPLETED, MODULE
from app.platform.db.models.student_badge import GLOBAL_SCOPE_ID

# An earned-badge identity: (badge_key, scope_type, scope_id).
EarnedKey = tuple[str, str, UUID]


@dataclass(frozen=True)
class BadgeMetrics:
    longest_streak: int
    distinct_quiz_definitions: int
    distinct_studied_sections: int
    flashcard_days: int
    has_completed_quiz: bool
    has_perfect_quiz: bool
    has_term_saved: bool
    has_flashcard: bool
    has_mastered_topic: bool
    has_first_week_activity: bool
    module_completed_ids: frozenset[UUID]


def metric_values(metrics: BadgeMetrics) -> dict[str, int]:
    """Scalar value per metric key for the global badges (booleans as 0/1). Drives BOTH qualification
    and the lockedBadge progress (current/target) the API returns."""
    return {
        "longest_streak": metrics.longest_streak,
        "distinct_quiz_definitions": metrics.distinct_quiz_definitions,
        "distinct_studied_sections": metrics.distinct_studied_sections,
        "flashcard_days": metrics.flashcard_days,
        "has_completed_quiz": int(metrics.has_completed_quiz),
        "has_perfect_quiz": int(metrics.has_perfect_quiz),
        "has_term_saved": int(metrics.has_term_saved),
        "has_flashcard": int(metrics.has_flashcard),
        "has_mastered_topic": int(metrics.has_mastered_topic),
        "has_first_week_activity": int(metrics.has_first_week_activity),
    }


def evaluate_badges(metrics: BadgeMetrics) -> set[EarnedKey]:
    """The full set of badge identities the student currently qualifies for (global + per-module)."""
    values = metric_values(metrics)
    qualified: set[EarnedKey] = set()
    for badge in CATALOG:
        if badge.metric == M_MODULE_COMPLETED:
            continue  # per-module, handled separately below
        if values.get(badge.metric, 0) >= badge.target:
            qualified.add((badge.badge_key, badge.scope_type, GLOBAL_SCOPE_ID))
    for module_id in metrics.module_completed_ids:
        qualified.add(("module_completed", MODULE, module_id))
    return qualified
