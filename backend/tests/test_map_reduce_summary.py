"""Map-reduce detailed summarization (Stage 4.5.1a, F-4.5-51).

Covers, on the deterministic adapter only (no real provider):
  - partition: fewest units under BOTH caps, never splits a segment, deterministic + budget-sensitive
    hash, cost guard, oversized-single-segment edge.
  - the lenient DetailedSummaryPartial validator + its last-valid-object discrimination (a permissive
    partial must still skip a reasoning model's brace-bearing thinking fragments).
  - the engine end-to-end through the gateway: map_reduce strategy + full coverageManifest persisted,
    the late-topic-sentinel content surviving map→reduce (provider-free coverage proof), the §3.3 tiered
    reduce preserving coverage, C3 resume (reuse vs budget-change invalidation).
  - the brief path stays single_call; migration 0015 objects exist.
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from uuid6 import uuid7

from app.domains.transcripts.map_reduce import (
    MapReduceError,
    MapReduceRunner,
    SegmentText,
    partition_segments,
)
from app.domains.transcripts.summary_service import (
    generate_brief_summary_async,
    generate_detailed_summary_async,
    insert_summary_jobs,
)
from app.platform.db.models import (
    AIRequestLog,
    GeneratedLectureSummary,
    IngestionJob,
    MapUnitSummary,
)
from app.platform.llm.errors import InvalidOutput
from app.platform.llm.gateway import LLMGateway
from app.platform.llm.models.summary import DetailedSummary, DetailedSummaryPartial
from app.platform.llm.provider import DeterministicTestProvider
from app.platform.llm.validation import OutputValidator
from tests.test_llm_gateway import _FakeLimiter
from tests.test_transcript_worker import _create_parsed_transcript, _session_factory


# ── pure partition ────────────────────────────────────────────────────────────


def _segs(*texts: str) -> list[SegmentText]:
    return [SegmentText(segment_id=uuid7(), text=t) for t in texts]


def test_partition_groups_fewest_units_under_char_cap():
    segs = _segs("aaaa", "bbbb", "cccc", "dddd")  # 4 chars each
    part = partition_segments(
        segs, char_budget=10, token_budget=1000, max_units=10, chunker_version="v", transcript_checksum="ck"
    )
    # "aaaa bbbb" = 9 ≤ 10; adding " cccc" = 14 > 10 → two units of two segments each (fewest).
    assert [u.text for u in part.units] == ["aaaa bbbb", "cccc dddd"]
    assert all(u.char_count <= 10 for u in part.units)
    assert part.units[0].start_segment_id == segs[0].segment_id
    assert part.units[0].end_segment_id == segs[1].segment_id
    assert [u.unit_index for u in part.units] == [0, 1]


def test_partition_deterministic_and_hash_is_budget_sensitive():
    segs = _segs("alpha", "beta", "gamma")
    a = partition_segments(
        segs, char_budget=12, token_budget=999, max_units=9, chunker_version="v1", transcript_checksum="ck"
    )
    b = partition_segments(
        segs, char_budget=12, token_budget=999, max_units=9, chunker_version="v1", transcript_checksum="ck"
    )
    assert a.partition_config_hash == b.partition_config_hash
    assert [u.text for u in a.units] == [u.text for u in b.units]
    c = partition_segments(
        segs, char_budget=999, token_budget=999, max_units=9, chunker_version="v1", transcript_checksum="ck"
    )
    assert len(c.units) == 1  # everything fits one unit
    assert c.partition_config_hash != a.partition_config_hash  # budget folded into the hash (C3)


def test_partition_token_cap_splits_when_char_fits():
    # char budget huge; the token cap (ceil(chars/3.5)) is the binding constraint.
    segs = _segs("xxxxxxx", "yyyyyyy")  # 7 chars each
    part = partition_segments(
        segs, char_budget=10_000, token_budget=3, max_units=10, chunker_version="v", transcript_checksum="ck"
    )
    assert len(part.units) == 2  # "xxxxxxx yyyyyyy" = 15 chars → ceil(15/3.5)=5 > 3 → split


def test_partition_cost_guard_raises_over_max_units():
    segs = _segs("a", "b", "c", "d")
    with pytest.raises(MapReduceError):
        partition_segments(
            segs, char_budget=1, token_budget=1, max_units=2, chunker_version="v", transcript_checksum="ck"
        )


def test_partition_oversized_single_segment_is_its_own_unit():
    segs = _segs("a", "bbbbbbbbbb", "c")  # middle 10 chars > budget 5, cannot be split
    part = partition_segments(
        segs, char_budget=5, token_budget=999, max_units=10, chunker_version="v", transcript_checksum="ck"
    )
    assert [u.text for u in part.units] == ["a", "bbbbbbbbbb", "c"]
    assert part.units[1].char_count == 10  # oversized, but never split


# ── lenient partial validator (pure) ──────────────────────────────────────────


def _partial(**overrides) -> str:
    data = {
        "overview": "",
        "keyConcepts": [],
        "importantDefinitions": [],
        "mainExplanations": [],
        "examples": [],
        "examRelevantPoints": [],
    }
    data.update(overrides)
    return json.dumps(data)


def test_detailed_partial_allows_all_empty_sections():
    out = OutputValidator().validate(
        raw_text=_partial(), output_schema=DetailedSummaryPartial, section_type="lecture"
    )
    assert isinstance(out, DetailedSummaryPartial)
    assert out.key_concepts == []


def test_detailed_partial_rejects_object_missing_a_required_key():
    # Drop examRelevantPoints — a fragment lacking the contract keys must NOT validate as a partial.
    raw = json.dumps(
        {
            "overview": "x",
            "keyConcepts": [],
            "importantDefinitions": [],
            "mainExplanations": [],
            "examples": [],
        }
    )
    with pytest.raises(InvalidOutput) as exc:
        OutputValidator().validate(
            raw_text=raw, output_schema=DetailedSummaryPartial, section_type="lecture"
        )
    assert exc.value.error_code == "partial_missing_keys"


def test_detailed_partial_selects_last_valid_skipping_thinking_fragments():
    # A reasoning model emits brace-bearing thinking ({} and a stray object) BEFORE the real partial.
    # Requiring all keys present is what lets last-valid selection skip those and pick the real answer.
    thinking = '{"thought": "let me consider"} prose {} '
    real = _partial(overview="the real partial", keyConcepts=["k"])
    out = OutputValidator().validate(
        raw_text=thinking + real, output_schema=DetailedSummaryPartial, section_type="lecture"
    )
    assert out.overview == "the real partial"


# ── engine end-to-end (deterministic adapter + DB) ─────────────────────────────


def _gateway(factory):
    return LLMGateway(
        provider=DeterministicTestProvider(), limiter=_FakeLimiter(), session_factory=factory
    )


async def _make_detailed_job(db_session: AsyncSession, factory, texts: list[str]):
    transcript, _ = await _create_parsed_transcript(db_session, texts=texts)
    async with factory() as session:
        async with session.begin():
            jobs = dict(await insert_summary_jobs(session, transcript=transcript, enable_detailed=True))
    return transcript, jobs["generate_detailed_summary"]


async def _detailed_summary(factory, transcript_id) -> GeneratedLectureSummary:
    async with factory() as session:
        return (
            await session.execute(
                select(GeneratedLectureSummary).where(
                    GeneratedLectureSummary.transcript_id == transcript_id,
                    GeneratedLectureSummary.summary_type == "detailed_study",
                )
            )
        ).scalar_one()


async def _count_map_logs(factory, ingestion_job_id) -> int:
    async with factory() as session:
        return len(
            (
                await session.execute(
                    select(AIRequestLog).where(
                        AIRequestLog.ingestion_job_id == ingestion_job_id,
                        AIRequestLog.feature == "detailed_summary_map",
                    )
                )
            ).scalars().all()
        )


async def _count_units(factory, transcript_id) -> int:
    async with factory() as session:
        return len(
            (
                await session.execute(
                    select(MapUnitSummary).where(MapUnitSummary.transcript_id == transcript_id)
                )
            ).scalars().all()
        )


@pytest.mark.anyio
async def test_detailed_map_reduce_persists_full_coverage(db_session: AsyncSession, monkeypatch):
    monkeypatch.setenv("LLM_SUMMARY_MAP_UNIT_CHAR_BUDGET", "30")  # force several units from short texts
    factory = _session_factory(db_session)
    texts = [
        "First segment about topic A.",
        "Second on topic B.",
        "Third covering topic C.",
        "Fourth wrapping up the session.",
    ]
    transcript, detailed_id = await _make_detailed_job(db_session, factory, texts)

    await generate_detailed_summary_async(detailed_id, gateway=_gateway(factory), session_factory=factory)

    async with factory() as session:
        assert (await session.get(IngestionJob, detailed_id)).status == "completed"
    summary = await _detailed_summary(factory, transcript.id)
    assert summary.generation_strategy == "map_reduce"
    assert summary.truncated is False
    assert summary.backend_used == "nvidia"
    meta = summary.generation_metadata
    n = meta["mapUnitCount"]
    assert n >= 2  # the small budget produced multiple units
    assert meta["coverageManifest"] == list(range(n))  # EVERY unit consumed
    assert len(meta["sourceMapUnitSummaryIds"]) == n
    assert meta["mapPromptVersion"] == "v1" and meta["reducePromptVersion"] == "v1"

    async with factory() as session:
        units = (
            await session.execute(
                select(MapUnitSummary).where(MapUnitSummary.transcript_id == transcript.id)
            )
        ).scalars().all()
    assert len(units) == n
    assert all(u.status == "succeeded" for u in units)
    assert all(u.partial_content is not None and u.ai_request_log_id is not None for u in units)
    assert all(u.source_transcript_checksum == transcript.checksum for u in units)


@pytest.mark.anyio
async def test_late_topic_sentinel_content_survives_into_reduce(db_session: AsyncSession, monkeypatch):
    # The PROOF that matters: the FINAL unit's content reaches the reduce output (not just a manifest
    # count). The input-aware deterministic adapter echoes each unit's tail and the reduce aggregates
    # them, so this holds with no real provider.
    monkeypatch.setenv("LLM_SUMMARY_MAP_UNIT_CHAR_BUDGET", "40")
    factory = _session_factory(db_session)
    texts = [
        "Opening remarks and the first concept.",
        "Middle development of the argument.",
        "Finally we cover LateLectureSentinelTopic.",
    ]
    transcript, detailed_id = await _make_detailed_job(db_session, factory, texts)

    await generate_detailed_summary_async(detailed_id, gateway=_gateway(factory), session_factory=factory)

    summary = await _detailed_summary(factory, transcript.id)
    meta = summary.generation_metadata
    n = meta["mapUnitCount"]
    assert (n - 1) in meta["coverageManifest"]  # structural: final unit index covered
    key_concepts = summary.content_json["keyConcepts"]
    assert any("LateLectureSentinelTopic" in kc for kc in key_concepts)  # content flow-through


@pytest.mark.anyio
async def test_tiered_reduce_branch_preserves_full_coverage(db_session: AsyncSession, monkeypatch):
    # Exercise the §3.3 tiered reduce directly with a controlled reduce-call stub, so convergence and
    # coverage are deterministic (not dependent on adapter output sizes). Coverage is index-based, so a
    # small fixed summary per call is sufficient to prove the tiers fold without losing any unit.
    factory = _session_factory(db_session)
    monkeypatch.setenv("LLM_SUMMARY_REDUCE_INPUT_CHAR_BUDGET", "300")
    monkeypatch.setenv("LLM_SUMMARY_REDUCE_INPUT_TOKEN_BUDGET", "400")  # char is the binding cap
    runner = MapReduceRunner(
        factory,
        _gateway(factory),
        ingestion_job_id=uuid7(),
        transcript_id=uuid7(),
        section_type="lecture",
        source_transcript_checksum="ck",
        attempt_number=1,
    )
    calls: list[str] = []

    async def fake_reduce_call(serialized: str) -> dict:
        calls.append(serialized)
        return {
            "parsed": DetailedSummary(
                overview="o",
                key_concepts=["k"],
                important_definitions=[],
                main_explanations=["m"],
                examples=["e"],
                exam_relevant_points=["p"],
            ),
            "ai_request_log_id": uuid7(),
        }

    monkeypatch.setattr(runner, "_reduce_call", fake_reduce_call)
    partials = [
        ([i], json.loads(_partial(overview="", keyConcepts=[f"m{i}"]))) for i in range(6)
    ]

    _result, coverage = await runner._reduce(partials, depth=0)

    assert coverage == [0, 1, 2, 3, 4, 5]  # tiered fold preserved every unit
    assert len(calls) > 1  # the tiered branch ran (a single-call reduce would be exactly one call)


@pytest.mark.anyio
async def test_resume_reuses_succeeded_partials_on_rerun(db_session: AsyncSession, monkeypatch):
    monkeypatch.setenv("LLM_SUMMARY_MAP_UNIT_CHAR_BUDGET", "30")
    factory = _session_factory(db_session)
    texts = ["Alpha segment text here.", "Beta segment text here.", "Gamma segment text here."]
    transcript, detailed_id = await _make_detailed_job(db_session, factory, texts)

    await generate_detailed_summary_async(detailed_id, gateway=_gateway(factory), session_factory=factory)
    first_logs = await _count_map_logs(factory, detailed_id)
    first_units = await _count_units(factory, transcript.id)
    assert first_units >= 2 and first_logs == first_units

    # Simulate an RQ retry: drop the persisted summary, reset the job to queued (map partials remain).
    async with factory() as session:
        async with session.begin():
            await session.execute(
                delete(GeneratedLectureSummary).where(
                    GeneratedLectureSummary.transcript_id == transcript.id
                )
            )
            job = await session.get(IngestionJob, detailed_id)
            job.status = "queued"
            job.completed_at = None

    await generate_detailed_summary_async(detailed_id, gateway=_gateway(factory), session_factory=factory)

    # Same partition hash + checksum → succeeded partials reused: NO new map calls, unit count steady.
    assert await _count_map_logs(factory, detailed_id) == first_logs
    assert await _count_units(factory, transcript.id) == first_units
    assert (await _detailed_summary(factory, transcript.id)).generation_strategy == "map_reduce"


@pytest.mark.anyio
async def test_budget_change_invalidates_partials_and_remaps(db_session: AsyncSession, monkeypatch):
    monkeypatch.setenv("LLM_SUMMARY_MAP_UNIT_CHAR_BUDGET", "30")
    factory = _session_factory(db_session)
    texts = ["Alpha segment text here.", "Beta segment text here.", "Gamma segment text here."]
    transcript, detailed_id = await _make_detailed_job(db_session, factory, texts)

    await generate_detailed_summary_async(detailed_id, gateway=_gateway(factory), session_factory=factory)
    first_logs = await _count_map_logs(factory, detailed_id)

    async with factory() as session:
        async with session.begin():
            await session.execute(
                delete(GeneratedLectureSummary).where(
                    GeneratedLectureSummary.transcript_id == transcript.id
                )
            )
            job = await session.get(IngestionJob, detailed_id)
            job.status = "queued"
            job.completed_at = None

    # A different budget → different partition_config_hash → the prior partials must NOT be reused (C3).
    monkeypatch.setenv("LLM_SUMMARY_MAP_UNIT_CHAR_BUDGET", "18")
    await generate_detailed_summary_async(detailed_id, gateway=_gateway(factory), session_factory=factory)

    assert await _count_map_logs(factory, detailed_id) > first_logs  # re-mapped under the new hash


@pytest.mark.anyio
async def test_brief_summary_stays_single_call_strategy(db_session: AsyncSession):
    factory = _session_factory(db_session)
    transcript, _ = await _create_parsed_transcript(db_session, texts=["A short brief transcript body."])
    async with factory() as session:
        async with session.begin():
            jobs = dict(await insert_summary_jobs(session, transcript=transcript, enable_detailed=False))

    await generate_brief_summary_async(
        jobs["generate_brief_summary"], gateway=_gateway(factory), session_factory=factory
    )

    async with factory() as session:
        summary = (
            await session.execute(
                select(GeneratedLectureSummary).where(
                    GeneratedLectureSummary.transcript_id == transcript.id,
                    GeneratedLectureSummary.summary_type == "brief",
                )
            )
        ).scalar_one()
    assert summary.generation_strategy == "single_call"
    assert summary.generation_metadata is None


@pytest.mark.anyio
async def test_migration_0015_objects_exist(db_session: AsyncSession):
    cols = (
        await db_session.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name='generated_lecture_summaries' "
                "AND column_name IN ('generation_strategy','generation_metadata')"
            )
        )
    ).scalars().all()
    assert set(cols) == {"generation_strategy", "generation_metadata"}

    assert (
        await db_session.execute(text("SELECT to_regclass('public.map_unit_summaries')"))
    ).scalar() is not None

    constraint = (
        await db_session.execute(
            text(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE conname='ck_ai_request_logs_feature'"
            )
        )
    ).scalar()
    assert "detailed_summary_map" in constraint and "detailed_summary_reduce" in constraint
