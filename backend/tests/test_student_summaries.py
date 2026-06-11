"""Stage 4.7 — student-facing summary read boundary.

Unit tests pin the §6 precedence (esp. corruption ≠ supersession) and the §5 policy gates in isolation;
integration tests exercise every §5 row over the real HTTP surface + DB, prove the D/P/I 404 bodies are
byte-identical (S2), the raw-transcript sentinel never surfaces (G3b backend half), the response schema
cannot leak transcript/provenance/job internals (§8.3), and Cache-Control is no-store (§8.4).
"""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime
from uuid import UUID, uuid4

from httpx import AsyncClient
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.student_summaries import precedence
from app.domains.student_summaries.markdown import (
    brief_to_markdown,
    detailed_to_markdown,
    summary_to_markdown,
)
from app.domains.student_summaries.policy import (
    SECTION_NOT_FOUND,
    STUDENT_SUMMARY_FORBIDDEN,
    StudentSummaryAccessPolicy,
)
from app.domains.student_summaries.precedence import (
    GENERATING,
    NOT_APPLICABLE,
    READY,
    UNAVAILABLE,
    derive_section_summaries_state,
    derive_slot_state,
)
from app.platform.db.models import (
    AIRequestLog,
    AppUser,
    CourseMembership,
    CourseModule,
    GeneratedLectureSummary,
    IngestionJob,
    ModuleSection,
    SectionAsset,
    Transcript,
    TranscriptSegment,
)
from fastapi import HTTPException

pytestmark = pytest.mark.anyio

SENTINEL = "RAW_TRANSCRIPT_SENTINEL_DO_NOT_SURFACE_4_7"

# Fields any student-reachable summary/section response must NEVER serialize (§8.3).
FORBIDDEN_KEYS = {
    "transcriptId",
    "transcript_id",
    "ingestionJobId",
    "jobId",
    "errorMessage",
    "modelId",
    "modelName",
    "promptVersion",
    "tokenUsage",
    "sourceTranscriptChecksum",
    "checksum",
    "storageKey",
    "overallState",
    "steps",
    "aiRequestLogId",
}


def _checksum(seed: str | None = None) -> str:
    return hashlib.sha256((seed or str(uuid4())).encode()).hexdigest()


def _now() -> datetime:
    return datetime.now(UTC)


# --------------------------------------------------------------------------------------------------
# Unit — §6 precedence. The trickiest correctness point: corruption ≠ supersession (two separate tests).
# --------------------------------------------------------------------------------------------------
class _FakeTranscript:
    def __init__(self, *, id: UUID | None = None, checksum: str = "abc", status: str = "completed") -> None:
        self.id = id or uuid4()
        self.checksum = checksum
        self.status = status


class _FakeSummary:
    def __init__(self, *, transcript_id: UUID, checksum: str, content_json: dict) -> None:
        self.id = uuid4()
        self.transcript_id = transcript_id
        self.source_transcript_checksum = checksum
        self.content_json = content_json


def _brief_json(text: str = "the core ideas") -> dict:
    return {"text": text}


def test_precedence_not_applicable_for_assignment():
    res = derive_slot_state(
        section_type="assignment",
        summary_type="brief",
        active_transcript=None,
        summary_row=None,
        summary_step_status=None,
        overall_state=None,
    )
    assert res.state == NOT_APPLICABLE


def test_precedence_no_active_transcript_is_unavailable():
    res = derive_slot_state(
        section_type="lecture",
        summary_type="brief",
        active_transcript=None,
        summary_row=None,
        summary_step_status=None,
        overall_state=None,
    )
    assert res.state == UNAVAILABLE


def test_precedence_generated_row_matching_checksum_is_ready():
    active = _FakeTranscript(checksum="cs-1")
    row = _FakeSummary(transcript_id=active.id, checksum="cs-1", content_json=_brief_json())
    res = derive_slot_state(
        section_type="lecture",
        summary_type="brief",
        active_transcript=active,
        summary_row=row,
        summary_step_status="completed",
        overall_state="summarized",
    )
    assert res.state == READY


