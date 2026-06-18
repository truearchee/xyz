"""Stage 6a — per-attempt pool sampling (pure function: recency bias, cross-section spread,
exhaustion-recycle, seed determinism). Gate proof (2): proven WITHOUT the database, so a sampling bug is
reproducible from a seed and the browser gate's "fresh combination" claim rests on a seedable sampler.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.domains.quiz.sampling import (
    PoolQuestionRef,
    SectionSamplePlan,
    sample_across_sections,
)


def _ref(*, seen_offset_minutes: int | None = None) -> PoolQuestionRef:
    last_seen = (
        None
        if seen_offset_minutes is None
        else datetime(2026, 6, 1, tzinfo=UTC) + timedelta(minutes=seen_offset_minutes)
    )
    return PoolQuestionRef(
        id=uuid4(),
        question_text="q",
        explanation="e",
        options=[{"text": "a", "isCorrect": True}, {"text": "b", "isCorrect": False}],
        last_seen=last_seen,
    )


def test_recency_bias_prefers_unseen_over_seen():
    unseen = [_ref() for _ in range(3)]
    seen = [_ref(seen_offset_minutes=i) for i in range(2)]
    plan = SectionSamplePlan(section_id=uuid4(), pool_questions=unseen + seen, count=3)
    chosen = sample_across_sections([plan], seed=42)
    chosen_ids = {c.id for c in chosen}
    assert len(chosen) == 3
    # All three drawn are from the unseen set (recency bias) — no seen question while unseen remain.
    assert chosen_ids == {q.id for q in unseen}


def test_cross_section_spread_is_even():
    s1 = SectionSamplePlan(section_id=uuid4(), pool_questions=[_ref() for _ in range(6)], count=2)
    s2 = SectionSamplePlan(section_id=uuid4(), pool_questions=[_ref() for _ in range(6)], count=2)
    s3 = SectionSamplePlan(section_id=uuid4(), pool_questions=[_ref() for _ in range(6)], count=2)
    s1_ids = {q.id for q in s1.pool_questions}
    s2_ids = {q.id for q in s2.pool_questions}
    s3_ids = {q.id for q in s3.pool_questions}
    chosen = sample_across_sections([s1, s2, s3], seed=7)
    assert len(chosen) == 6  # 2 per section
    assert sum(1 for c in chosen if c.id in s1_ids) == 2
    assert sum(1 for c in chosen if c.id in s2_ids) == 2
    assert sum(1 for c in chosen if c.id in s3_ids) == 2


def test_exhaustion_recycles_oldest_seen_no_error():
    # 2 unseen + 2 seen, draw 3 → 2 unseen + the single OLDEST-seen recycled. Never raises, never new gen.
    unseen = [_ref() for _ in range(2)]
    older = _ref(seen_offset_minutes=1)
    newer = _ref(seen_offset_minutes=99)
    plan = SectionSamplePlan(section_id=uuid4(), pool_questions=unseen + [newer, older], count=3)
    chosen = sample_across_sections([plan], seed=1)
    chosen_ids = [c.id for c in chosen]
    assert len(chosen) == 3
    assert {unseen[0].id, unseen[1].id}.issubset(set(chosen_ids))
    assert older.id in chosen_ids  # oldest-seen recycled first
    assert newer.id not in chosen_ids


def test_seed_determinism_reproducible_and_varies():
    pool = [_ref() for _ in range(12)]
    plan = SectionSamplePlan(section_id=uuid4(), pool_questions=pool, count=4)

    a = [c.id for c in sample_across_sections([plan], seed=123)]
    b = [c.id for c in sample_across_sections([plan], seed=123)]
    assert a == b  # same seed → identical sample (deterministic gate)

    orderings = {
        tuple(c.id for c in sample_across_sections([plan], seed=s)) for s in range(8)
    }
    assert len(orderings) > 1  # different attempt seeds → observably different combinations


def test_exclude_drops_prefix_questions():
    pool = [_ref() for _ in range(6)]
    plan = SectionSamplePlan(section_id=uuid4(), pool_questions=pool, count=3)
    excluded = frozenset({pool[0].id, pool[1].id})
    chosen = sample_across_sections([plan], seed=5, exclude=excluded)
    assert len(chosen) == 3
    assert excluded.isdisjoint({c.id for c in chosen})
