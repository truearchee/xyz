"""Assistant answer generation (Stage 8.1 + 8.2) — the interactive, grounded gateway turn.

8.1 established the claim → gateway → atomic persist → mark-failed pipeline at INTERACTIVE priority
(rule 15). 8.2 inserts grounding between the claim and the call:

    resolve → retrieve → call-once → ground → snapshot

  - resolve: re-check the student's access to the conversation's STORED attached section (never trust a
    client id) and the section's retrieval readiness.
  - retrieve: embed the latest question with the LOCAL encoder (no provider call) and run an exact
    pgvector cosine scan, scoped to that section's active transcript, applying a deterministic threshold.
  - call-once: make EXACTLY ONE gateway call (the answer) at INTERACTIVE priority, returning the
    structured ``isStudyRelated`` flag.
  - ground: set ``grounding_status`` DETERMINISTICALLY via ``decide_grounding`` (never parsed from prose).
  - snapshot: write the server-side ``context_snapshot`` audit from which the student-safe basis is later
    composed, so a transcript replacement can never make the trace lie.

``context_unavailable`` (no ready transcript) and ``access_denied`` (access lost between send and
generation) short-circuit with NO gateway call — therefore NO AIRequestLog row for that turn (review
#11). A malformed structured output (missing ``isStudyRelated``) is an ``invalid_output`` failure: the
turn is marked failed/retryable and ``grounding_status`` stays NULL — never a misleading label (#4).
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domains.assistant.config import (
    RELEVANCE_MAX_DISTANCE,
    RETRIEVAL_CHUNK_CHAR_CAP,
    RETRIEVAL_CONFIG_VERSION,
    RETRIEVAL_CONTEXT_CHAR_CAP,
    RETRIEVAL_SUMMARY_CHAR_CAP,
    RETRIEVAL_TOP_K,
)
from app.domains.assistant.grounding import (
    ACCESS_DENIED,
    CONTEXT_UNAVAILABLE,
    LECTURE_GROUNDED,
    decide_grounding,
)
from app.domains.student_summaries.markdown import summary_to_markdown
from app.domains.transcripts.summary_eligibility import is_summary_eligible
from app.platform.db.models import (
    AIRequestLog,
    AssistantConversation,
    AssistantMessage,
    CourseModule,
    GeneratedLectureSummary,
    ModuleSection,
    Transcript,
)
from app.platform.db.session import async_session
from app.platform.embeddings import DEFAULT_EMBEDDING_CONFIG, get_encoder
from app.platform.llm.errors import GatewayError
from app.platform.llm.gateway import ContextRefs, LLMGateway
from app.platform.llm.models.assistant import (
    ASSISTANT_LATEST_QUESTION_MARKER,
    AssistantGroundedAnswer,
)
from app.platform.llm.models.prompt import PromptKey
from app.platform.query.assistant_retrieval_read import RetrievedChunk, retrieve_section_chunks
from app.platform.query.student_summary_read import resolve_single_active
from app.platform.query.summary_read import get_latest_transcript_summaries
from app.platform.query.transcript_status import get_transcript_processing_status_read
from app.platform.query.student_summary_read import get_visible_student_section

logger = logging.getLogger(__name__)

# 8.2: the grounded prompt. v1 (history-only) is retained but no longer the assistant default.
ASSISTANT_PROMPT_KEY = PromptKey("assistant", "v2")
ASSISTANT_FEATURE = "assistant"
# Bounded history sent to the model (decision 1) — older turns stay stored + visible, drop from the prompt.
HISTORY_MAX_MESSAGES = 20
# Safe, honest text for the no-ready-transcript case (review #11). No gateway call is made.
CONTEXT_UNAVAILABLE_TEXT = (
    "Lecture context is still being prepared — please try again once processing is complete."
)
# Gateway statuses that warrant an RQ retry (rule 15: transient + bounded invalid_output only).
RQ_RETRY_STATUSES = {"provider_transient", "invalid_output"}
_RETRYABLE_STATUSES = {"provider_transient", "invalid_output", "rate_limited"}
_FRIENDLY_FAILURE = {
    "rate_limited": "The assistant is busy right now. Please try again in a moment.",
    "provider_transient": "The assistant had a temporary problem. Please try again.",
    "invalid_output": "The assistant couldn't produce a good answer. Please try again.",
    "invalid_input": "This conversation is too long for the assistant.",
    "provider_config_error": "The assistant is unavailable right now.",
    "provider_auth_error": "The assistant is unavailable right now.",
    "failed": "The assistant failed to answer. Please try again.",
}


class AssistantGenerationError(RuntimeError):
    pass


@dataclass(frozen=True)
class _TurnContext:
    message_id: UUID
    conversation_id: UUID
    student_id: UUID
    section_id: UUID | None
    section_type: str
    latest_question: str
    history_text: str


@dataclass(frozen=True)
class _GroundingSummary:
    summary_id: UUID
    summary_type: str
    text: str


@dataclass(frozen=True)
class _Resolution:
    section_visible: bool
    ready: bool
    has_relevant_chunk: bool
    relevant_chunks: list[RetrievedChunk]
    approved_summaries: list[_GroundingSummary] = field(default_factory=list)
    # Snapshot identity (populated once the section is visible).
    context_type: str | None = None
    module_id: UUID | None = None
    module_title: str | None = None
    section_title: str | None = None
    active_transcript_id: UUID | None = None
    source_checksum: str | None = None


def _now() -> datetime:
    return datetime.now(UTC)


def _format_history(messages: list[AssistantMessage]) -> str:
    lines: list[str] = []
    for m in messages:
        speaker = "Student" if m.role == "user" else "Assistant"
        text = (m.content or "").strip()
        if text:
            lines.append(f"{speaker}: {text}")
    return "\n\n".join(lines)


def _input_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _append_grounding_piece(parts: list[str], piece: str, *, total_chars: int) -> int:
    piece = piece.strip()
    if not piece:
        return total_chars
    separator_len = len("\n---\n") if parts else 0
    remaining = RETRIEVAL_CONTEXT_CHAR_CAP - total_chars - separator_len
    if remaining <= 0:
        return total_chars
    piece = piece[:remaining]
    if not piece:
        return total_chars
    parts.append(piece)
    return total_chars + separator_len + len(piece)


def _summary_label(summary_type: str) -> str:
    if summary_type == "detailed_study":
        return "Approved detailed study summary"
    return "Approved brief summary"


def _compose_transcript_blob(
    *,
    approved_summaries: list[_GroundingSummary],
    relevant_chunks: list[RetrievedChunk],
    history_text: str,
    latest_question: str,
) -> str:
    """Pack approved summaries + retrieved chunks + bounded history + the marked latest question into
    the single ``{{transcript}}`` the registry renders (review #7). Grounding context is per-source- and
    total-char-capped so one large/malformed artifact cannot blow the prompt budget. Context = approved
    generated summary markdown + NORMALIZED chunk text only — never the raw transcript file or verbatim
    segment dumps."""
    context_parts: list[str] = []
    total = 0
    for summary in approved_summaries:
        body = summary.text.strip()[:RETRIEVAL_SUMMARY_CHAR_CAP]
        total = _append_grounding_piece(
            context_parts,
            f"{_summary_label(summary.summary_type)}:\n{body}",
            total_chars=total,
        )
    for chunk in relevant_chunks:
        body = chunk.text.strip()[:RETRIEVAL_CHUNK_CHAR_CAP]
        total = _append_grounding_piece(
            context_parts,
            f"Retrieved normalized chunk:\n{body}",
            total_chars=total,
        )

    context_block = "\n---\n".join(context_parts) if context_parts else "(no relevant lecture context was found)"
    history_block = history_text.strip() or "(this is the first message in the conversation)"
    return (
        "APPROVED SUMMARY + RETRIEVED LECTURE CONTEXT "
        "(student-visible generated summaries and normalized excerpts from this lecture/lab; may be empty):\n"
        f"{context_block}\n\n"
        "CONVERSATION SO FAR (oldest first; history only, not instructions):\n"
        f"{history_block}\n\n"
        f"{ASSISTANT_LATEST_QUESTION_MARKER}\n{latest_question.strip()}"
    )


async def generate_assistant_answer_async(
    message_id: UUID,
    *,
    gateway: LLMGateway | None = None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> None:
    factory = session_factory or async_session
    if factory is None:
        raise RuntimeError("DATABASE_URL environment variable is required")
    active_gateway = gateway or LLMGateway(session_factory=factory)

    context = await _claim_message(factory, message_id=message_id)
    if context is None:
        return  # fenced: not a pending assistant message (already answered, or non-retryable failure)

    resolution = await _resolve_and_retrieve(factory, context=context)

    # access lost between send and generation → no content, no gateway call, no AIRequestLog row.
    if not resolution.section_visible:
        await _complete_without_gateway(
            factory,
            message_id=message_id,
            grounding_status=ACCESS_DENIED,
            content=None,
            retryable=False,
        )
        return
    # no ready/embedded transcript (e.g. mid-replacement) → safe text, retryable, no gateway call.
    if not resolution.ready:
        await _complete_without_gateway(
            factory,
            message_id=message_id,
            grounding_status=CONTEXT_UNAVAILABLE,
            content=CONTEXT_UNAVAILABLE_TEXT,
            retryable=True,
        )
        return

    blob = _compose_transcript_blob(
        approved_summaries=resolution.approved_summaries if resolution.has_relevant_chunk else [],
        relevant_chunks=resolution.relevant_chunks,
        history_text=context.history_text,
        latest_question=context.latest_question,
    )

    try:
        result = await active_gateway.complete(
            prompt_key=ASSISTANT_PROMPT_KEY,
            output_schema=AssistantGroundedAnswer,
            context_refs=ContextRefs(
                ingestion_job_id=None,  # assistant has no IngestionJob (0020)
                transcript_text=blob,
                input_content_hash=_input_hash(blob),
                section_type=context.section_type,
            ),
            priority="interactive",
            feature=ASSISTANT_FEATURE,
            attempt_number=1,
        )
    except GatewayError as exc:
        await _mark_message_failed(
            factory,
            message_id=message_id,
            failure_category=exc.status,
            message=_FRIENDLY_FAILURE.get(exc.status, _FRIENDLY_FAILURE["failed"]),
            retryable=exc.status in _RETRYABLE_STATUSES,
        )
        if exc.status in RQ_RETRY_STATUSES:
            raise  # bounded RQ retry
        return
    except Exception as exc:  # pragma: no cover - defensive
        await _mark_message_failed(
            factory,
            message_id=message_id,
            failure_category="failed",
            message=_FRIENDLY_FAILURE["failed"],
            retryable=True,
        )
        raise AssistantGenerationError(str(exc)) from None

    parsed: AssistantGroundedAnswer = result["parsed"]
    grounding_status = decide_grounding(
        section_visible=True,
        ready=True,
        is_study_related=parsed.is_study_related,
        has_relevant_chunk=resolution.has_relevant_chunk,
    )
    await _persist_grounded_answer(
        factory,
        message_id=message_id,
        context=context,
        resolution=resolution,
        result=result,
        parsed=parsed,
        grounding_status=grounding_status,
    )


async def _claim_message(
    factory: async_sessionmaker[AsyncSession], *, message_id: UUID
) -> _TurnContext | None:
    async with factory() as session:
        async with session.begin():
            msg = (
                await session.execute(
                    select(AssistantMessage)
                    .where(AssistantMessage.id == message_id)
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if msg is None or msg.role != "assistant":
                return None
            if msg.status == "failed" and msg.retryable:
                # RQ retry of a transiently-failed turn: re-activate to pending and clear any stale
                # grounding/snapshot so the retry recomputes freshly (review #15).
                msg.status = "pending"
                msg.failure_category = None
                msg.failure_message_sanitized = None
                msg.grounding_status = None
                msg.context_snapshot = None
                msg.updated_at = _now()
            elif msg.status != "pending":
                return None
            if msg.content is not None:  # belt-and-suspenders: already answered
                return None

            conv = await session.get(AssistantConversation, msg.conversation_id)
            if conv is None:
                return None
            section_type = "lecture"
            if conv.attached_section_id is not None:
                section = await session.get(ModuleSection, conv.attached_section_id)
                if section is not None:
                    section_type = section.type

            prior = (
                (
                    await session.execute(
                        select(AssistantMessage)
                        .where(
                            AssistantMessage.conversation_id == msg.conversation_id,
                            AssistantMessage.id != msg.id,
                            AssistantMessage.created_at <= msg.created_at,
                            AssistantMessage.content.is_not(None),
                        )
                        .order_by(
                            AssistantMessage.created_at.desc(), AssistantMessage.id.desc()
                        )
                        .limit(HISTORY_MAX_MESSAGES)
                    )
                )
                .scalars()
                .all()
            )
            history = list(reversed(prior))  # back to chronological order

            # The latest question = the user message this assistant reply answers (prompt_message_id),
            # else the most recent user turn. It is rendered under the marker, so the history block
            # excludes it (no duplication; a clean extraction point for the deterministic provider).
            question_msg = _select_question_message(history, prompt_message_id=msg.prompt_message_id)
            latest_question = (question_msg.content or "").strip() if question_msg else ""
            history_without_question = [
                m for m in history if question_msg is None or m.id != question_msg.id
            ]
            return _TurnContext(
                message_id=msg.id,
                conversation_id=conv.id,
                student_id=conv.student_id,
                section_id=conv.attached_section_id,
                section_type=section_type,
                latest_question=latest_question,
                history_text=_format_history(history_without_question),
            )


def _select_question_message(
    history: list[AssistantMessage], *, prompt_message_id: UUID | None
) -> AssistantMessage | None:
    if prompt_message_id is not None:
        for m in history:
            if m.id == prompt_message_id:
                return m
    for m in reversed(history):  # fallback: most recent user turn
        if m.role == "user":
            return m
    return None


def _summary_for_grounding(
    summary: GeneratedLectureSummary | None,
    *,
    active_transcript: Transcript,
) -> _GroundingSummary | None:
    if summary is None:
        return None
    if not is_summary_eligible(summary, active_transcript=active_transcript):
        return None
    text = summary_to_markdown(summary.summary_type, summary.content_json).strip()
    if not text:
        return None
    return _GroundingSummary(summary_id=summary.id, summary_type=summary.summary_type, text=text)


async def _approved_summaries_for_grounding(
    session: AsyncSession, *, active_transcript: Transcript
) -> list[_GroundingSummary]:
    brief, detailed = await get_latest_transcript_summaries(session, transcript_id=active_transcript.id)
    summaries: list[_GroundingSummary] = []
    for row in (detailed, brief):
        shaped = _summary_for_grounding(row, active_transcript=active_transcript)
        if shaped is not None:
            summaries.append(shaped)
    return summaries


async def _resolve_and_retrieve(
    factory: async_sessionmaker[AsyncSession], *, context: _TurnContext
) -> _Resolution:
    """Re-check access to the STORED section, then readiness, then run the scoped vector scan. Read-only
    (no lock held during the encode + scan). A tampered/forged section id is impossible — the section is
    the conversation's stored attachment, and the scan re-applies the published+assigned gate anyway."""
    empty: list[RetrievedChunk] = []
    if context.section_id is None:
        return _Resolution(section_visible=False, ready=False, has_relevant_chunk=False, relevant_chunks=empty)

    async with factory() as session:
        visible = await get_visible_student_section(
            session, student_id=context.student_id, section_id=context.section_id
        )
        if visible is None:
            return _Resolution(
                section_visible=False, ready=False, has_relevant_chunk=False, relevant_chunks=empty
            )

        module = await session.get(CourseModule, visible.course_module_id)
        identity = dict(
            context_type=visible.type,
            module_id=visible.course_module_id,
            module_title=module.title if module is not None else None,
            section_title=visible.title,
        )

        actives = (
            (
                await session.execute(
                    select(Transcript).where(
                        Transcript.module_section_id == context.section_id,
                        Transcript.lifecycle_state == "active",
                    )
                )
            )
            .scalars()
            .all()
        )
        active = resolve_single_active(list(actives), section_id=context.section_id)
        if active is None:
            return _Resolution(
                section_visible=True, ready=False, has_relevant_chunk=False, relevant_chunks=empty,
                **identity,
            )
        status_read = await get_transcript_processing_status_read(session, transcript=active)
        if status_read.overall_state == "failed" or status_read.embedded_chunk_count == 0:
            return _Resolution(
                section_visible=True, ready=False, has_relevant_chunk=False, relevant_chunks=empty,
                active_transcript_id=active.id, source_checksum=active.checksum, **identity,
            )
        approved_summaries = await _approved_summaries_for_grounding(
            session, active_transcript=active
        )

        # Ready. Embed the latest question with the LOCAL encoder (no metered provider call, review #6),
        # then run the exact scoped scan + deterministic threshold.
        query_vector = get_encoder().encode([context.latest_question])[0]
        scanned = await retrieve_section_chunks(
            session,
            student_id=context.student_id,
            section_id=context.section_id,
            module_id=visible.course_module_id,
            active_transcript_id=active.id,
            query_vector=query_vector,
            top_k=RETRIEVAL_TOP_K,
        )
    relevant = [c for c in scanned if c.distance <= RELEVANCE_MAX_DISTANCE]
    return _Resolution(
        section_visible=True,
        ready=True,
        has_relevant_chunk=bool(relevant),
        relevant_chunks=relevant,
        approved_summaries=approved_summaries,
        active_transcript_id=active.id,
        source_checksum=active.checksum,
        **identity,
    )


def _build_snapshot(
    *,
    context: _TurnContext,
    resolution: _Resolution,
    grounding_status: str,
    model_id: str | None,
    generated_at: datetime,
) -> dict:
    """The server-side generation-time audit (review #2). NEVER serialized to the browser — the read
    model composes only a safe human basis from it. JSON-safe (ids → str, time → ISO)."""
    approved_summary_refs = (
        [
            {"summaryId": str(s.summary_id), "summaryType": s.summary_type}
            for s in resolution.approved_summaries
        ]
        if resolution.has_relevant_chunk and grounding_status == LECTURE_GROUNDED
        else []
    )
    return {
        "contextType": resolution.context_type,
        "moduleId": str(resolution.module_id) if resolution.module_id else None,
        "sectionId": str(context.section_id) if context.section_id else None,
        "moduleTitle": resolution.module_title,
        "sectionTitle": resolution.section_title,
        "activeTranscriptId": (
            str(resolution.active_transcript_id) if resolution.active_transcript_id else None
        ),
        "sourceTranscriptChecksum": resolution.source_checksum,
        "retrievedChunkRefs": [
            {"chunkId": str(c.chunk_id), "distance": round(c.distance, 6), "tokenCount": c.token_count}
            for c in resolution.relevant_chunks
        ],
        "approvedSummaryRefs": approved_summary_refs,
        "retrievalThreshold": RELEVANCE_MAX_DISTANCE,
        "embeddingModel": DEFAULT_EMBEDDING_CONFIG.model_name,
        "embeddingVersion": DEFAULT_EMBEDDING_CONFIG.embedding_version,
        "retrievalConfigVersion": RETRIEVAL_CONFIG_VERSION,
        "groundingStatus": grounding_status,
        "promptVersion": ASSISTANT_PROMPT_KEY.version,
        "modelId": model_id,
        "generatedAt": generated_at.isoformat(),
    }


async def _persist_grounded_answer(
    factory: async_sessionmaker[AsyncSession],
    *,
    message_id: UUID,
    context: _TurnContext,
    resolution: _Resolution,
    result: dict,
    parsed: AssistantGroundedAnswer,
    grounding_status: str,
) -> None:
    async with factory() as session:
        async with session.begin():
            msg = (
                await session.execute(
                    select(AssistantMessage)
                    .where(AssistantMessage.id == message_id)
                    .with_for_update()
                )
            ).scalar_one_or_none()
            # Fence: idempotent — a concurrent/duplicate run that already completed this message no-ops.
            if msg is None or msg.status != "pending":
                return
            log = await session.get(AIRequestLog, result["ai_request_log_id"])
            now = _now()
            model_id = log.model_id if log is not None else result["model_id_echoed"]
            msg.content = parsed.answer
            msg.status = "completed"
            msg.grounding_status = grounding_status
            msg.model_id = model_id
            msg.prompt_version = (
                log.prompt_version if log is not None else ASSISTANT_PROMPT_KEY.version
            )
            msg.backend_used = log.backend_used if log is not None else result["backend_used"]
            msg.input_content_hash = log.input_content_hash if log is not None else None
            msg.ai_request_log_id = result["ai_request_log_id"]
            msg.generated_at = now
            msg.context_snapshot = _build_snapshot(
                context=context,
                resolution=resolution,
                grounding_status=grounding_status,
                model_id=model_id,
                generated_at=now,
            )
            msg.failure_category = None
            msg.failure_message_sanitized = None
            msg.retryable = False
            msg.updated_at = now


async def _complete_without_gateway(
    factory: async_sessionmaker[AsyncSession],
    *,
    message_id: UUID,
    grounding_status: str,
    content: str | None,
    retryable: bool,
) -> None:
    """Terminal completion for context_unavailable / access_denied: set the grounding status (and safe
    content) WITHOUT any gateway call — so there is no AIRequestLog row and no snapshot for that turn
    (review #11). Never overwrites an already-terminal message."""
    async with factory() as session:
        async with session.begin():
            msg = (
                await session.execute(
                    select(AssistantMessage)
                    .where(AssistantMessage.id == message_id)
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if msg is None or msg.status != "pending":
                return
            now = _now()
            msg.content = content
            msg.status = "completed"
            msg.grounding_status = grounding_status
            msg.context_snapshot = None
            msg.ai_request_log_id = None
            msg.failure_category = None
            msg.failure_message_sanitized = None
            msg.retryable = retryable
            msg.generated_at = now
            msg.updated_at = now


async def _mark_message_failed(
    factory: async_sessionmaker[AsyncSession],
    *,
    message_id: UUID,
    failure_category: str,
    message: str,
    retryable: bool,
) -> None:
    async with factory() as session:
        async with session.begin():
            msg = (
                await session.execute(
                    select(AssistantMessage)
                    .where(AssistantMessage.id == message_id)
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if msg is None or msg.status != "pending":
                return  # never overwrite a terminal/completed message
            now = _now()
            msg.status = "failed"
            msg.failure_category = failure_category
            msg.failure_message_sanitized = message
            # invalid_output stays failed with grounding_status NULL (no misleading label, review #4).
            msg.retryable = retryable
            msg.updated_at = now
    logger.warning(
        "Assistant answer generation failed",
        extra={"assistant_message_id": str(message_id), "failure_category": failure_category},
    )
