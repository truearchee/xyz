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
    try_activate_pending_transcript,
)
from app.domains.transcripts.summary_eligibility import (
    get_activation_ready_summaries,
    is_summary_eligible,
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
    prompt_version: str = "v1",
    source_checksum: str | None = None,
) -> GeneratedLectureSummary:
    log = AIRequestLog(
        ingestion_job_id=job.id,
        feature=feature,
        model_id="m",
        prompt_version=prompt_version,
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
        prompt_version=prompt_version,
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
    prompt_version: str = "v1",
    summary_checksum: str | None = None,
) -> None:
    """Build the end-state that makes overall_state == 'summarized' (embedded chunk + 3 done jobs +
    brief & detailed summary rows)."""
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
        prompt_version=prompt_version,
        source_checksum=summary_checksum,
    )
    await _create_summary_row(
        session,
        transcript,
        summary_type="detailed_study",
        feature="summary_detailed",
        job=detailed_job,
        prompt_version=prompt_version,
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