def test_precedence_corruption_tripwire_is_unavailable_and_logs(caplog):
    """CORRUPTION: a row for the ACTIVE transcript (id match) but checksum disagrees → UNAVAILABLE + log."""
    active = _FakeTranscript(checksum="cs-active")
    row = _FakeSummary(transcript_id=active.id, checksum="cs-DIFFERENT", content_json=_brief_json())
    with caplog.at_level(logging.ERROR, logger="app.domains.student_summaries.precedence"):
        res = derive_slot_state(
            section_type="lecture",
            summary_type="brief",
            active_transcript=active,
            summary_row=row,
            summary_step_status="completed",
            overall_state="summarized",
        )
    assert res.state == UNAVAILABLE
    assert any("corruption tripwire" in r.message for r in caplog.records), "corruption must LOG"


def test_precedence_supersession_is_generating_and_does_not_log_corruption(caplog):
    """SUPERSESSION: no row for the active transcript (mid-replacement) → GENERATING, NO corruption log.

    This is the distinct-from-corruption case. is_summary_eligible would be False for a superseded row
    too — but here there is simply NO row for the active transcript, so we must NOT emit a corruption
    signal and must fall through to GENERATING."""
    active = _FakeTranscript(checksum="cs-new")
    with caplog.at_level(logging.ERROR, logger="app.domains.student_summaries.precedence"):
        res = derive_slot_state(
            section_type="lecture",
            summary_type="brief",
            active_transcript=active,
            summary_row=None,  # the new active transcript has no summaries yet
            summary_step_status="queued",
            overall_state="summarizing",
        )
    assert res.state == GENERATING
    assert not any("corruption tripwire" in r.message for r in caplog.records), (
        "supersession must NOT emit the corruption signal"
    )


def test_precedence_blank_content_is_unavailable_and_logs(caplog):
    active = _FakeTranscript(checksum="cs-1")
    row = _FakeSummary(transcript_id=active.id, checksum="cs-1", content_json={"text": "   "})
    with caplog.at_level(logging.WARNING, logger="app.domains.student_summaries.precedence"):
        res = derive_slot_state(
            section_type="lecture",
            summary_type="brief",
            active_transcript=active,
            summary_row=row,
            summary_step_status="completed",
            overall_state="summarized",
        )
    assert res.state == UNAVAILABLE
    assert any("blank-content" in r.message for r in caplog.records)


def test_precedence_summary_step_failed_is_unavailable():
    active = _FakeTranscript()
    res = derive_slot_state(
        section_type="lecture",
        summary_type="brief",
        active_transcript=active,
        summary_row=None,
        summary_step_status="failed",
        overall_state="failed",
    )
    assert res.state == UNAVAILABLE


def test_precedence_summary_job_running_is_generating():
    active = _FakeTranscript()
    res = derive_slot_state(
        section_type="lecture",
        summary_type="detailed_study",
        active_transcript=active,
        summary_row=None,
        summary_step_status="running",
        overall_state="summarizing",
    )
    assert res.state == GENERATING


def test_precedence_completed_but_missing_is_unavailable_with_inconsistency(caplog):
    active = _FakeTranscript()
    with caplog.at_level(logging.ERROR, logger="app.domains.student_summaries.precedence"):
        res = derive_slot_state(
            section_type="lecture",
            summary_type="brief",
            active_transcript=active,
            summary_row=None,
            summary_step_status="completed",  # step says done but no success-only row
            overall_state="summarized",
        )
    assert res.state == UNAVAILABLE
    assert res.lecturer_inconsistency is True
    assert any("completed-but-missing" in r.message for r in caplog.records)


