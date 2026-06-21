"""Code-defined badge catalog (Stage 10) — the stable source of truth for MVP.

A flat-file/code catalog (no ``BadgeDefinition`` table, deferred post-MVP) mirrors how the event-type and
prompt vocabularies live in code: git gives review/audit/deploy semantics for free. Each badge has a
stable ``badge_key`` (never change it — it is the unique-constraint key), a ``metric`` it reads, and a
``target`` threshold. UI metadata (title/description/icon) is returned by the API so the frontend
interprets nothing locally. ``icon`` is a short token the frontend maps to a glyph.

Scopes: most badges are ``global`` (one per student); ``module_completed`` is ``module``-scoped (earnable
once per module). Counting rules (the mandatory 10a deliverable) are documented per badge below and bind
each to an event/snapshot — every count is reproducible from the event spine + schedule + Stage 9
snapshots (rule 7), and volume badges count DISTINCT source items so re-doing work cannot farm them.
"""

from __future__ import annotations

from dataclasses import dataclass

GLOBAL = "global"
MODULE = "module"

# Badge families.
MILESTONE = "milestone"
CONSISTENCY = "consistency"
MASTERY = "mastery"
EFFORT = "effort"

# Metric keys (see badges.metric_values + the per-module module_completed handling).
M_HAS_COMPLETED_QUIZ = "has_completed_quiz"
M_DISTINCT_QUIZ_DEFINITIONS = "distinct_quiz_definitions"
M_HAS_PERFECT_QUIZ = "has_perfect_quiz"
M_DISTINCT_STUDIED_SECTIONS = "distinct_studied_sections"
M_HAS_TERM_SAVED = "has_term_saved"
M_HAS_FLASHCARD = "has_flashcard"
M_FLASHCARD_DAYS = "flashcard_days"
M_HAS_MASTERED_TOPIC = "has_mastered_topic"
M_HAS_FIRST_WEEK_ACTIVITY = "has_first_week_activity"
M_LONGEST_STREAK = "longest_streak"
M_MODULE_COMPLETED = "module_completed"  # special: per-module set, not a scalar


@dataclass(frozen=True)
class BadgeDef:
    badge_key: str
    family: str
    scope_type: str
    title: str
    description: str
    icon: str
    metric: str
    target: int
    rule_version: int = 1


# The starter catalog (14 badges across the four families). Counting rule noted per entry.
CATALOG: tuple[BadgeDef, ...] = (
    # ── Milestones (first-time, boolean) ─────────────────────────────────────
    BadgeDef("first_quiz", MILESTONE, GLOBAL, "First quiz",
             "Complete your first quiz.", "check",
             M_HAS_COMPLETED_QUIZ, 1),  # >=1 completed_quiz event
    BadgeDef("first_summary", MILESTONE, GLOBAL, "First summary",
             "Open your first section summary.", "book",
             M_DISTINCT_STUDIED_SECTIONS, 1),  # >=1 distinct studied_section
    BadgeDef("first_flashcard", MILESTONE, GLOBAL, "First flashcards",
             "Finish your first flashcard session.", "cards",
             M_HAS_FLASHCARD, 1),  # >=1 glossary_practice_completed (mode=flashcard)
    BadgeDef("first_term_saved", MILESTONE, GLOBAL, "First saved term",
             "Save your first glossary term.", "bookmark",
             M_HAS_TERM_SAVED, 1),  # >=1 glossary_term_saved event
    BadgeDef("first_week_active", MILESTONE, GLOBAL, "Strong start",
             "Do any learning activity in your first scheduled week.", "sunrise",
             M_HAS_FIRST_WEEK_ACTIVITY, 1),  # >=1 engagement day in the first scheduled week
    # ── Consistency (streak milestones, keyed off longest_streak) ─────────────
    BadgeDef("streak_3", CONSISTENCY, GLOBAL, "3-day streak",
             "Learn on 3 scheduled class days in a row.", "flame",
             M_LONGEST_STREAK, 3),
    BadgeDef("streak_7", CONSISTENCY, GLOBAL, "7-day streak",
             "Learn on 7 scheduled class days in a row.", "flame",
             M_LONGEST_STREAK, 7),
    BadgeDef("streak_30", CONSISTENCY, GLOBAL, "30-day streak",
             "Learn on 30 scheduled class days in a row.", "flame",
             M_LONGEST_STREAK, 30),
    # ── Mastery ───────────────────────────────────────────────────────────────
    BadgeDef("topic_mastered", MASTERY, GLOBAL, "Topic mastered",
             "Reach a strong mastery rating on a topic.", "star",
             M_HAS_MASTERED_TOPIC, 1),  # a TopicMasterySnapshot with status_label='strong'
    BadgeDef("perfect_quiz", MASTERY, GLOBAL, "Perfect score",
             "Score 100% on a quiz.", "trophy",
             M_HAS_PERFECT_QUIZ, 1),  # >=1 perfect_quiz_score event
    BadgeDef("module_completed", MASTERY, MODULE, "Module complete",
             "Complete the post-class quiz for every quiz-bearing section in a module.", "medal",
             M_MODULE_COMPLETED, 1),  # per-module: all post_class-quiz sections done
    # ── Effort / volume (distinct source items, anti-farm) ────────────────────
    BadgeDef("quizzes_10", EFFORT, GLOBAL, "Ten quizzes",
             "Complete 10 different quizzes.", "stack",
             M_DISTINCT_QUIZ_DEFINITIONS, 10),  # DISTINCT quiz_definition (retakes don't inflate)
    BadgeDef("flashcard_days_5", EFFORT, GLOBAL, "Flashcard habit",
             "Practice flashcards on 5 different days.", "cards",
             M_FLASHCARD_DAYS, 5),  # DISTINCT local days with a completed flashcard session (D1)
    BadgeDef("summaries_10", EFFORT, GLOBAL, "Ten summaries",
             "Study 10 different section summaries.", "book",
             M_DISTINCT_STUDIED_SECTIONS, 10),  # DISTINCT studied_section (re-reading doesn't inflate)
)

CATALOG_BY_KEY: dict[str, BadgeDef] = {badge.badge_key: badge for badge in CATALOG}
