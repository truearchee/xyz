"""Summary generation job handlers (spec §6/§7/§8/§11).

After embeddings complete, two IngestionJob rows (``generate_brief_summary``,
``generate_detailed_summary``) are created in the embed transaction and enqueued onto the ``ai``
queue. Each handler loads the full normalized transcript, calls ``LLMGateway.complete`` (which owns
logging, limiting, validation), and on success stores a ``GeneratedLectureSummary`` whose provenance
is copied directly from the gateway's AIRequestLog row. On failure it writes no artifact and records
``IngestionJob.failure_category`` — the transcript itself is NOT failed (embeddings succeeded; the
projection represents per-step failure). This is the exact contract Stage 4.6's retry consumes.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from uuid6 import uuid7

from app.domains.transcripts.chunker import NORMALIZATION_VERSION, normalize_segment_text
from app.domains.transcripts.map_reduce import (
    MapReduceFenced,
    MapReduceOutcome,
    MapReduceRunner,
    SegmentText,
)
from app.domains.transcripts.summary_specs import (
    BRIEF,
    BRIEF_FROM_DETAILED_FEATURE,
    BRIEF_FROM_DETAILED_PROMPT_KEY,
    DETAILED,
    SUMMARY_JOB_TYPES,
    SUMMARY_SPECS,
    SummarySpec,
)
from app.platform.db.models import (
    AIRequestLog,
    GeneratedLectureSummary,
    IngestionJob,
    ModuleSection,
    Transcript,
    TranscriptSegment,
)
from app.platform.config import settings
from app.platform.db.session import async_session
from app.platform.faults.pipeline_faults import maybe_fail_step
from app.platform.llm.errors import GatewayError
from app.platform.llm.gateway import ContextRefs, LLMGateway
from app.platform.query.summary_read import get_latest_transcript_summaries

logger = logging.getLogger(__name__)

__all__ = [
    "BRIEF",
    "DETAILED",
    "SUMMARY_JOB_TYPES",
    "SUMMARY_SPECS",
    "SummarySpec",
    "generate_brief_summary_async",
    "generate_detailed_summary_async",
    "insert_summary_jobs",
]

# Failures that warrant an RQ retry (rule 15: reserved for transient + bounded invalid_output).
# provider_config_error / provider_auth_error are deliberately ABSENT — a bad model id or key is
# terminal; retrying it is a denial-of-wallet strategy (§8).
RQ_RETRY_STATUSES = {"provider_transient", "invalid_output"}
_FAILURE_CATEGORIES = {
    "provider_transient",
    "rate_limited",
    "invalid_output",
    "invalid_input",
    "provider_config_error",
    "provider_auth_error",
}


class SummaryGenerationError(RuntimeError):
    pass


@dataclass(frozen=True)
class _SummaryContext:
    transcript_id: UUID
    module_section_id: UUID
    source_transcript_checksum: str
    section_type: str
    normalized_text: str
    input_hash: str
    attempts: int
    truncated: bool
    source_char_count: int
    summarized_char_count: int
    # Map-reduce (4.5.1a): the per-segment normalized text the detailed path partitions over, and the
    # full (untruncated) transcript. Both are populated for every claim; brief ignores them.
    segment_texts: tuple[tuple[UUID, str], ...]
    normalized_full: str
    # Brief-from-detailed (4.5.1b, ADR-052): when True the brief input (normalized_text) is the COMPLETED
    # detailed summary's content_json, not the transcript — the brief uses the brief_from_detailed prompt
    # + feature and persists generation_strategy='derived_from_detailed'. False = the OB1 transcript-based
    # fallback (detailed disabled) or the detailed spec itself.
    brief_from_detailed: bool = False
    brief_source_detailed_id: UUID | None = None


def _now() -> datetime:
    return datetime.now(UTC)


def _summary_idempotency_key(transcript: Transcript, job_type: str) -> str:
    return f"{transcript.id}:{job_type}:{transcript.checksum}"


def _normalized_transcript(segments: list[TranscriptSegment]) -> str:
    parts = [normalize_segment_text(segment.text) for segment in segments]
    return " ".join(part for part in parts if part).strip()


def _truncate_for_summary(normalized_text: str) -> tuple[str, bool, int, int]:
    """Option A (F-4.5-50): after structural normalization, cap the transcript at the char budget so the
    real provider call stays under its server-side request-time ceiling (full lectures → HTTP 408 both
    routes). Cuts at a clean sentence/word boundary, never mid-word. Returns
    (kept_text, truncated, source_char_count, summarized_char_count) — `truncated` is LABELED on the record
    + surfaced in the UI, never silent. Over-budget = first-portion only; full coverage is map-reduce (F-4.5-51)."""
    budget = settings.LLM_SUMMARY_INPUT_CHAR_BUDGET
    source_chars = len(normalized_text)
    if source_chars <= budget:
        return normalized_text, False, source_chars, source_chars
    head = normalized_text[:budget]
    cut = head.rfind(". ")          # prefer a sentence boundary in the back half
    if cut < budget // 2:
        cut = head.rfind(" ")       # else the last word boundary
    kept = (head[: cut + 1] if cut > 0 else head).strip()
    return kept, True, source_chars, len(kept)


def _summary_input_hash(normalized_text: str) -> str:
    payload = {"normalizationVersion": NORMALIZATION_VERSION, "text": normalized_text}
    canonical = json.dumps(
        payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _brief_from_detailed_input_hash(detailed: GeneratedLectureSummary) -> str:
    """Provenance hash for a brief derived from a specific detailed summary (4.5.1b). Tied to the source
    detailed row's identity so a REGENERATED detailed (new id + input_hash) yields a distinct brief row."""
    payload = {
        "briefFromDetailed": True,
        "detailedSummaryId": str(detailed.id),
        "detailedInputHash": detailed.input_hash,
    }
    canonical = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