def test_precedence_upstream_terminally_failed_is_unavailable_not_forever_generating():
    """Upstream (e.g. embed) failed; summary step never started → UNAVAILABLE, never a forever-spinner."""
    active = _FakeTranscript()
    res = derive_slot_state(
        section_type="lecture",
        summary_type="brief",
        active_transcript=active,
        summary_row=None,
        summary_step_status="not_started",
        overall_state="failed",
    )
    assert res.state == UNAVAILABLE


def test_precedence_upstream_progressing_is_generating():
    active = _FakeTranscript()
    res = derive_slot_state(
        section_type="lecture",
        summary_type="brief",
        active_transcript=active,
        summary_row=None,
        summary_step_status="not_started",
        overall_state="embedding",
    )
    assert res.state == GENERATING


def test_coarse_section_state():
    assert derive_section_summaries_state(NOT_APPLICABLE, NOT_APPLICABLE) == "not_applicable"
    assert derive_section_summaries_state(READY, READY) == "ready"
    assert derive_section_summaries_state(READY, GENERATING) == "partial"
    assert derive_section_summaries_state(GENERATING, GENERATING) == "generating"
    assert derive_section_summaries_state(UNAVAILABLE, UNAVAILABLE) == "none"


# --------------------------------------------------------------------------------------------------
# Unit — §5 policy gates (rows R / D-P-I).
# --------------------------------------------------------------------------------------------------
def test_policy_row_r_non_student_forbidden():
    for role in ("lecturer", "admin"):
        with pytest.raises(HTTPException) as exc:
            StudentSummaryAccessPolicy.require_student(role)
        assert exc.value.status_code == 403
        assert exc.value.detail == STUDENT_SUMMARY_FORBIDDEN


def test_policy_student_passes():
    StudentSummaryAccessPolicy.require_student("student")  # no raise


def test_policy_rows_dpi_missing_section_is_pinned_404():
    with pytest.raises(HTTPException) as exc:
        StudentSummaryAccessPolicy.require_visible(None)
    assert exc.value.status_code == 404
    assert exc.value.detail == SECTION_NOT_FOUND


def test_policy_visible_section_returned():
    sentinel = object()
    assert StudentSummaryAccessPolicy.require_visible(sentinel) is sentinel


# --------------------------------------------------------------------------------------------------
# Unit — markdown shaping (§3.3): detailed structured JSON → flattened markdown; empties skipped.
# --------------------------------------------------------------------------------------------------
def test_brief_markdown_is_text():
    assert brief_to_markdown({"text": "  hello world  "}) == "hello world"


def test_detailed_markdown_flattens_and_skips_empty_sections():
    md = detailed_to_markdown(
        {
            "overview": "An overview.",
            "keyConcepts": ["A", "B"],
            "importantDefinitions": [{"term": "T", "definition": "D"}],
            "mainExplanations": [],
            "examples": ["E1"],
            "examRelevantPoints": [],
            "labNotes": ["note"],
        }
    )
    assert "## Overview" in md and "An overview." in md
    assert "## Key concepts" in md and "- A" in md
    assert "**T** — D" in md
    assert "## Examples" in md and "- E1" in md
    assert "## Lab notes" in md
    assert "## Main explanations" not in md  # empty list skipped
    assert "## Exam-relevant points" not in md


def test_summary_to_markdown_dispatch():
    assert summary_to_markdown("brief", {"text": "x"}) == "x"
    assert "## Overview" in summary_to_markdown("detailed_study", {"overview": "o"})


# --------------------------------------------------------------------------------------------------
# Integration factories.
# --------------------------------------------------------------------------------------------------
async def _user(session: AsyncSession, *, role: str, email: str | None = None, is_active: bool = True) -> AppUser:
    user = AppUser(
        auth_provider_id=f"provider-{uuid4()}",
        email=email or f"{role}-{uuid4()}@example.test",
        full_name="Test",
        role=role,
        is_active=is_active,
        timezone="UTC",
    )
    session.add(user)
    await session.flush()
    return user


