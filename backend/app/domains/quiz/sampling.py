"""Per-attempt pool sampling — pure, seedable, recency-biased (Stage 6a).

How "retakes get new questions" survives reuse: each attempt SAMPLES a quiz-length combination from the
prepared section pool(s), biased toward questions THIS student has not recently seen. A multi-section quiz
samples a SPREAD across its in-scope sections (roughly even coverage per section — never all from one
lecture). On exhaustion (the student has seen everything in a section) the oldest-seen are recycled — NO
new AI call. The whole thing is a PURE function of (pools, exposure, seed): a fixed seed → a reproducible
sample (so the browser gate is deterministic and sampling bugs reproduce); a different attempt seed → an
observably different combination wherever the pool is larger than the draw.

This module does NO database I/O — the caller loads pool questions + per-student exposure and snapshots the
returned selection. Correctness rides on option identity (the snapshot shuffles display order later).
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

# Mixed into the attempt seed per section index so different in-scope sections get different — but still
# deterministic — shuffles from one attempt seed (Knuth multiplicative constant; value is irrelevant, only
# that it decorrelates indices).
_SECTION_SEED_MIX = 2654435761


@dataclass(frozen=True)
class PoolQuestionRef:
    """A pool question + this student's exposure to it. ``last_seen`` is None iff the student has never
    had this PoolQuestion snapshotted into one of their attempts (i.e. it is UNSEEN)."""

    id: UUID
    question_text: str
    explanation: str
    options: list  # canonical [{"text": str, "isCorrect": bool}, ...]
    last_seen: datetime | None


@dataclass(frozen=True)
class SectionSamplePlan:
    """One in-scope section's candidate pool questions + how many to draw from it (cross-section spread)."""

    section_id: UUID
    pool_questions: list[PoolQuestionRef]
    count: int


def sample_one_section(
    plan: SectionSamplePlan,
    rng: random.Random,
    *,
    exclude: frozenset[UUID] = frozenset(),
) -> list[PoolQuestionRef]:
    """Recency-biased draw from a single section: UNSEEN first (seeded shuffle for variety), then
    least-recently-seen (exhaustion-recycle, oldest first). Deterministic for a given ``rng`` state."""
    candidates = [q for q in plan.pool_questions if q.id not in exclude]
    unseen = [q for q in candidates if q.last_seen is None]
    seen = [q for q in candidates if q.last_seen is not None]
    rng.shuffle(unseen)
    # Oldest-seen first; id is the stable secondary key so equal-recency ties are deterministic.
    seen.sort(key=lambda q: (q.last_seen, str(q.id)))
    ordered = unseen + seen
    return ordered[: max(0, plan.count)]


def sample_across_sections(
    plans: list[SectionSamplePlan],
    *,
    seed: int,
    exclude: frozenset[UUID] = frozenset(),
) -> list[PoolQuestionRef]:
    """Sample each in-scope section independently (even spread) under one attempt seed. ``exclude`` drops
    questions already placed in the attempt (the retake mistake-prefix; 6c). Order follows ``plans``."""
    result: list[PoolQuestionRef] = []
    for index, plan in enumerate(plans):
        rng = random.Random(seed ^ (index * _SECTION_SEED_MIX))
        result.extend(sample_one_section(plan, rng, exclude=exclude))
    return result


def seed_for_attempt(attempt_id: UUID, *, override: int | None = None) -> int:
    """Deterministic per-attempt seed (stable production variation), or a test-injected override. The
    override path is how the E2E gate makes assembly reproducible (mirrors the existing fault-injection
    env hooks); production always derives from the attempt id."""
    if override is not None:
        return override
    return int.from_bytes(attempt_id.bytes[:8], "big")