async def insert_summary_jobs(
    session: AsyncSession,
    *,
    transcript: Transcript,
    enable_detailed: bool | None = None,
) -> list[tuple[str, UUID]]:
    """Create the summary jobs (queued) within the caller's transaction (the embed txn).

    Brief is always created. Detailed is created ONLY when ``ENABLE_DETAILED_SUMMARY`` (§5) — gated
    at CREATION, not enqueue, so under 4.5b no detailed IngestionJob row exists for the 4.6 sweeper to
    misread and the inaccessible Think-v0 is never called. ``enable_detailed`` overrides the setting
    (used by tests of the detailed mechanism, which lands in 4.5c). Returns the (job_type, job_id)
    pairs to enqueue. Idempotent: an already-active or completed job is not duplicated; a previously
    failed job is reset to queued.
    """
    detailed_enabled = (
        settings.ENABLE_DETAILED_SUMMARY if enable_detailed is None else enable_detailed
    )
    # Always create the brief job ROW. Create detailed only when enabled (§5 — gated at creation).
    specs = [BRIEF] + ([DETAILED] if detailed_enabled else [])
    created: dict[str, UUID] = {}
    for spec in specs:
        job_id = await _ensure_summary_job(session, transcript=transcript, spec=spec)
        if job_id is not None:
            created[spec.job_type] = job_id

    # DAG (4.5.1b, ADR-052): when detailed is enabled, enqueue ONLY the detailed job now — the brief forks
    # from the COMPLETED detailed (the detailed handler enqueues the already-created brief row). When
    # detailed is disabled (OB1), enqueue the brief now: it falls back to the transcript-based truncated
    # path (degraded + labeled + non-quiz-eligible). Returns the (job_type, job_id) pairs to enqueue NOW.
    primary = DETAILED.job_type if detailed_enabled else BRIEF.job_type
    return [(primary, created[primary])] if primary in created else []


async def _fork_brief_after_detailed(
    factory: async_sessionmaker[AsyncSession],
    *,
    transcript_id: UUID,
) -> UUID | None:
    """Brief-from-detailed DAG (4.5.1b): enqueue the transcript's queued brief job once the detailed has
    completed. Idempotent (the brief claim no-ops on an already-completed/running job; enqueue is keyed on
    a stable RQ job_id). Returns the enqueued brief job id (or None if there is no queued brief)."""
    async with factory() as session:
        brief_job = (
            await session.execute(
                select(IngestionJob).where(
                    IngestionJob.transcript_id == transcript_id,
                    IngestionJob.job_type == BRIEF.job_type,
                    IngestionJob.status == "queued",
                )
            )
        ).scalar_one_or_none()
        brief_job_id = brief_job.id if brief_job is not None else None
    if brief_job_id is not None:
        from app.workers.queues import enqueue_generate_brief_summary

        try:
            enqueue_generate_brief_summary(brief_job_id)
        except Exception:  # pragma: no cover - best-effort, like activation; reaper/retry re-forks
            logger.warning(
                "failed to enqueue brief after detailed; will be re-forked on retry",
                extra={"brief_job_id": str(brief_job_id), "transcript_id": str(transcript_id)},
            )
    return brief_job_id