async def _module(session: AsyncSession, *, owner_id: UUID) -> CourseModule:
    module = CourseModule(title=f"M-{uuid4()}", owner_id=owner_id, timezone="UTC", is_active=True)
    session.add(module)
    await session.flush()
    return module


async def _membership(session: AsyncSession, *, user_id: UUID, module_id: UUID, role: str, status: str = "active"):
    m = CourseMembership(user_id=user_id, module_id=module_id, role=role, status=status)
    session.add(m)
    await session.flush()
    return m


async def _section(
    session: AsyncSession,
    *,
    module_id: UUID,
    title: str = "Lecture 1",
    section_type: str = "lecture",
    order_index: int = 0,
    publish_status: str = "published",
    lecturer_notes: str | None = "notes",
) -> ModuleSection:
    s = ModuleSection(
        course_module_id=module_id,
        title=title,
        type=section_type,
        order_index=order_index,
        publish_status=publish_status,
        lecturer_notes=lecturer_notes,
        status="active",
    )
    session.add(s)
    await session.flush()
    return s


async def _transcript(
    session: AsyncSession,
    *,
    section_id: UUID,
    uploader_id: UUID,
    lifecycle_state: str = "active",
    checksum: str | None = None,
    status: str = "completed",
) -> Transcript:
    t = Transcript(
        id=uuid4(),
        module_section_id=section_id,
        source_type="manual_upload",
        original_file_name="lecture.vtt",
        storage_key=f"modules/test/transcripts/{uuid4()}/x.vtt",
        mime_type="text/vtt",
        file_size=10,
        checksum=checksum or _checksum(),
        status=status,
        uploaded_by_user_id=uploader_id,
        lifecycle_state=lifecycle_state,
        # CHECK ck_transcripts_superseded_has_ts requires a timestamp when superseded.
        superseded_at=_now() if lifecycle_state == "superseded" else None,
    )
    session.add(t)
    await session.flush()
    return t


async def _job(session: AsyncSession, *, transcript_id: UUID, job_type: str, status: str, failure_category: str | None = None) -> IngestionJob:
    j = IngestionJob(
        transcript_id=transcript_id,
        job_type=job_type,
        status=status,
        idempotency_key=f"{transcript_id}:{job_type}:{uuid4()}",
        completed_at=_now() if status == "completed" else None,
        failure_category=failure_category,
    )
    session.add(j)
    await session.flush()
    return j


async def _summary(
    session: AsyncSession,
    *,
    transcript: Transcript,
    summary_type: str,
    job: IngestionJob,
    content_json: dict | None = None,
    source_checksum: str | None = None,
) -> GeneratedLectureSummary:
    log = AIRequestLog(
        ingestion_job_id=job.id,
        feature="summary_brief" if summary_type == "brief" else "summary_detailed",
        model_id="m",
        prompt_version="v1",
        prompt_content_hash="pch",
        rendered_prompt_hash="rph",
        input_content_hash="ich",
        status="succeeded",
    )
    session.add(log)
    await session.flush()
    default = {"text": "the core ideas of the topic"} if summary_type == "brief" else {
        "overview": "structured overview of the session",
        "keyConcepts": ["k1"],
        "importantDefinitions": [{"term": "t", "definition": "d"}],
        "mainExplanations": ["m1"],
        "examples": ["e1"],
        "examRelevantPoints": ["x1"],
        "labNotes": [],
    }
    summary = GeneratedLectureSummary(
        transcript_id=transcript.id,
        module_section_id=transcript.module_section_id,
        summary_type=summary_type,
        content_json=content_json or default,
        content_schema_version="v1",
        model_id="m",
        prompt_version="v1",
        prompt_content_hash="pch",
        backend_used="cerebras" if summary_type == "brief" else "nvidia",
        source_transcript_checksum=source_checksum or transcript.checksum,
        input_hash="ih",
        ai_request_log_id=log.id,
        created_by_ingestion_job_id=job.id,
    )
    session.add(summary)
    await session.flush()
    return summary


