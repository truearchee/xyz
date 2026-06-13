"""Brief-from-detailed DAG + gating + backfill + fencing (Stage 4.5.1b, ADR-052).

Deterministic adapter only. Covers: the brief derives from the completed detailed (mode-A) — proven by the
brief's AIRequestLog feature + the source-detailed provenance; the §0.1 gating predicate truth table
INCLUDING the negative (a truncated / non-map_reduce detailed is NOT quiz-eligible); the backfill command
(stale selection, dry-run enqueues nothing, cap, idempotent); the stale-write fences (brief-claim checks the
ACTIVE-transcript checksum; map-reduce aborts clean on mid-flight supersede); the AIRequestLog chain helper.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from uuid6 import uuid7

from app.domains.transcripts.backfill import backfill_stale_detailed_summaries
from app.domains.transcripts.map_reduce import MapReduceFenced, MapReduceRunner, SegmentText
from app.domains.transcripts.summary_eligibility import is_full_coverage_detailed
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
    Transcript,
)
from app.platform.llm.gateway import LLMGateway
from app.platform.llm.provider import DeterministicTestProvider
from app.platform.query.summary_read import (
    get_ai_request_log_chain,
    get_latest_transcript_summaries,
)
from tests.test_llm_gateway import _FakeLimiter
from tests.test_transcript_worker import _create_parsed_transcript, _session_factory


def _gateway(factory):
    return LLMGateway(
        provider=DeterministicTestProvider(), limiter=_FakeLimiter(), session_factory=factory
    )


async def _make_detailed_job(db_session, factory, texts):
    transcript, _ = await _create_parsed_transcript(db_session, texts=texts)
    async with factory() as session:
        async with session.begin():
            await insert_summary_jobs(session, transcript=transcript, enable_detailed=True)
        rows = (
            await session.execute(
                select(IngestionJob).where(
                    IngestionJob.transcript_id == transcript.id,
                    IngestionJob.job_type.in_(
                        ("generate_brief_summary", "generate_detailed_summary")
                    ),
                )
            )
        ).scalars().all()
    return transcript, {r.job_type: r.id for r in rows}


async def _summary(factory, transcript_id, summary_type):
    async with factory() as session:
        return (
            await session.execute(
                select(GeneratedLectureSummary).where(
                    GeneratedLectureSummary.transcript_id == transcript_id,
                    GeneratedLectureSummary.summary_type == summary_type,
                )
            )
        ).scalar_one()


# ── brief derives from the completed detailed (mode-A) ─────────────────────────


@pytest.mark.anyio
async def test_brief_derives_from_completed_detailed(db_session: AsyncSession):
    # settings.ENABLE_DETAILED_SUMMARY defaults true → brief-from-detailed mode.
    factory = _session_factory(db_session)
    transcript, jobs = await _make_detailed_job(
        db_session, factory, ["First topic here.", "Second topic here.", "Third topic here."]
    )
    # Detailed first (map-reduce), then the brief derives from it.
    await generate_detailed_summary_async(
        jobs["generate_detailed_summary"], gateway=_gateway(factory), session_factory=factory
    )
    await generate_brief_summary_async(
        jobs["generate_brief_summary"], gateway=_gateway(factory), session_factory=factory
    )

    detailed = await _summary(factory, transcript.id, "detailed_study")
    brief = await _summary(factory, transcript.id, "brief")
    assert brief.generation_strategy == "derived_from_detailed"
    assert brief.generation_metadata["sourceDetailedSummaryId"] == str(detailed.id)
    assert brief.truncated is False  # inherited from the full-coverage detailed
    assert brief.backend_used == "cerebras"
    # The brief ran through the brief_from_detailed gateway feature — NOT the transcript-based summary_brief.
    async with factory() as session:
        brief_log = await session.get(AIRequestLog, brief.ai_request_log_id)
    assert brief_log.feature == "brief_from_detailed"


@pytest.mark.anyio
async def test_brief_defers_when_no_completed_detailed_yet(db_session: AsyncSession):
    # Brief-from-detailed mode but the detailed has not completed: the brief claim DEFERS (no artifact, the
    # job stays queued, no attempt consumed) — the detailed-completion fork is the trigger.
    factory = _session_factory(db_session)
    transcript, jobs = await _make_detailed_job(db_session, factory, ["Only topic here."])
    await generate_brief_summary_async(
        jobs["generate_brief_summary"], gateway=_gateway(factory), session_factory=factory
    )
    async with factory() as session:
        briefs = (
            await session.execute(
                select(GeneratedLectureSummary).where(
                    GeneratedLectureSummary.transcript_id == transcript.id,
                    GeneratedLectureSummary.summary_type == "brief",
                )
            )
        ).scalars().all()
        brief_job = await session.get(IngestionJob, jobs["generate_brief_summary"])
    assert briefs == []  # deferred — no brief written
    assert brief_job.status == "queued"  # left queued, awaiting the detailed-completion fork
    assert brief_job.attempts == 0  # no attempt consumed by the defer


# ── §0.1 gating predicate (pure) — incl. the NEGATIVE assertion ────────────────


def _detailed(strategy: str, truncated: bool, summary_type: str = "detailed_study"):
    # In-memory model object (not flushed) — the predicate only reads these three fields.
    return GeneratedLectureSummary(
        summary_type=summary_type, generation_strategy=strategy, truncated=truncated
    )


def test_full_coverage_predicate_truth_table():
    assert is_full_coverage_detailed(_detailed("map_reduce", False)) is True
    # NEGATIVE assertions (the discipline the developer named — a truncated/non-map_reduce row is NOT eligible):
    assert is_full_coverage_detailed(_detailed("map_reduce", True)) is False  # truncated map_reduce
    assert is_full_coverage_detailed(_detailed("truncated_fallback", False)) is False
    assert is_full_coverage_detailed(_detailed("single_call", True)) is False
    assert is_full_coverage_detailed(_detailed("single_call", False)) is False  # not map_reduce
    assert is_full_coverage_detailed(_detailed("map_reduce", False, summary_type="brief")) is False
    assert is_full_coverage_detailed(None) is False


# ── backfill (built, not run) ──────────────────────────────────────────────────


async def _persist_detailed(factory, transcript, *, strategy, truncated):
    """Persist a detailed summary row (+ its AIRequestLog) with a given strategy/truncated state."""
    async with factory() as session:
        async with session.begin():
            log = AIRequestLog(
                ingestion_job_id=None,
                feature="summary_detailed",
                model_id="m",
                prompt_version="v1",
                prompt_content_hash="pch",
                rendered_prompt_hash="rph",
                input_content_hash="ich",
                status="succeeded",
            )
            # A COMPLETED detailed job under the CANONICAL idempotency_key — so the backfill's
            # _ensure_summary_job finds THIS completed job and must force-requeue it (exercising the real
            # completed-job path). on_conflict-safe + reuse so it composes with a transcript that already
            # has a detailed job (e.g. from _make_detailed_job).
            await session.execute(
                pg_insert(IngestionJob)
                .values(
                    id=uuid7(),
                    transcript_id=transcript.id,
                    job_type="generate_detailed_summary",
                    status="completed",
                    idempotency_key=f"{transcript.id}:generate_detailed_summary:{transcript.checksum}",
                )
                .on_conflict_do_nothing(index_elements=["idempotency_key"])
            )
            job = (
                await session.execute(
                    select(IngestionJob).where(
                        IngestionJob.transcript_id == transcript.id,
                        IngestionJob.job_type == "generate_detailed_summary",
                    )
                )
            ).scalar_one()
            job.status = "completed"
            await session.flush()
            log.ingestion_job_id = job.id
            session.add(log)
            await session.flush()
            session.add(
                GeneratedLectureSummary(
                    transcript_id=transcript.id,
                    module_section_id=transcript.module_section_id,
                    summary_type="detailed_study",
                    content_json={"overview": "o"},
                    content_schema_version="detailed-v1",
                    model_id="m",
                    prompt_version="v1",
                    prompt_content_hash="pch",
                    backend_used="nvidia",
                    source_transcript_checksum=transcript.checksum,
                    input_hash=f"ih-{uuid7()}",
                    ai_request_log_id=log.id,
                    generation_strategy=strategy,
                    truncated=truncated,
                )
            )


async def _activate(factory, transcript):
    async with factory() as session:
        async with session.begin():
            row = await session.get(Transcript, transcript.id)
            row.lifecycle_state = "active"


@pytest.mark.anyio
async def test_backfill_selects_stale_and_dry_run_enqueues_nothing(db_session: AsyncSession):
    factory = _session_factory(db_session)
    stale_t, _ = await _create_parsed_transcript(db_session, texts=["stale lecture body."])
    await _activate(factory, stale_t)
    await _persist_detailed(factory, stale_t, strategy="single_call", truncated=True)
    fresh_t, _ = await _create_parsed_transcript(db_session, texts=["fresh lecture body."])
    await _activate(factory, fresh_t)
    await _persist_detailed(factory, fresh_t, strategy="map_reduce", truncated=False)

    dry = await backfill_stale_detailed_summaries(factory, dry_run=True)
    assert stale_t.id in dry.selected
    assert fresh_t.id not in dry.selected  # idempotent: full-coverage is never selected
    assert dry.enqueued == []  # dry-run enqueues nothing

    run = await backfill_stale_detailed_summaries(factory, dry_run=False)
    assert [tid for tid, _ in run.enqueued] == [str(stale_t.id)]
    async with factory() as session:
        job = (
            await session.execute(
                select(IngestionJob).where(
                    IngestionJob.transcript_id == stale_t.id,
                    IngestionJob.job_type == "generate_detailed_summary",
                    IngestionJob.status == "queued",
                )
            )
        ).scalar_one()
    assert job is not None  # the detailed job was reset to queued for regeneration


@pytest.mark.anyio
async def test_backfill_honors_cap(db_session: AsyncSession):
    factory = _session_factory(db_session)
    for i in range(3):
        t, _ = await _create_parsed_transcript(db_session, texts=[f"stale {i} body."])
        await _activate(factory, t)
        await _persist_detailed(factory, t, strategy="truncated_fallback", truncated=True)

    report = await backfill_stale_detailed_summaries(factory, dry_run=True, cap=2)
    assert len(report.selected) == 2
    assert report.capped is True


# ── stale-write fences (§6.1) ──────────────────────────────────────────────────


@pytest.mark.anyio
async def test_brief_claim_fences_on_active_checksum_mismatch(db_session: AsyncSession):
    # A detailed exists but its source checksum does not match the transcript's CURRENT checksum (a
    # replacement). The brief-claim must DEFER, never staple a stale detailed's brief onto the transcript.
    factory = _session_factory(db_session)
    transcript, jobs = await _make_detailed_job(db_session, factory, ["topic body here."])
    await _persist_detailed(factory, transcript, strategy="map_reduce", truncated=False)
    # Mutate the transcript checksum so the persisted detailed no longer matches the active transcript.
    async with factory() as session:
        async with session.begin():
            row = await session.get(Transcript, transcript.id)
            row.checksum = "f" * 64  # a different (valid lowercase-hex) checksum — as if replaced

    await generate_brief_summary_async(
        jobs["generate_brief_summary"], gateway=_gateway(factory), session_factory=factory
    )
    async with factory() as session:
        briefs = (
            await session.execute(
                select(GeneratedLectureSummary).where(
                    GeneratedLectureSummary.transcript_id == transcript.id,
                    GeneratedLectureSummary.summary_type == "brief",
                )
            )
        ).scalars().all()
    assert briefs == []  # fenced: no brief stapled onto the checksum-mismatched (replaced) transcript


@pytest.mark.anyio
async def test_map_reduce_fences_on_mid_flight_supersede(db_session: AsyncSession, monkeypatch):
    monkeypatch.setenv("LLM_SUMMARY_MAP_UNIT_CHAR_BUDGET", "20")
    factory = _session_factory(db_session)
    transcript, _ = await _create_parsed_transcript(
        db_session, texts=["Alpha body text.", "Beta body text.", "Gamma body text."]
    )
    # Supersede the transcript, then run the engine directly → it must abort clean (no partials written).
    # superseded_at is set to satisfy ck_transcripts_superseded_has_ts.
    async with factory() as session:
        async with session.begin():
            row = await session.get(Transcript, transcript.id)
            row.lifecycle_state = "superseded"
            row.superseded_at = datetime.now(UTC)

    runner = MapReduceRunner(
        factory,
        _gateway(factory),
        ingestion_job_id=uuid7(),
        transcript_id=transcript.id,
        section_type="lecture",
        source_transcript_checksum=transcript.checksum,
        attempt_number=1,
    )
    segments = [SegmentText(segment_id=uuid7(), text=t) for t in ("Alpha body text.", "Beta body text.")]
    with pytest.raises(MapReduceFenced):
        await runner.run(segments, "Alpha body text. Beta body text.")
    async with factory() as session:
        units = (
            await session.execute(
                select(MapUnitSummary).where(MapUnitSummary.transcript_id == transcript.id)
            )
        ).scalars().all()
    assert units == []  # no stale partial written for a superseded transcript


# ── AIRequestLog chain helper ──────────────────────────────────────────────────


@pytest.mark.anyio
async def test_ai_request_log_chain_correlates_map_reduce_by_job(db_session: AsyncSession, monkeypatch):
    monkeypatch.setenv("LLM_SUMMARY_MAP_UNIT_CHAR_BUDGET", "20")  # several map units
    factory = _session_factory(db_session)
    transcript, jobs = await _make_detailed_job(
        db_session, factory, ["Alpha topic body.", "Beta topic body.", "Gamma topic body."]
    )
    detailed_id = jobs["generate_detailed_summary"]
    await generate_detailed_summary_async(detailed_id, gateway=_gateway(factory), session_factory=factory)

    async with factory() as session:
        chain = await get_ai_request_log_chain(session, ingestion_job_id=detailed_id)
    features = [row.feature for row in chain]
    assert features.count("detailed_summary_map") >= 2  # one per map unit
    assert "detailed_summary_reduce" in features
    assert all(row.status == "succeeded" for row in chain)