async def _ensure_summary_job(
    session: AsyncSession,
    *,
    transcript: Transcript,
    spec: SummarySpec,
    force: bool = False,
) -> UUID | None:
    # ``force`` (the 4.5.1b backfill): re-queue an already-COMPLETED job to regenerate a stale summary.
    # The normal path (force=False) no-ops on a completed job so the pipeline never duplicates work.
    active = await _active_summary_job(session, transcript_id=transcript.id, job_type=spec.job_type)
    if active is not None:
        return active.id

    idempotency_key = _summary_idempotency_key(transcript, spec.job_type)
    try:
        async with session.begin_nested():
            await session.execute(
                pg_insert(IngestionJob)
                .values(
                    id=uuid7(),
                    transcript_id=transcript.id,
                    job_type=spec.job_type,
                    status="queued",
                    idempotency_key=idempotency_key,
                    processor_version=str(spec.prompt_key),
                )
                .on_conflict_do_nothing(index_elements=["idempotency_key"])
            )
    except IntegrityError:
        # A concurrent writer won the one-active-summary index; re-read below.
        pass

    active = await _active_summary_job(session, transcript_id=transcript.id, job_type=spec.job_type)
    if active is not None:
        return active.id

    job = (
        await session.execute(
            select(IngestionJob)
            .where(IngestionJob.idempotency_key == idempotency_key)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if job is None:
        return None
    if job.status == "completed" and not force:
        return None
    if job.status == "failed" or (force and job.status == "completed"):
        now = _now()
        job.status = "queued"
        job.error_message = None
        job.failure_category = None
        job.completed_at = None
        job.updated_at = now
    return job.id


async def _active_summary_job(
    session: AsyncSession,
    *,
    transcript_id: UUID,
    job_type: str,
) -> IngestionJob | None:
    return (
        await session.execute(
            select(IngestionJob)
            .where(
                IngestionJob.transcript_id == transcript_id,
                IngestionJob.job_type == job_type,
                IngestionJob.status.in_(("queued", "running")),
            )
            .with_for_update()
        )
    ).scalar_one_or_none()


async def generate_brief_summary_async(
    ingestion_job_id: UUID,
    *,
    gateway: LLMGateway | None = None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> None:
    await _generate_summary_async(
        ingestion_job_id, spec=BRIEF, gateway=gateway, session_factory=session_factory
    )


async def generate_detailed_summary_async(
    ingestion_job_id: UUID,
    *,
    gateway: LLMGateway | None = None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> None:
    await _generate_summary_async(
        ingestion_job_id, spec=DETAILED, gateway=gateway, session_factory=session_factory
    )


async def _generate_summary_async(
    ingestion_job_id: UUID,
    *,
    spec: SummarySpec,
    gateway: LLMGateway | None,
    session_factory: async_sessionmaker[AsyncSession] | None,
) -> None:
    factory = session_factory or async_session
    if factory is None:
        raise RuntimeError("DATABASE_URL environment variable is required")
    active_gateway = gateway or LLMGateway(session_factory=factory)

    context = await _claim_summary_job(factory, ingestion_job_id=ingestion_job_id, spec=spec)
    if context is None:
        return

    result: dict | None = None
    outcome: MapReduceOutcome | None = None
    try:
        maybe_fail_step(spec.feature)
        if spec.summary_type == DETAILED.summary_type:
            # Detailed = map-reduce (4.5.1a): partition → map each unit → reduce. Every sub-call goes
            # through the gateway; a GatewayError (e.g. a unit times out) or a terminal MapReduceError
            # propagates to the handlers below exactly like the single-call brief path.
            runner = MapReduceRunner(
                factory,
                active_gateway,
                ingestion_job_id=ingestion_job_id,
                transcript_id=context.transcript_id,
                section_type=context.section_type,
                source_transcript_checksum=context.source_transcript_checksum,
                attempt_number=context.attempts,
            )
            outcome = await runner.run(
                [SegmentText(segment_id=sid, text=text) for sid, text in context.segment_texts],
                context.normalized_full,
            )
        else:
            # Brief (4.5.1b): mode-A (brief-from-detailed) uses the brief_from_detailed prompt + feature
            # over the completed detailed's content; mode-B (OB1 fallback, detailed disabled) uses the
            # transcript-based brief_summary prompt. `maybe_fail_step(spec.feature)` above stays keyed on
            # the STEP name "summary_brief" (the 4.6 pipeline fault), distinct from the LLM feature here.
            brief_prompt_key = (
                BRIEF_FROM_DETAILED_PROMPT_KEY if context.brief_from_detailed else spec.prompt_key
            )
            brief_feature = (
                BRIEF_FROM_DETAILED_FEATURE if context.brief_from_detailed else spec.feature
            )
            result = await active_gateway.complete(
                prompt_key=brief_prompt_key,
                output_schema=spec.output_schema,
                context_refs=ContextRefs(
                    ingestion_job_id=ingestion_job_id,
                    transcript_text=context.normalized_text,
                    input_content_hash=context.input_hash,
                    section_type=context.section_type,
                ),
                priority="background",
                feature=brief_feature,
                attempt_number=context.attempts,
            )
    except MapReduceFenced:
        # §6.1: the transcript was superseded/changed mid map-reduce. Clean abort — no artifact written,
        # NOT a failure (the replacement's own jobs proceed; the reaper reclaims this stale running job).
        logger.info(
            "map-reduce fenced (transcript superseded mid-flight)",
            extra={"ingestion_job_id": str(ingestion_job_id)},
        )
        return
    except GatewayError as exc:
        await _mark_summary_failed(
            factory,
            ingestion_job_id=ingestion_job_id,
            spec=spec,
            status=exc.status,
            error_message=_sanitize_error(exc),
        )
        if exc.status in RQ_RETRY_STATUSES:
            raise  # bounded RQ retry
        return
    except Exception as exc:  # pragma: no cover - defensive
        await _mark_summary_failed(
            factory,
            ingestion_job_id=ingestion_job_id,
            spec=spec,
            status="failed",
            error_message="summary generation failed",
        )
        raise SummaryGenerationError(str(exc)) from None

    await _persist_summary_success(
        factory,
        ingestion_job_id=ingestion_job_id,
        spec=spec,
        context=context,
        result=result,
        outcome=outcome,
    )

    # Brief-from-detailed DAG (4.5.1b, ADR-052): once the DETAILED summary is persisted, fork the brief —
    # it derives from the completed detailed and was created (not enqueued) at embed-time. Best-effort: a
    # superseded transcript's brief claim re-fences. No-op when detailed is disabled (no detailed runs).
    if spec.summary_type == DETAILED.summary_type:
        await _fork_brief_after_detailed(factory, transcript_id=context.transcript_id)

    # 4.6a (ADR-46-A): if this transcript is a completed pending replacement, swap it in. No-op for
    # the common active-first-upload path and for a pending that is not yet fully summarized. Never
    # fail the summary job on an activation error — leave the pending for a later trigger / retry.
    await _try_activate_after_summary(factory, transcript_id=context.transcript_id)


async def _try_activate_after_summary(
    factory: async_sessionmaker[AsyncSession],
    *,
    transcript_id: UUID,
) -> None:
    # Delegates to the shared best-effort hook (also called by the embed leaf — F-4.6b-2). Local import
    # keeps the summary_service ⇄ activation cycle broken.
    from app.domains.transcripts.activation import attempt_pending_activation

    await attempt_pending_activation(factory, transcript_id=transcript_id)


async def _claim_summary_job(
    factory: async_sessionmaker[AsyncSession],
    *,
    ingestion_job_id: UUID,
    spec: SummarySpec,
) -> _SummaryContext | None:
    async with factory() as session:
        async with session.begin():
            job = (
                await session.execute(
                    select(IngestionJob)
                    .where(
                        IngestionJob.id == ingestion_job_id,
                        IngestionJob.job_type == spec.job_type,
                    )
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if job is None or job.status == "completed":
                return None

            transcript = (
                await session.execute(
                    select(Transcript)
                    .where(Transcript.id == job.transcript_id)
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if transcript is None:
                raise SummaryGenerationError("transcript not found")
            if transcript.lifecycle_state == "superseded":
                # Fenced before any mutation: do not summarize a superseded transcript (ADR-46-B §3.2).
                return None

            section = (
                await session.execute(
                    select(ModuleSection).where(
                        ModuleSection.id == transcript.module_section_id
                    )
                )
            ).scalar_one_or_none()
            if section is None:
                raise SummaryGenerationError("module section not found")

            segments = (
                await session.execute(
                    select(TranscriptSegment)
                    .where(TranscriptSegment.transcript_id == transcript.id)
                    .order_by(TranscriptSegment.sequence_number)
                )
            ).scalars().all()
            segment_texts = tuple(
                (segment.id, normalized)
                for segment in segments
                if (normalized := normalize_segment_text(segment.text))
            )
            normalized_full = " ".join(text for _, text in segment_texts).strip()
            if not normalized_full:
                raise SummaryGenerationError("no transcript text available")

            # Resolve the model input BEFORE marking the job running, so a brief that must wait for the
            # detailed (brief-from-detailed) can DEFER without leaving a dangling 'running' job.
            brief_from_detailed = False
            brief_source_detailed_id: UUID | None = None
            if spec.summary_type == DETAILED.summary_type:
                # Map-reduce (4.5.1a): the FULL transcript is partitioned downstream — NEVER truncated.
                # The persist path recomputes the provenance input_hash to fold the partition hash.
                normalized = normalized_full
                truncated = False
                source_chars = kept_chars = len(normalized_full)
                input_hash = _summary_input_hash(normalized)
            elif settings.ENABLE_DETAILED_SUMMARY:
                # Brief-from-detailed (4.5.1b, ADR-052): derive the brief from the COMPLETED detailed
                # summary, not the transcript. §6.1 fence: the detailed must be bound to THIS active
                # transcript (matching checksum) — a brief firing after a replacement reads the NEW
                # detailed or DEFERS, never staples a stale detailed's brief onto a replaced transcript.
                _brief_row, detailed_row = await get_latest_transcript_summaries(
                    session, transcript_id=transcript.id
                )
                if (
                    detailed_row is None
                    or detailed_row.source_transcript_checksum != transcript.checksum
                ):
                    # Not ready / stale → defer (leave the job queued; the detailed-completion fork
                    # re-enqueues it). No 'running' mark, no attempt consumed.
                    return None
                normalized = json.dumps(
                    detailed_row.content_json, ensure_ascii=False, separators=(",", ":")
                )
                truncated = bool(detailed_row.truncated)  # the brief is as truncated as its source
                source_chars = kept_chars = len(normalized)
                input_hash = _brief_from_detailed_input_hash(detailed_row)
                brief_from_detailed = True
                brief_source_detailed_id = detailed_row.id
            else:
                # OB1 fallback (detailed disabled): transcript-based single-call brief (Option A). Honestly
                # degraded — truncated, labeled, NOT quiz-eligible — never a back door for full coverage.
                normalized, truncated, source_chars, kept_chars = _truncate_for_summary(normalized_full)
                input_hash = _summary_input_hash(normalized)

            now = _now()
            job.status = "running"
            job.attempts += 1
            job.started_at = now
            job.completed_at = None
            job.updated_at = now
            job.error_message = None
            job.failure_category = None

            return _SummaryContext(
                transcript_id=transcript.id,
                module_section_id=transcript.module_section_id,
                source_transcript_checksum=transcript.checksum,
                section_type=section.type,
                normalized_text=normalized,
                input_hash=input_hash,
                attempts=job.attempts,
                truncated=truncated,
                source_char_count=source_chars,
                summarized_char_count=kept_chars,
                segment_texts=segment_texts,
                normalized_full=normalized_full,
                brief_from_detailed=brief_from_detailed,
                brief_source_detailed_id=brief_source_detailed_id,
            )


async def _persist_summary_success(
    factory: async_sessionmaker[AsyncSession],
    *,
    ingestion_job_id: UUID,
    spec: SummarySpec,
    context: _SummaryContext,
    result: dict | None = None,
    outcome: MapReduceOutcome | None = None,
) -> None:
    # Exactly one of result (brief single-call) / outcome (detailed map-reduce) is provided. The
    # map-reduce outcome carries the REDUCE call's CompletionResult plus the strategy provenance; its
    # input_hash folds the partition hash so it never collides with the prior truncated single-call row.
    if outcome is not None:
        source = outcome.result
        input_hash = outcome.input_hash
        generation_strategy = "map_reduce"
        generation_metadata: dict | None = {
            "mapPromptVersion": outcome.map_prompt_version,
            "reducePromptVersion": outcome.reduce_prompt_version,
            "mapUnitCount": outcome.map_unit_count,
            "sourceMapUnitSummaryIds": outcome.source_map_unit_summary_ids,
            "coverageManifest": outcome.coverage_manifest,
            "partitionConfigHash": outcome.partition_config_hash,
        }
    elif result is not None:
        source = result
        input_hash = context.input_hash
        if context.brief_from_detailed:
            # Mode-A brief: derived from the completed detailed. The strategy label is INFORMATIONAL
            # provenance — quiz-eligibility is a property of the DETAILED (is_full_coverage_detailed),
            # never the brief. `truncated` was inherited from the source detailed in the claim.
            generation_strategy = "derived_from_detailed"
            generation_metadata = {
                "sourceDetailedSummaryId": str(context.brief_source_detailed_id),
                "briefPromptVersion": BRIEF_FROM_DETAILED_PROMPT_KEY.version,
            }
        else:
            # Mode-B brief (OB1 fallback) or any legacy transcript-based brief.
            generation_strategy = "single_call"
            generation_metadata = None
    else:  # pragma: no cover - defensive
        raise SummaryGenerationError("persist requires exactly one of result/outcome")

    content_json = source["parsed"].model_dump(by_alias=True)
    async with factory() as session:
        async with session.begin():
            job = (
                await session.execute(
                    select(IngestionJob)
                    .where(
                        IngestionJob.id == ingestion_job_id,
                        IngestionJob.job_type == spec.job_type,
                    )
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if job is None or job.status != "running":
                return

            transcript = (
                await session.execute(
                    select(Transcript)
                    .where(Transcript.id == context.transcript_id)
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if transcript is None or transcript.lifecycle_state == "superseded":
                # Fenced: do not write a summary artifact for a superseded transcript (ADR-46-B §3.2).
                return

            log = await session.get(AIRequestLog, source["ai_request_log_id"])
            if log is None:  # pragma: no cover - defensive
                raise SummaryGenerationError("AIRequestLog row missing for generated summary")

            await session.execute(
                pg_insert(GeneratedLectureSummary)
                .values(
                    id=uuid7(),
                    transcript_id=context.transcript_id,
                    module_section_id=context.module_section_id,
                    summary_type=spec.summary_type,
                    content_json=content_json,
                    content_schema_version=spec.content_schema_version,
                    model_id=log.model_id,
                    prompt_version=log.prompt_version,
                    prompt_content_hash=log.prompt_content_hash,
                    backend_used=log.backend_used,
                    reasoning_level=log.reasoning_level,
                    source_transcript_checksum=context.source_transcript_checksum,
                    input_hash=input_hash,
                    ai_request_log_id=log.id,
                    created_by_ingestion_job_id=ingestion_job_id,
                    truncated=context.truncated,
                    source_char_count=context.source_char_count,
                    summarized_char_count=context.summarized_char_count,
                    generation_strategy=generation_strategy,
                    generation_metadata=generation_metadata,
                )
                .on_conflict_do_nothing(constraint="uq_gen_summaries_provenance")
            )

            now = _now()
            job.status = "completed"
            job.completed_at = now
            job.updated_at = now
            job.error_message = None
            job.failure_category = None
            job.result_metadata = {
                "summary_type": spec.summary_type,
                "ai_request_log_id": str(log.id),
                "backend_used": log.backend_used,
            }


async def _mark_summary_failed(
    factory: async_sessionmaker[AsyncSession],
    *,
    ingestion_job_id: UUID,
    spec: SummarySpec,
    status: str,
    error_message: str,
) -> None:
    failure_category = status if status in _FAILURE_CATEGORIES else "failed"
    async with factory() as session:
        async with session.begin():
            job = (
                await session.execute(
                    select(IngestionJob)
                    .where(
                        IngestionJob.id == ingestion_job_id,
                        IngestionJob.job_type == spec.job_type,
                    )
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if job is None or job.status == "completed":
                return
            now = _now()
            job.status = "failed"
            job.error_message = error_message
            job.failure_category = failure_category
            job.updated_at = now
            # The transcript is NOT failed — embeddings succeeded; per-step failure is shown
            # by the status projection (spec §7.4).
    logger.warning(
        "Summary job failed",
        extra={
            "ingestion_job_id": str(ingestion_job_id),
            "job_type": spec.job_type,
            "failure_category": failure_category,
        },
    )


def _sanitize_error(exc: GatewayError) -> str:
    code = f" ({exc.error_code})" if exc.error_code else ""
    return f"{exc.status}{code}"