def _headers(user: AppUser, jwt_factory) -> dict[str, str]:
    return {"Authorization": f"Bearer {jwt_factory(sub=user.auth_provider_id)}"}


async def _summarized_section(session: AsyncSession, *, module_id: UUID, uploader_id: UUID, **kw) -> tuple[ModuleSection, Transcript]:
    """A published lecture with an active transcript + both summaries generated + completed jobs."""
    section = await _section(session, module_id=module_id, **kw)
    transcript = await _transcript(session, section_id=section.id, uploader_id=uploader_id)
    await _job(session, transcript_id=transcript.id, job_type="embed", status="completed")
    brief_job = await _job(session, transcript_id=transcript.id, job_type="generate_brief_summary", status="completed")
    detailed_job = await _job(session, transcript_id=transcript.id, job_type="generate_detailed_summary", status="completed")
    await _summary(session, transcript=transcript, summary_type="brief", job=brief_job)
    await _summary(session, transcript=transcript, summary_type="detailed_study", job=detailed_job)
    return section, transcript


# --------------------------------------------------------------------------------------------------
# Integration — §5 rows.
# --------------------------------------------------------------------------------------------------
async def test_row1_both_summaries_ready(db_session, auth_client: AsyncClient, jwt_factory, mock_jwks_client):
    lecturer = await _user(db_session, role="lecturer")
    student = await _user(db_session, role="student")
    module = await _module(db_session, owner_id=lecturer.id)
    await _membership(db_session, user_id=student.id, module_id=module.id, role="student")
    section, _ = await _summarized_section(db_session, module_id=module.id, uploader_id=lecturer.id)

    resp = await auth_client.get(f"/student/sections/{section.id}/summaries", headers=_headers(student, jwt_factory))
    assert resp.status_code == 200
    body = resp.json()
    assert body["summaries"]["brief"]["state"] == "ready"
    assert "core ideas" in body["summaries"]["brief"]["content"]
    assert body["summaries"]["detailed"]["state"] == "ready"
    assert "## Overview" in body["summaries"]["detailed"]["content"]
    assert resp.headers["cache-control"] == "private, no-store"

    detail = await auth_client.get(f"/student/sections/{section.id}", headers=_headers(student, jwt_factory))
    assert detail.status_code == 200
    d = detail.json()
    assert d["summaries"]["brief"]["state"] == "ready"
    assert d["summaries"]["detailed"]["state"] == "ready"
    assert d["lecturerNotes"] == "notes"


async def test_row2_brief_ready_detailed_generating(db_session, auth_client, jwt_factory, mock_jwks_client):
    lecturer = await _user(db_session, role="lecturer")
    student = await _user(db_session, role="student")
    module = await _module(db_session, owner_id=lecturer.id)
    await _membership(db_session, user_id=student.id, module_id=module.id, role="student")
    section = await _section(db_session, module_id=module.id)
    transcript = await _transcript(db_session, section_id=section.id, uploader_id=lecturer.id)
    await _job(db_session, transcript_id=transcript.id, job_type="embed", status="completed")
    brief_job = await _job(db_session, transcript_id=transcript.id, job_type="generate_brief_summary", status="completed")
    await _job(db_session, transcript_id=transcript.id, job_type="generate_detailed_summary", status="running")
    await _summary(db_session, transcript=transcript, summary_type="brief", job=brief_job)

    resp = await auth_client.get(f"/student/sections/{section.id}/summaries", headers=_headers(student, jwt_factory))
    body = resp.json()
    assert body["summaries"]["brief"]["state"] == "ready"
    assert body["summaries"]["detailed"]["state"] == "generating"
    assert body["summaries"]["detailed"]["content"] is None


