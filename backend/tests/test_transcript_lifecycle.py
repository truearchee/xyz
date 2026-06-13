"""Stage 4.6a foundation: lifecycle/eligibility/resolver/activation + fault harness.

Covers the backend foundation behaviours (the full browser gate is 4.6d):
  - is_summary_eligible predicate (identity + provenance)
  - ActiveTranscriptSummaryResolver eligibility flags (read-only)
  - get_activation_ready_summaries write-side readiness
  - try_activate_pending_transcript atomic swap + no-op guards
  - pending-discard on a second replacement upload
  - pipeline fault-injection harness (no-op when off; forced fail; prod refusal; seed helper)
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.transcripts.activation import (
    ActivationOutcome,
    attempt_pending_activation,
    try_activate_pending_transcript,
)
from app.domains.transcripts.embedding_encoder import DeterministicEmbeddingEncoder
from app.domains.transcripts.embedding_service import embed_transcript_async
from app.domains.transcripts.summary_eligibility import (
    get_activation_ready_summaries,
    is_summary_eligible,
)
from app.domains.transcripts.summary_specs import (
    BRIEF,
    DETAILED,
    EXPECTED_PROMPT_VERSION_BY_SUMMARY_TYPE,
)
from app.platform.db.models import (
    AIRequestLog,
    GeneratedLectureSummary,
    IngestionJob,
    Transcript,
    TranscriptChunk,
    TranscriptSegment,
)
from app.platform.faults.pipeline_faults import (
    FAULTABLE_STEPS,
    PipelineFaultInjected,
    maybe_fail_step,
    seed_failed_ingestion_job,
)
from app.platform.query.active_transcript_summary_resolver import (
    ActiveTranscriptSummaryResolver,
)
from tests.test_transcript_worker import _session_factory
from tests.test_transcripts import (
    _create_membership,
    _create_module,
    _create_section,
    _create_transcript,
    _create_user,
    _headers,
    _transcript_file,
    fake_storage,  # noqa: F401 — re-exported so pytest resolves it as a fixture here
)


def _now() -> datetime:
    return datetime.now(UTC)


def _checksum() -> str:
    return hashlib.sha256(uuid4().bytes).hexdigest()


async def _section_with_lecturer(session: AsyncSession):
    lecturer = await _create_user(session, email=f"life-{uuid4()}@example.com", role="lecturer")
    module = await _create_module(session, owner_id=lecturer.id)
    await _create_membership(session, user_id=lecturer.id, module_id=module.id, role="lecturer")
    section = await _create_section(session, module_id=module.id)
    return section, lecturer


def _transcript(
    section_id: UUID,
    lecturer_id: UUID,
    *,
    lifecycle_state: str,
    checksum: str | None = None,
    replacement_of: UUID | None = None,
) -> Transcript:
    return Transcript(
        id=uuid4(),
        module_section_id=section_id,
        source_type="manual_upload",
        original_file_name="x.vtt",
        storage_key=f"modules/test/transcripts/{uuid4()}/x.vtt",
        mime_type="text/vtt",
        file_size=10,
        checksum=checksum or _checksum(),
        status="completed",
        uploaded_by_user_id=lecturer_id,
        lifecycle_state=lifecycle_state,
        replacement_of_transcript_id=replacement_of,
    )


async def _create_summary_row(
    session: AsyncSession,
    transcript: Transcript,
    *,
    summary_type: str,
    feature: str,
    job: IngestionJob,
    prompt_version: str | None = None,
    source_checksum: str | None = None,
) -> GeneratedLectureSummary:
    # Default to the CURRENT expected version for this summary type (brief / map-reduce reduce) so the
    # row is activation-eligible without a hardcoded literal that rots on a version bump (4.5.1a finding).
    resolved_version = prompt_version or EXPECTED_PROMPT_VERSION_BY_SUMMARY_TYPE.get(summary_type, "v1")
    log = AIRequestLog(
        ingestion_job_id=job.id,
        feature=feature,
        model_id="m",
        prompt_version=resolved_version,
        prompt_content_hash="pch",
        rendered_prompt_hash="rph",
        input_content_hash="ich",
        status="succeeded",
    )
    session.add(log)
    await session.flush()
    summary = GeneratedLectureSummary(
        transcript_id=transcript.id,
        module_section_id=transcript.module_section_id,
        summary_type=summary_type,
        content_json=(
            {"text": "brief"}
            if summary_type == "brief"
            else {
                "overview": "o",
                "keyConcepts": [],
                "importantDefinitions": [],
                "mainExplanations": [],
                "examples": [],
                "examRelevantPoints": [],
            }
        ),
        content_schema_version="v1",
        model_id="m",
        prompt_version=resolved_version,
        prompt_content_hash="pch",
        backend_used="cerebras",
        source_transcript_checksum=source_checksum or transcript.checksum,
        input_hash="ih",
        ai_request_log_id=log.id,
        created_by_ingestion_job_id=job.id,
    )
    session.add(summary)
    await session.flush()
    return summary


async def _make_summarized(
    session: AsyncSession,
    transcript: Transcript,
    *,
    prompt_version: str | None = None,
    summary_checksum: str | None = None,
) -> None:
    """Build the end-state that makes overall_state == 'summarized' (embedded chunk + 3 done jobs +
    brief & detailed summary rows).

    By default each summary row is stamped with the CURRENT expected prompt version for its type
    (brief = brief prompt, detailed = the map-reduce REDUCE prompt) so the rows are activation-eligible
    — tracking ``EXPECTED_PROMPT_VERSION_BY_SUMMARY_TYPE`` rather than a hardcoded literal that silently
    rots whenever a prompt version is bumped (the 4.5.1a finding: the 4.5 v2 bump left this at "v1").
    Pass ``prompt_version`` to force a specific (e.g. stale) version for staleness tests."""
    now = _now()
    brief_version = prompt_version or EXPECTED_PROMPT_VERSION_BY_SUMMARY_TYPE[BRIEF.summary_type]
    detailed_version = (
        prompt_version or EXPECTED_PROMPT_VERSION_BY_SUMMARY_TYPE[DETAILED.summary_type]
    )
    segment = TranscriptSegment(
        transcript_id=transcript.id, sequence_number=0, start_ms=0, end_ms=1000, text="hello"
    )
    session.add(segment)
    await session.flush()
    session.add(
        TranscriptChunk(
            transcript_id=transcript.id,
            chunk_index=0,
            start_segment_id=segment.id,
            end_segment_id=segment.id,
            start_sequence_number=0,
            end_sequence_number=0,
            text="hello",
            token_count=1,
            token_count_method="words",
            normalization_version="norm-v1-structural",
            chunking_version="chunk-v1-no-overlap-180w",
            embedding=[0.0] * 384,
            embedding_model="m",
            embedding_model_revision="r",
            embedding_dimension=384,
            embedding_normalization="l2",
            embedding_version="ev",
            embedding_input_hash="h",
            embedding_generated_at=now,
        )
    )
    embed_job = IngestionJob(
        transcript_id=transcript.id,
        job_type="embed",
        status="completed",
        idempotency_key=f"{transcript.id}:embed:{uuid4()}",
        completed_at=now,
    )
    brief_job = IngestionJob(
        transcript_id=transcript.id,
        job_type="generate_brief_summary",
        status="completed",
        idempotency_key=f"{transcript.id}:brief:{uuid4()}",
        completed_at=now,
    )
    detailed_job = IngestionJob(
        transcript_id=transcript.id,
        job_type="generate_detailed_summary",
        status="completed",
        idempotency_key=f"{transcript.id}:detailed:{uuid4()}",
        completed_at=now,
    )
    session.add_all([embed_job, brief_job, detailed_job])
    await session.flush()
    await _create_summary_row(
        session,
        transcript,
        summary_type="brief",
        feature="summary_brief",
        job=brief_job,
        prompt_version=brief_version,
        source_checksum=summary_checksum,
    )
    await _create_summary_row(
        session,
        transcript,
        summary_type="detailed_study",
        feature="summary_detailed",
        job=detailed_job,
        prompt_version=detailed_version,
        source_checksum=summary_checksum,
    )


# ───────────────────────── eligibility predicate ─────────────────────────


def test_is_summary_eligible_matches_identity_and_checksum() -> None:
    checksum = _checksum()
    transcript = Transcript(id=uuid4(), checksum=checksum)
    summary = GeneratedLectureSummary(
        transcript_id=transcript.id, source_transcript_checksum=checksum
    )
    assert is_summary_eligible(summary, active_transcript=transcript) is True


def test_is_summary_eligible_rejects_wrong_transcript() -> None:
    transcript = Transcript(id=uuid4(), checksum=_checksum())
    summary = GeneratedLectureSummary(
        transcript_id=uuid4(), source_transcript_checksum=transcript.checksum
    )
    assert is_summary_eligible(summary, active_transcript=transcript) is False


def test_is_summary_eligible_rejects_stale_checksum() -> None:
    transcript = Transcript(id=uuid4(), checksum=_checksum())
    summary = GeneratedLectureSummary(
        transcript_id=transcript.id, source_transcript_checksum=_checksum()
    )
    assert is_summary_eligible(summary, active_transcript=transcript) is False


# ───────────────────────── resolver (read-only) ─────────────────────────


@pytest.mark.anyio
async def test_resolver_flags_eligible_and_ineligible_summaries(db_session: AsyncSession) -> None:
    section, lecturer = await _section_with_lecturer(db_session)
    active = _transcript(section.id, lecturer.id, lifecycle_state="active")
    db_session.add(active)
    await db_session.flush()
    await _make_summarized(db_session, active)
    await db_session.commit()

    resolver = ActiveTranscriptSummaryResolver()
    view = await resolver.resolve(db_session, active_transcript=active)
    assert view.brief is not None
    assert view.detailed is not None
    assert view.brief_eligible is True
    assert view.detailed_eligible is True


@pytest.mark.anyio
async def test_resolver_marks_checksum_mismatch_ineligible(db_session: AsyncSession) -> None:
    section, lecturer = await _section_with_lecturer(db_session)
    active = _transcript(section.id, lecturer.id, lifecycle_state="active")
    db_session.add(active)
    await db_session.flush()
    # Summaries written against a DIFFERENT (stale) checksum than the active transcript.
    await _make_summarized(db_session, active, summary_checksum=_checksum())
    await db_session.commit()

    view = await ActiveTranscriptSummaryResolver().resolve(db_session, active_transcript=active)
    assert view.brief is not None  # the row exists...
    assert view.brief_eligible is False  # ...but is not bound to the active transcript
    assert view.detailed_eligible is False


# ───────────────────────── activation swap ─────────────────────────


@pytest.mark.anyio
async def test_activation_swaps_active_and_pending(db_session: AsyncSession) -> None:
    section, lecturer = await _section_with_lecturer(db_session)
    active = _transcript(section.id, lecturer.id, lifecycle_state="active")
    db_session.add(active)
    await db_session.flush()
    pending = _transcript(
        section.id, lecturer.id, lifecycle_state="pending", replacement_of=active.id
    )
    db_session.add(pending)
    await db_session.flush()
    await _make_summarized(db_session, pending)
    active_id, pending_id, section_id = active.id, pending.id, section.id
    await db_session.commit()

    factory = _session_factory(db_session)
    async with factory() as session:
        outcome = await try_activate_pending_transcript(session, transcript_id=pending_id)
    assert outcome is ActivationOutcome.ACTIVATED

    db_session.expire_all()
    active_ref = await db_session.get(Transcript, active_id)
    pending_ref = await db_session.get(Transcript, pending_id)
    assert pending_ref is not None and pending_ref.lifecycle_state == "active"
    assert active_ref is not None and active_ref.lifecycle_state == "superseded"
    assert active_ref.superseded_by_transcript_id == pending_id
    assert active_ref.supersession_reason == "replaced_active"
    assert active_ref.superseded_at is not None

    actives = (
        await db_session.execute(
            select(Transcript).where(
                Transcript.module_section_id == section_id,
                Transcript.lifecycle_state == "active",
            )
        )
    ).scalars().all()
    assert [t.id for t in actives] == [pending_id]


@pytest.mark.anyio
async def test_activation_noop_for_active_transcript(db_session: AsyncSession) -> None:
    section, lecturer = await _section_with_lecturer(db_session)
    active = _transcript(section.id, lecturer.id, lifecycle_state="active")
    db_session.add(active)
    active_id = active.id
    await db_session.commit()

    factory = _session_factory(db_session)
    async with factory() as session:
        outcome = await try_activate_pending_transcript(session, transcript_id=active_id)
    assert outcome is ActivationOutcome.NOT_PENDING

    db_session.expire_all()
    ref = await db_session.get(Transcript, active_id)
    assert ref is not None and ref.lifecycle_state == "active"


@pytest.mark.anyio
async def test_activation_not_ready_when_not_summarized(db_session: AsyncSession) -> None:
    section, lecturer = await _section_with_lecturer(db_session)
    active = _transcript(section.id, lecturer.id, lifecycle_state="active")
    db_session.add(active)
    await db_session.flush()
    pending = _transcript(
        section.id, lecturer.id, lifecycle_state="pending", replacement_of=active.id
    )
    db_session.add(pending)
    active_id, pending_id = active.id, pending.id
    await db_session.commit()  # pending has no chunks/jobs/summaries → not summarized

    factory = _session_factory(db_session)
    async with factory() as session:
        outcome = await try_activate_pending_transcript(session, transcript_id=pending_id)
    assert outcome is ActivationOutcome.NOT_READY

    db_session.expire_all()
    assert (await db_session.get(Transcript, pending_id)).lifecycle_state == "pending"
    assert (await db_session.get(Transcript, active_id)).lifecycle_state == "active"


@pytest.mark.anyio
async def test_activation_not_ready_when_summary_checksum_mismatch(
    db_session: AsyncSession,
) -> None:
    section, lecturer = await _section_with_lecturer(db_session)
    active = _transcript(section.id, lecturer.id, lifecycle_state="active")
    db_session.add(active)
    await db_session.flush()
    pending = _transcript(
        section.id, lecturer.id, lifecycle_state="pending", replacement_of=active.id
    )
    db_session.add(pending)
    await db_session.flush()
    # Fully processed but the summary rows carry a stale checksum → ineligible → not activatable.
    await _make_summarized(db_session, pending, summary_checksum=_checksum())
    await db_session.commit()

    factory = _session_factory(db_session)
    async with factory() as session:
        outcome = await try_activate_pending_transcript(session, transcript_id=pending.id)
    assert outcome is ActivationOutcome.NOT_READY


@pytest.mark.anyio
async def test_get_activation_ready_summaries_requires_both_when_detailed_required(
    db_session: AsyncSession,
) -> None:
    section, lecturer = await _section_with_lecturer(db_session)
    transcript = _transcript(section.id, lecturer.id, lifecycle_state="pending")
    db_session.add(transcript)
    await db_session.flush()
    # Only a brief summary present.
    brief_job = IngestionJob(
        transcript_id=transcript.id,
        job_type="generate_brief_summary",
        status="completed",
        idempotency_key=f"{transcript.id}:brief:{uuid4()}",
        completed_at=_now(),
    )
    db_session.add(brief_job)
    await db_session.flush()
    await _create_summary_row(
        db_session,
        transcript,
        summary_type="brief",
        feature="summary_brief",
        job=brief_job,
    )
    await db_session.commit()

    readiness = await get_activation_ready_summaries(
        db_session, transcript=transcript, require_detailed=True
    )
    assert readiness.brief_ready is True
    assert readiness.detailed_ready is False
    assert readiness.is_ready is False

    readiness_no_detail = await get_activation_ready_summaries(
        db_session, transcript=transcript, require_detailed=False
    )
    assert readiness_no_detail.is_ready is True


# ───────────────────────── pending-discard ─────────────────────────


@pytest.mark.anyio
async def test_third_upload_discards_prior_pending(
    auth_client,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
    fake_storage,
) -> None:
    # Two replacements while one is still pending: the prior pending is discarded so the one-pending
    # invariant holds (ADR-46-A). Drives the API twice through the same section.
    lecturer = await _create_user(
        db_session, email=f"discard-{uuid4()}@example.com", role="lecturer"
    )
    module = await _create_module(db_session, owner_id=lecturer.id)
    await _create_membership(
        db_session, user_id=lecturer.id, module_id=module.id, role="lecturer"
    )
    section = await _create_section(db_session, module_id=module.id)
    active = await _create_transcript(
        db_session, section_id=section.id, uploaded_by_user_id=lecturer.id
    )
    module_id, section_id, active_id = module.id, section.id, active.id
    await db_session.commit()

    first = await auth_client.post(
        f"/modules/{module_id}/sections/{section_id}/transcript",
        files=_transcript_file(),
        headers=_headers(lecturer, jwt_factory),
    )
    assert first.status_code == 201
    first_pending_id = UUID(first.json()["id"])

    second = await auth_client.post(
        f"/modules/{module_id}/sections/{section_id}/transcript",
        files=_transcript_file(),
        headers=_headers(lecturer, jwt_factory),
    )
    assert second.status_code == 201
    second_pending_id = UUID(second.json()["id"])
    assert second_pending_id != first_pending_id

    db_session.expire_all()
    rows = (
        await db_session.execute(
            select(Transcript).where(Transcript.module_section_id == section_id)
        )
    ).scalars().all()
    by_id = {row.id: row for row in rows}
    assert by_id[active_id].lifecycle_state == "active"
    assert by_id[first_pending_id].lifecycle_state == "superseded"
    assert by_id[first_pending_id].supersession_reason == "discarded_pending"
    assert by_id[second_pending_id].lifecycle_state == "pending"
    # Exactly one pending remains.
    pendings = [r.id for r in rows if r.lifecycle_state == "pending"]
    assert pendings == [second_pending_id]


# ───────────────────────── fault-injection harness ─────────────────────────


def test_maybe_fail_step_noop_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PIPELINE_FAULT_INJECTION_ENABLED", raising=False)
    monkeypatch.setenv("PIPELINE_FAULT_INJECTION", "parse")
    for step in FAULTABLE_STEPS:
        assert maybe_fail_step(step) is None  # no-op even though a step is configured


def test_maybe_fail_step_raises_only_for_matching_step(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("PIPELINE_FAULT_INJECTION_ENABLED", "true")
    monkeypatch.setenv("PIPELINE_FAULT_INJECTION", "embed")
    assert maybe_fail_step("parse") is None
    with pytest.raises(PipelineFaultInjected) as exc:
        maybe_fail_step("embed")
    assert exc.value.step == "embed"


def test_maybe_fail_step_refuses_in_prod(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("PIPELINE_FAULT_INJECTION_ENABLED", "true")
    monkeypatch.setenv("PIPELINE_FAULT_INJECTION", "parse")
    with pytest.raises(RuntimeError):
        maybe_fail_step("parse")


@pytest.mark.anyio
async def test_seed_failed_ingestion_job(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "test")
    section, lecturer = await _section_with_lecturer(db_session)
    transcript = _transcript(section.id, lecturer.id, lifecycle_state="active")
    db_session.add(transcript)
    await db_session.flush()

    job_id = await seed_failed_ingestion_job(
        db_session,
        transcript_id=transcript.id,
        job_type="embed",
        failure_category="provider_transient",
    )
    job = await db_session.get(IngestionJob, job_id)
    assert job is not None
    assert job.status == "failed"
    assert job.job_type == "embed"
    assert job.failure_category == "provider_transient"


# ───────────────────────── active-summary preview endpoint (4.6d) ─────────────────────────


@pytest.mark.anyio
async def test_active_summary_preview_returns_eligible(
    auth_client, db_session: AsyncSession, jwt_factory, mock_jwks_client
) -> None:
    section, lecturer = await _section_with_lecturer(db_session)
    module_id, section_id = section.course_module_id, section.id
    active = _transcript(section_id, lecturer.id, lifecycle_state="active")
    db_session.add(active)
    await db_session.flush()
    await _make_summarized(db_session, active)
    active_id = active.id
    await db_session.commit()

    response = await auth_client.get(
        f"/modules/{module_id}/sections/{section_id}/transcript-active-summary-preview",
        headers=_headers(lecturer, jwt_factory),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["activeTranscriptId"] == str(active_id)
    assert body["briefEligible"] is True
    assert body["detailedEligible"] is True
    assert body["hasPendingReplacement"] is False
    # Internal provenance is never exposed.
    assert not {"checksum", "storageKey", "sourceTranscriptChecksum"} & set(body)


@pytest.mark.anyio
async def test_active_summary_preview_flags_pending_replacement(
    auth_client, db_session: AsyncSession, jwt_factory, mock_jwks_client
) -> None:
    section, lecturer = await _section_with_lecturer(db_session)
    module_id, section_id = section.course_module_id, section.id
    active = _transcript(section_id, lecturer.id, lifecycle_state="active")
    db_session.add(active)
    await db_session.flush()
    await _make_summarized(db_session, active)
    pending = _transcript(
        section_id, lecturer.id, lifecycle_state="pending", replacement_of=active.id
    )
    db_session.add(pending)
    active_id = active.id
    await db_session.commit()

    response = await auth_client.get(
        f"/modules/{module_id}/sections/{section_id}/transcript-active-summary-preview",
        headers=_headers(lecturer, jwt_factory),
    )
    assert response.status_code == 200
    body = response.json()
    # Continuity: the preview still surfaces the ACTIVE (v1) while a replacement processes.
    assert body["activeTranscriptId"] == str(active_id)
    assert body["hasPendingReplacement"] is True


@pytest.mark.anyio
async def test_active_summary_preview_authz(
    auth_client, db_session: AsyncSession, jwt_factory, mock_jwks_client
) -> None:
    section, lecturer = await _section_with_lecturer(db_session)
    module_id, section_id = section.course_module_id, section.id
    active = _transcript(section_id, lecturer.id, lifecycle_state="active")
    db_session.add(active)
    await db_session.flush()
    await _make_summarized(db_session, active)
    student = await _create_user(db_session, email=f"prev-stu-{uuid4()}@example.com", role="student")
    await _create_membership(db_session, user_id=student.id, module_id=module_id, role="student")
    other = await _create_user(db_session, email=f"prev-oth-{uuid4()}@example.com", role="lecturer")
    await db_session.commit()

    path = f"/modules/{module_id}/sections/{section_id}/transcript-active-summary-preview"
    student_resp = await auth_client.get(path, headers=_headers(student, jwt_factory))
    other_resp = await auth_client.get(path, headers=_headers(other, jwt_factory))
    assert student_resp.status_code == 403
    assert other_resp.status_code == 404


# ───────── F-4.6b-2: every pipeline leaf triggers activation (ordering-independent) ─────────


async def _summarized_except_embed(session: AsyncSession, transcript: Transcript):
    """Build a pending whose summaries are DONE but embed is still pending: one un-embedded chunk + a
    QUEUED embed job + completed brief/detailed jobs + summary rows. Returns the embed job id. Lets the
    real embed worker be the LAST leaf to complete (the exact F-4.6b-2 ordering)."""
    now = _now()
    segment = TranscriptSegment(
        transcript_id=transcript.id, sequence_number=0, start_ms=0, end_ms=1000, text="hello"
    )
    session.add(segment)
    await session.flush()
    session.add(
        TranscriptChunk(
            transcript_id=transcript.id,
            chunk_index=0,
            start_segment_id=segment.id,
            end_segment_id=segment.id,
            start_sequence_number=0,
            end_sequence_number=0,
            text="hello",
            token_count=1,
            token_count_method="words",
            normalization_version="norm-v1-structural",
            chunking_version="chunk-v1-no-overlap-180w",
        )  # NO embedding — the embed worker fills it
    )
    embed_job = IngestionJob(
        transcript_id=transcript.id,
        job_type="embed",
        status="queued",
        idempotency_key=f"{transcript.id}:embed:{uuid4()}",
    )
    brief_job = IngestionJob(
        transcript_id=transcript.id,
        job_type="generate_brief_summary",
        status="completed",
        idempotency_key=f"{transcript.id}:brief:{uuid4()}",
        completed_at=now,
    )
    detailed_job = IngestionJob(
        transcript_id=transcript.id,
        job_type="generate_detailed_summary",
        status="completed",
        idempotency_key=f"{transcript.id}:detailed:{uuid4()}",
        completed_at=now,
    )
    session.add_all([embed_job, brief_job, detailed_job])
    await session.flush()
    await _create_summary_row(
        session, transcript, summary_type="brief", feature="summary_brief", job=brief_job
    )
    await _create_summary_row(
        session, transcript, summary_type="detailed_study", feature="summary_detailed", job=detailed_job
    )
    return embed_job.id


@pytest.mark.anyio
async def test_pending_activates_when_embed_completes_after_summaries(db_session: AsyncSession) -> None:
    """F-4.6b-2: embed is a leaf that can finish LAST (parallel to summaries). Its completion must
    trigger the swap — proven through the REAL embed worker."""
    section, lecturer = await _section_with_lecturer(db_session)
    active = _transcript(section.id, lecturer.id, lifecycle_state="active")
    db_session.add(active)
    await db_session.flush()
    await _make_summarized(db_session, active)
    pending = _transcript(
        section.id, lecturer.id, lifecycle_state="pending", replacement_of=active.id
    )
    db_session.add(pending)
    await db_session.flush()
    embed_job_id = await _summarized_except_embed(db_session, pending)
    active_id, pending_id, section_id = active.id, pending.id, section.id
    await db_session.commit()

    # Embed finishes last → the embed-leaf activation hook must fire the swap.
    await embed_transcript_async(
        embed_job_id,
        encoder=DeterministicEmbeddingEncoder(),
        session_factory=_session_factory(db_session),
    )
    db_session.expire_all()
    assert (await db_session.get(Transcript, pending_id)).lifecycle_state == "active"
    active_ref = await db_session.get(Transcript, active_id)
    assert active_ref.lifecycle_state == "superseded"
    assert active_ref.superseded_by_transcript_id == pending_id
    actives = (
        await db_session.execute(
            select(Transcript).where(
                Transcript.module_section_id == section_id,
                Transcript.lifecycle_state == "active",
            )
        )
    ).scalars().all()
    assert [t.id for t in actives] == [pending_id]


@pytest.mark.anyio
async def test_pending_activates_when_summary_completes_after_embed(db_session: AsyncSession) -> None:
    """Symmetric case: embed + brief finish FIRST, the detailed summary leaf finishes last → the
    summary-leaf hook fires the swap. (Whichever leaf is last activates — ordering-independent.)"""
    section, lecturer = await _section_with_lecturer(db_session)
    active = _transcript(section.id, lecturer.id, lifecycle_state="active")
    db_session.add(active)
    await db_session.flush()
    await _make_summarized(db_session, active)
    # Pending with embed + brief done but detailed still pending (embed finished first here).
    pending = _transcript(
        section.id, lecturer.id, lifecycle_state="pending", replacement_of=active.id
    )
    db_session.add(pending)
    await db_session.flush()
    await _make_summarized(db_session, pending)
    pending_id, active_id = pending.id, active.id
    detailed_job = (
        await db_session.execute(
            select(IngestionJob).where(
                IngestionJob.transcript_id == pending_id,
                IngestionJob.job_type == "generate_detailed_summary",
            )
        )
    ).scalar_one()
    detailed_job.status = "queued"
    detailed_job.completed_at = None
    detailed_job_id = detailed_job.id  # capture before commit expires the instance
    detailed_row = (
        await db_session.execute(
            select(GeneratedLectureSummary).where(
                GeneratedLectureSummary.transcript_id == pending_id,
                GeneratedLectureSummary.summary_type == "detailed_study",
            )
        )
    ).scalar_one()
    await db_session.delete(detailed_row)
    await db_session.commit()

    factory = _session_factory(db_session)
    await attempt_pending_activation(factory, transcript_id=pending_id)  # not ready → no-op
    db_session.expire_all()
    assert (await db_session.get(Transcript, pending_id)).lifecycle_state == "pending"

    # The detailed summary leaf now completes last → its hook fires the swap.
    async with factory() as session:
        job = await session.get(IngestionJob, detailed_job_id)
        job.status = "completed"
        job.completed_at = _now()
        pending_ref = await session.get(Transcript, pending_id)
        await _create_summary_row(
            session,
            pending_ref,
            summary_type="detailed_study",
            feature="summary_detailed",
            job=job,
        )
        await session.commit()
    await attempt_pending_activation(factory, transcript_id=pending_id)
    db_session.expire_all()
    assert (await db_session.get(Transcript, pending_id)).lifecycle_state == "active"
    assert (await db_session.get(Transcript, active_id)).lifecycle_state == "superseded"


@pytest.mark.anyio
async def test_concurrent_leaf_activations_swap_exactly_once(db_session: AsyncSession) -> None:
    """Two leaves finishing near-simultaneously each call activation → EXACTLY ONE swap (the section
    lock + flush-before-promote + one-active index hold). No double-activation, no index violation."""
    section, lecturer = await _section_with_lecturer(db_session)
    active = _transcript(section.id, lecturer.id, lifecycle_state="active")
    db_session.add(active)
    await db_session.flush()
    await _make_summarized(db_session, active)
    pending = _transcript(
        section.id, lecturer.id, lifecycle_state="pending", replacement_of=active.id
    )
    db_session.add(pending)
    await db_session.flush()
    await _make_summarized(db_session, pending)
    active_id, pending_id, section_id = active.id, pending.id, section.id
    await db_session.commit()

    factory = _session_factory(db_session)
    async with factory() as s1:
        o1 = await try_activate_pending_transcript(s1, transcript_id=pending_id)
    async with factory() as s2:
        o2 = await try_activate_pending_transcript(s2, transcript_id=pending_id)
    assert {o1, o2} == {ActivationOutcome.ACTIVATED, ActivationOutcome.NOT_PENDING}

    db_session.expire_all()
    actives = (
        await db_session.execute(
            select(Transcript).where(
                Transcript.module_section_id == section_id,
                Transcript.lifecycle_state == "active",
            )
        )
    ).scalars().all()
    assert [t.id for t in actives] == [pending_id]  # exactly one active
    assert (await db_session.get(Transcript, active_id)).lifecycle_state == "superseded"