async def test_row4_summary_failed_is_unavailable(db_session, auth_client, jwt_factory, mock_jwks_client):
    lecturer = await _user(db_session, role="lecturer")
    student = await _user(db_session, role="student")
    module = await _module(db_session, owner_id=lecturer.id)
    await _membership(db_session, user_id=student.id, module_id=module.id, role="student")
    section = await _section(db_session, module_id=module.id)
    transcript = await _transcript(db_session, section_id=section.id, uploader_id=lecturer.id)
    await _job(db_session, transcript_id=transcript.id, job_type="embed", status="completed")
    await _job(db_session, transcript_id=transcript.id, job_type="generate_brief_summary", status="failed", failure_category="invalid_output")

    resp = await auth_client.get(f"/student/sections/{section.id}/summaries", headers=_headers(student, jwt_factory))
    body = resp.json()
    assert body["summaries"]["brief"]["state"] == "unavailable"
    # student never sees the lecturer failure taxonomy
    assert "invalid_output" not in resp.text


async def test_row5_no_transcript_is_unavailable(db_session, auth_client, jwt_factory, mock_jwks_client):
    lecturer = await _user(db_session, role="lecturer")
    student = await _user(db_session, role="student")
    module = await _module(db_session, owner_id=lecturer.id)
    await _membership(db_session, user_id=student.id, module_id=module.id, role="student")
    section = await _section(db_session, module_id=module.id)

    resp = await auth_client.get(f"/student/sections/{section.id}/summaries", headers=_headers(student, jwt_factory))
    body = resp.json()
    assert body["summaries"]["brief"]["state"] == "unavailable"
    assert body["summaries"]["detailed"]["state"] == "unavailable"


async def test_row6_supersession_mid_regeneration_is_generating(db_session, auth_client, jwt_factory, mock_jwks_client):
    """New active transcript has no summaries yet; old superseded one did. Student sees GENERATING, never
    the old transcript's summary attributed to the new one (§7)."""
    lecturer = await _user(db_session, role="lecturer")
    student = await _user(db_session, role="student")
    module = await _module(db_session, owner_id=lecturer.id)
    await _membership(db_session, user_id=student.id, module_id=module.id, role="student")
    section = await _section(db_session, module_id=module.id)
    # superseded old transcript WITH summaries
    old = await _transcript(db_session, section_id=section.id, uploader_id=lecturer.id, lifecycle_state="superseded")
    old.superseded_at = _now()
    old_job = await _job(db_session, transcript_id=old.id, job_type="generate_brief_summary", status="completed")
    await _summary(db_session, transcript=old, summary_type="brief", job=old_job, content_json={"text": "OLD SUMMARY"})
    # new active transcript, no summaries yet, brief job queued
    new = await _transcript(db_session, section_id=section.id, uploader_id=lecturer.id, lifecycle_state="active")
    await _job(db_session, transcript_id=new.id, job_type="embed", status="completed")
    await _job(db_session, transcript_id=new.id, job_type="generate_brief_summary", status="queued")

    resp = await auth_client.get(f"/student/sections/{section.id}/summaries", headers=_headers(student, jwt_factory))
    body = resp.json()
    assert body["summaries"]["brief"]["state"] == "generating"
    assert "OLD SUMMARY" not in resp.text  # never the superseded content


async def test_rowT_assignment_is_not_applicable_200(db_session, auth_client, jwt_factory, mock_jwks_client):
    lecturer = await _user(db_session, role="lecturer")
    student = await _user(db_session, role="student")
    module = await _module(db_session, owner_id=lecturer.id)
    await _membership(db_session, user_id=student.id, module_id=module.id, role="student")
    section = await _section(db_session, module_id=module.id, title="Assignment 1", section_type="assignment")

    resp = await auth_client.get(f"/student/sections/{section.id}/summaries", headers=_headers(student, jwt_factory))
    assert resp.status_code == 200  # NOT 404 (H1)
    body = resp.json()
    assert body["summaries"]["brief"]["state"] == "not_applicable"
    assert body["summaries"]["detailed"]["state"] == "not_applicable"


async def test_rows_DPI_byte_identical_404(db_session, auth_client, jwt_factory, mock_jwks_client):
    """Rows D (unpublished), P (other module), I (inactive membership) → byte-identical 404 (S2)."""
    lecturer = await _user(db_session, role="lecturer")
    student = await _user(db_session, role="student")
    module = await _module(db_session, owner_id=lecturer.id)
    await _membership(db_session, user_id=student.id, module_id=module.id, role="student")

    # Row D — a draft section in the student's module
    draft = await _section(db_session, module_id=module.id, title="Draft", publish_status="draft")
    # Row P — a published section in a module the student is NOT in
    other_lecturer = await _user(db_session, role="lecturer")
    other_module = await _module(db_session, owner_id=other_lecturer.id)
    other_section, _ = await _summarized_section(db_session, module_id=other_module.id, uploader_id=other_lecturer.id)
    # Row I — published section in a module where the student's membership is archived
    inactive_lecturer = await _user(db_session, role="lecturer")
    inactive_module = await _module(db_session, owner_id=inactive_lecturer.id)
    await _membership(db_session, user_id=student.id, module_id=inactive_module.id, role="student", status="archived")
    inactive_section, _ = await _summarized_section(db_session, module_id=inactive_module.id, uploader_id=inactive_lecturer.id)

    h = _headers(student, jwt_factory)
    rD = await auth_client.get(f"/student/sections/{draft.id}/summaries", headers=h)
    rP = await auth_client.get(f"/student/sections/{other_section.id}/summaries", headers=h)
    rI = await auth_client.get(f"/student/sections/{inactive_section.id}/summaries", headers=h)
    for r in (rD, rP, rI):
        assert r.status_code == 404
    # byte-identical bodies (S2) — assert on bytes, not just status
    assert rD.content == rP.content == rI.content
    assert rD.json() == {"detail": SECTION_NOT_FOUND}


async def test_rowR_non_student_forbidden_403(db_session, auth_client, jwt_factory, mock_jwks_client):
    lecturer = await _user(db_session, role="lecturer")
    student = await _user(db_session, role="student")
    module = await _module(db_session, owner_id=lecturer.id)
    await _membership(db_session, user_id=lecturer.id, module_id=module.id, role="lecturer")
    section, _ = await _summarized_section(db_session, module_id=module.id, uploader_id=lecturer.id)

    resp = await auth_client.get(f"/student/sections/{section.id}/summaries", headers=_headers(lecturer, jwt_factory))
    assert resp.status_code == 403
    assert resp.json() == {"detail": STUDENT_SUMMARY_FORBIDDEN}


async def test_rowA_unauthenticated_401(db_session, auth_client, jwt_factory, mock_jwks_client):
    lecturer = await _user(db_session, role="lecturer")
    module = await _module(db_session, owner_id=lecturer.id)
    section, _ = await _summarized_section(db_session, module_id=module.id, uploader_id=lecturer.id)
    resp = await auth_client.get(f"/student/sections/{section.id}/summaries")  # no auth header
    assert resp.status_code == 401


# --------------------------------------------------------------------------------------------------
# Integration — security (sentinel non-leak, schema hygiene) + list + P3.
# --------------------------------------------------------------------------------------------------
async def test_sentinel_never_surfaces_in_student_responses(db_session, auth_client, jwt_factory, mock_jwks_client):
    """G3(b) backend half — a raw-transcript sentinel must appear in NO student response."""
    lecturer = await _user(db_session, role="lecturer")
    student = await _user(db_session, role="student")
    module = await _module(db_session, owner_id=lecturer.id)
    await _membership(db_session, user_id=student.id, module_id=module.id, role="student")
    section, transcript = await _summarized_section(db_session, module_id=module.id, uploader_id=lecturer.id)
    # seed the sentinel into a transcript segment (raw transcript text) — summaries do NOT contain it
    db_session.add(
        TranscriptSegment(transcript_id=transcript.id, sequence_number=99, start_ms=0, end_ms=1, text=SENTINEL)
    )
    await db_session.flush()

    h = _headers(student, jwt_factory)
    for path in (
        f"/student/modules/{module.id}/sections",
        f"/student/sections/{section.id}",
        f"/student/sections/{section.id}/summaries",
    ):
        r = await auth_client.get(path, headers=h)
        assert r.status_code == 200
        assert SENTINEL not in r.text, f"sentinel leaked via {path}"


async def test_schema_hygiene_no_forbidden_fields(db_session, auth_client, jwt_factory, mock_jwks_client):
    lecturer = await _user(db_session, role="lecturer")
    student = await _user(db_session, role="student")
    module = await _module(db_session, owner_id=lecturer.id)
    await _membership(db_session, user_id=student.id, module_id=module.id, role="student")
    section, _ = await _summarized_section(db_session, module_id=module.id, uploader_id=lecturer.id)

    h = _headers(student, jwt_factory)

    def _assert_clean(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                assert k not in FORBIDDEN_KEYS, f"forbidden key leaked: {k}"
                _assert_clean(v)
        elif isinstance(obj, list):
            for v in obj:
                _assert_clean(v)

    for path in (
        f"/student/modules/{module.id}/sections",
        f"/student/sections/{section.id}",
        f"/student/sections/{section.id}/summaries",
    ):
        r = await auth_client.get(path, headers=h)
        _assert_clean(r.json())


async def test_list_coarse_state_and_membership(db_session, auth_client, jwt_factory, mock_jwks_client):
    lecturer = await _user(db_session, role="lecturer")
    student = await _user(db_session, role="student")
    module = await _module(db_session, owner_id=lecturer.id)
    await _membership(db_session, user_id=student.id, module_id=module.id, role="student")
    ready_section, _ = await _summarized_section(db_session, module_id=module.id, uploader_id=lecturer.id, title="Lecture 1", order_index=0)
    assignment = await _section(db_session, module_id=module.id, title="Assignment 1", section_type="assignment", order_index=1)
    # a published lecture with no transcript → 'none'
    bare = await _section(db_session, module_id=module.id, title="Lecture 2", order_index=2)

    resp = await auth_client.get(f"/student/modules/{module.id}/sections", headers=_headers(student, jwt_factory))
    assert resp.status_code == 200
    by_id = {row["id"]: row for row in resp.json()}
    assert by_id[str(ready_section.id)]["summariesState"] == "ready"
    assert by_id[str(assignment.id)]["summariesState"] == "not_applicable"
    assert by_id[str(bare.id)]["summariesState"] == "none"

    # non-member → 404
    outsider = await _user(db_session, role="student")
    r404 = await auth_client.get(f"/student/modules/{module.id}/sections", headers=_headers(outsider, jwt_factory))
    assert r404.status_code == 404
    # lecturer → 403
    r403 = await auth_client.get(f"/student/modules/{module.id}/sections", headers=_headers(lecturer, jwt_factory))
    assert r403.status_code == 403


async def test_p3_transcript_endpoints_reject_student(db_session, auth_client, jwt_factory, mock_jwks_client):
    """P3 / S4(b) — every transcript text-bearing endpoint rejects the student token (403)."""
    lecturer = await _user(db_session, role="lecturer")
    student = await _user(db_session, role="student")
    module = await _module(db_session, owner_id=lecturer.id)
    await _membership(db_session, user_id=student.id, module_id=module.id, role="student")
    section, _ = await _summarized_section(db_session, module_id=module.id, uploader_id=lecturer.id)
    h = _headers(student, jwt_factory)
    base = f"/modules/{module.id}/sections/{section.id}"
    for path in (
        f"{base}/transcript",
        f"{base}/transcript-processing-status",
        f"{base}/transcript-summaries",
        f"{base}/transcript-active-summary-preview",
    ):
        r = await auth_client.get(path, headers=h)
        assert r.status_code == 403, f"{path} did not reject the student: {r.status_code}"
