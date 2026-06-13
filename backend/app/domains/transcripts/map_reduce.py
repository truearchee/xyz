"""Map-reduce detailed summarization engine (Stage 4.5.1a, F-4.5-51).

Removes the single-call transcript-size ceiling (a full ~60-min lecture 408s the provider on BOTH
routes — F-4.5-50). The detailed summary is produced by:

  partition  → group consecutive normalized segments into the FEWEST map-units each under BOTH a char
               and an estimated-token budget; never split a segment. Deterministic; hashed.
  map        → summarize each unit in its own background ``gateway.complete`` call → a persisted
               ``MapUnitSummary`` partial (resume: a unit whose partial already succeeded for the SAME
               partition hash + transcript checksum is reused, never re-called — C3).
  reduce     → merge the partials into one coherent ``DetailedSummary``. The reduce INPUT is itself a
               408 surface, so a §3.3 GUARD reduces in ordered groups (tiered) when the serialized
               partials exceed the reduce-input budget, recursing until one call fits.

Every provider call goes through ``LLMGateway.complete`` (the single orchestration point) — this module
adds NO transport, logging, or limiting of its own. Rule-15 deviation is recorded in ADR-051: a summary
is a one-time ingestion cost (quizzes read the generated summary, never re-summarize), the calls are
background-priority, and the partition is coarse (fewest units).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from uuid6 import uuid7

from app.domains.transcripts.chunker import NORMALIZATION_VERSION
from app.domains.transcripts.summary_specs import MAP_PROMPT_KEY, OVERVIEW_PROMPT_KEY
from app.platform.config import settings
from app.platform.db.models import MapUnitSummary, Transcript
from app.platform.llm.context import CHARS_PER_TOKEN, estimate_tokens
from app.platform.llm.errors import GatewayError
from app.platform.llm.gateway import ContextRefs, LLMGateway
from app.platform.llm.models.summary import (
    BriefSummary,
    DetailedSummary,
    DetailedSummaryPartial,
    Definition,
)

logger = logging.getLogger(__name__)
# Cap on each unioned list in the assembled detailed summary (defense against a pathological partial count).
_MAX_LIST_ITEMS = 60


class MapReduceError(RuntimeError):
    """A terminal map-reduce failure (cost-guard tripped, coverage gap, assemble failure)."""


class MapReduceFenced(MapReduceError):
    """The transcript was superseded or its checksum changed mid-flight (§6.1 stale-write fence). The
    caller treats this as a CLEAN abort — no partial/reduce artifact is written, and it is NOT a job
    failure (the transcript is being replaced; activation of the replacement proceeds independently)."""


@dataclass(frozen=True)
class SegmentText:
    """A transcript segment reduced to (id, normalized non-empty text) for partitioning."""

    segment_id: UUID
    text: str


@dataclass(frozen=True)
class MapUnit:
    unit_index: int
    start_segment_id: UUID
    end_segment_id: UUID
    text: str
    char_count: int
    est_tokens: int


@dataclass(frozen=True)
class Partition:
    units: tuple[MapUnit, ...]
    partition_config_hash: str


@dataclass(frozen=True)
class MapReduceOutcome:
    """What the detailed handler persists: the assembled detailed + map-reduce provenance."""

    result: dict  # {"parsed": assembled DetailedSummary, "ai_request_log_id": the overview call's log}
    input_hash: str  # folds partition_config_hash → distinct provenance per budget (decision 4)
    map_prompt_version: str
    overview_prompt_version: str
    map_unit_count: int
    source_map_unit_summary_ids: list[str]
    coverage_manifest: list[int]
    partition_config_hash: str


@dataclass(frozen=True)
class _MappedUnit:
    unit_index: int
    map_unit_summary_id: UUID
    content: dict


# ── pure partition + hashing ────────────────────────────────────────────────


def _est_tokens_for_chars(char_count: int) -> int:
    # estimate_tokens is purely length-based (ceil(len/3.5)); derive from a char count without joining.
    import math

    return math.ceil(char_count / CHARS_PER_TOKEN)


def compute_partition_config_hash(
    *, char_budget: int, token_budget: int, chunker_version: str, transcript_checksum: str
) -> str:
    payload = {
        "charBudget": char_budget,
        "tokenBudget": token_budget,
        "chunkerVersion": chunker_version,
        "transcriptChecksum": transcript_checksum,
    }
    canonical = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def partition_segments(
    segments: list[SegmentText],
    *,
    char_budget: int,
    token_budget: int,
    max_units: int,
    chunker_version: str,
    transcript_checksum: str,
) -> Partition:
    """Group CONSECUTIVE segments into the FEWEST units each under BOTH budgets; never split a segment.

    Greedy left-to-right packing is optimal for contiguous, non-splitting grouping and is deterministic
    for a given (segment texts, budgets). A lone segment larger than a budget becomes its own unit (we
    cannot split it) — still far under the full-transcript size that 408s. Char counts track the joined
    length incrementally so the token estimate is exact without re-joining (O(n), not O(n²))."""
    units: list[MapUnit] = []
    cur: list[SegmentText] = []
    cur_chars = 0  # exact length of " ".join(cur)

    def flush() -> None:
        nonlocal cur, cur_chars
        if not cur:
            return
        text = " ".join(s.text for s in cur).strip()
        units.append(
            MapUnit(
                unit_index=len(units),
                start_segment_id=cur[0].segment_id,
                end_segment_id=cur[-1].segment_id,
                text=text,
                char_count=len(text),
                est_tokens=estimate_tokens(text),
            )
        )
        cur = []
        cur_chars = 0

    for seg in segments:
        added = (1 if cur else 0) + len(seg.text)  # +1 for the joining space
        new_chars = cur_chars + added
        if cur and (new_chars > char_budget or _est_tokens_for_chars(new_chars) > token_budget):
            flush()
            new_chars = len(seg.text)
        cur.append(seg)
        cur_chars = new_chars
    flush()

    if len(units) > max_units:
        raise MapReduceError(
            f"partition produced {len(units)} map-units (> max {max_units}); cost guard tripped"
        )
    return Partition(
        units=tuple(units),
        partition_config_hash=compute_partition_config_hash(
            char_budget=char_budget,
            token_budget=token_budget,
            chunker_version=chunker_version,
            transcript_checksum=transcript_checksum,
        ),
    )


def _dedupe_strings(lists) -> list[str]:
    """Flatten an iterable of string lists in order, dropping blanks and case-insensitive duplicates while
    preserving the FIRST original spelling and order. Capped to bound the assembled summary."""
    seen: set[str] = set()
    out: list[str] = []
    for lst in lists:
        for s in lst or []:
            text = str(s).strip()
            key = text.casefold()
            if text and key not in seen:
                seen.add(key)
                out.append(text)
                if len(out) >= _MAX_LIST_ITEMS:
                    return out
    return out


def _dedupe_definitions(partials: list[dict]) -> list[dict]:
    """Union the partials' importantDefinitions, deduped by term (case-insensitive), first spelling wins."""
    seen: set[str] = set()
    out: list[dict] = []
    for p in partials:
        for d in p.get("importantDefinitions") or []:
            term = str(d.get("term", "")).strip()
            definition = str(d.get("definition", "")).strip()
            key = term.casefold()
            if term and definition and key not in seen:
                seen.add(key)
                out.append({"term": term, "definition": definition})
                if len(out) >= _MAX_LIST_ITEMS:
                    return out
    return out


def _union_partials(partials: list[dict]) -> dict:
    """Programmatic reduce (F-4.5.1c-3): union + dedupe every structured list across the map partials, in
    lecture order. Guarantees the detailed summary covers the WHOLE lecture — no LLM compression can drop
    content the map already extracted."""
    return {
        "keyConcepts": _dedupe_strings(p.get("keyConcepts") for p in partials),
        "importantDefinitions": _dedupe_definitions(partials),
        "mainExplanations": _dedupe_strings(p.get("mainExplanations") for p in partials),
        "examples": _dedupe_strings(p.get("examples") for p in partials),
        "examRelevantPoints": _dedupe_strings(p.get("examRelevantPoints") for p in partials),
        "labNotes": _dedupe_strings(p.get("labNotes") for p in partials),
    }


def _overview_input(partials: list[dict], merged: dict) -> str:
    """Small, focused input for the overview LLM call: the per-portion overviews (the lecture arc) + the
    merged key concepts. Kept compact so the call is fast and reliable."""
    lines = ["Per-portion overviews (in order):"]
    for p in partials:
        ov = (p.get("overview") or "").strip()
        if ov:
            lines.append(f"- {ov}")
    lines.append("")
    lines.append("Key concepts covered: " + ", ".join(merged["keyConcepts"][:40]))
    return "\n".join(lines)


def _hash(payload: dict) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _unit_input_hash(unit: MapUnit) -> str:
    return _hash({"normalizationVersion": NORMALIZATION_VERSION, "unitIndex": unit.unit_index, "text": unit.text})


def _overview_input_hash(overview_input: str) -> str:
    return _hash({"normalizationVersion": NORMALIZATION_VERSION, "phase": "overview", "input": overview_input})


def detailed_input_hash(full_text: str, partition_config_hash: str) -> str:
    """Provenance hash for the persisted map-reduce summary. Folds the partition hash so a budget change
    yields a DISTINCT row and never collides with the prior truncated single-call row (decision 4)."""
    return _hash(
        {
            "normalizationVersion": NORMALIZATION_VERSION,
            "fullText": full_text,
            "partitionConfigHash": partition_config_hash,
        }
    )


# ── orchestration ────────────────────────────────────────────────────────────


class MapReduceRunner:
    def __init__(
        self,
        factory: async_sessionmaker[AsyncSession],
        gateway: LLMGateway,
        *,
        ingestion_job_id: UUID,
        transcript_id: UUID,
        section_type: str,
        source_transcript_checksum: str,
        attempt_number: int,
    ) -> None:
        self._factory = factory
        self._gateway = gateway
        self._ingestion_job_id = ingestion_job_id
        self._transcript_id = transcript_id
        self._section_type = section_type
        self._checksum = source_transcript_checksum
        self._attempt_number = attempt_number

    async def run(self, segments: list[SegmentText], full_text: str) -> MapReduceOutcome:
        # §6.1 early abort: never spend map calls on an already-superseded/changed transcript.
        async with self._factory() as session:
            await self._fence(session)
        partition = partition_segments(
            segments,
            char_budget=settings.LLM_SUMMARY_MAP_UNIT_CHAR_BUDGET,
            token_budget=settings.LLM_SUMMARY_MAP_UNIT_TOKEN_BUDGET,
            max_units=settings.LLM_SUMMARY_MAX_MAP_UNITS,
            chunker_version=NORMALIZATION_VERSION,
            transcript_checksum=self._checksum,
        )
        logger.info(
            "map-reduce partition",
            extra={
                "transcript_id": str(self._transcript_id),
                "map_unit_count": len(partition.units),
                "partition_config_hash": partition.partition_config_hash[:12],
            },
        )
        mapped = await self._map_all(partition)
        # §6.1 fence before the artifact write: do not assemble for a superseded/changed transcript.
        async with self._factory() as session:
            await self._fence(session)
        # Reduce = programmatic union of the structured partials (full coverage GUARANTEED by construction)
        # + one LLM call for the overview (F-4.5.1c-3). Coverage is exhaustive: every mapped unit's lists
        # are merged in.
        reduce_result = await self._assemble(mapped)
        expected = sorted(u.unit_index for u in partition.units)
        return MapReduceOutcome(
            result=reduce_result,
            input_hash=detailed_input_hash(full_text, partition.partition_config_hash),
            map_prompt_version=MAP_PROMPT_KEY.version,
            overview_prompt_version=OVERVIEW_PROMPT_KEY.version,
            map_unit_count=len(partition.units),
            source_map_unit_summary_ids=[str(m.map_unit_summary_id) for m in mapped],
            coverage_manifest=expected,
            partition_config_hash=partition.partition_config_hash,
        )

    async def _map_all(self, partition: Partition) -> list[_MappedUnit]:
        # Bounded concurrency (default 1 = sequential). Map units are independent rows keyed by
        # unit_index; order is restored by sort. A unit that raises GatewayError propagates → the job
        # fails and RQ retries the whole detailed job; succeeded units are reused on the retry (C3).
        sem = asyncio.Semaphore(settings.LLM_SUMMARY_MAP_CONCURRENCY)

        async def one(unit: MapUnit) -> _MappedUnit:
            async with sem:
                return await self._map_unit(unit, partition.partition_config_hash)

        results = await asyncio.gather(*(one(u) for u in partition.units))
        return sorted(results, key=lambda m: m.unit_index)

    async def _complete_retrying(self, *, label: str, **kwargs) -> dict:
        """gateway.complete with bounded in-call retry on invalid_output (4.5.1c). K2-Think-v2 is
        non-deterministic — even with JSON mode a call can occasionally return an unparseable body; a
        retry almost always yields clean JSON. Retries happen WITHIN the job (no RQ scheduler needed —
        F-4.5-47). Any non-invalid_output GatewayError (408/auth/limit) propagates immediately."""
        attempts = settings.LLM_SUMMARY_INVALID_OUTPUT_RETRIES + 1
        last_exc: GatewayError | None = None
        for i in range(attempts):
            try:
                return await self._gateway.complete(**kwargs)
            except GatewayError as exc:
                if exc.status != "invalid_output" or i == attempts - 1:
                    raise
                last_exc = exc
                logger.warning(
                    "map-reduce %s invalid_output; retrying (%d/%d)", label, i + 1, attempts - 1
                )
        raise last_exc  # pragma: no cover - loop always returns or raises above

    async def _map_unit(self, unit: MapUnit, partition_hash: str) -> _MappedUnit:
        existing = await self._find_succeeded_partial(unit.unit_index, partition_hash)
        if existing is not None and existing.partial_content is not None:
            return _MappedUnit(unit.unit_index, existing.id, existing.partial_content)

        result = await self._complete_retrying(
            label=f"map[{unit.unit_index}]",
            prompt_key=MAP_PROMPT_KEY,
            output_schema=DetailedSummaryPartial,
            context_refs=ContextRefs(
                ingestion_job_id=self._ingestion_job_id,
                transcript_text=unit.text,
                input_content_hash=_unit_input_hash(unit),
                section_type=self._section_type,
            ),
            priority="background",
            feature="detailed_summary_map",
            attempt_number=self._attempt_number,
        )
        content = result["parsed"].model_dump(by_alias=True)
        map_unit_summary_id = await self._persist_partial(
            unit, partition_hash, content, result["ai_request_log_id"]
        )
        return _MappedUnit(unit.unit_index, map_unit_summary_id, content)

    async def _assemble(self, mapped: list[_MappedUnit]) -> dict:
        """Reduce = programmatic union of the map partials' structured lists (coverage guaranteed) + ONE
        LLM call for the overview (F-4.5.1c-3). The model only writes the short overview — what it does
        reliably — instead of being asked to faithfully merge structured content (which it compresses
        away). Returns {"parsed": assembled DetailedSummary, "ai_request_log_id": the overview call's}."""
        partials = [m.content for m in mapped]  # in unit order
        merged = _union_partials(partials)
        overview_input = _overview_input(partials, merged)
        ov = await self._complete_retrying(
            label="overview",
            prompt_key=OVERVIEW_PROMPT_KEY,
            output_schema=BriefSummary,
            context_refs=ContextRefs(
                ingestion_job_id=self._ingestion_job_id,
                transcript_text=overview_input,
                input_content_hash=_overview_input_hash(overview_input),
                section_type=self._section_type,
            ),
            priority="background",
            feature="detailed_summary_reduce",
            attempt_number=self._attempt_number,
        )
        assembled = DetailedSummary(
            overview=ov["parsed"].text.strip(),
            key_concepts=merged["keyConcepts"],
            important_definitions=[
                Definition(term=d["term"], definition=d["definition"])
                for d in merged["importantDefinitions"]
            ],
            main_explanations=merged["mainExplanations"],
            examples=merged["examples"],
            exam_relevant_points=merged["examRelevantPoints"],
            lab_notes=merged["labNotes"] or None,
        )
        return {"parsed": assembled, "ai_request_log_id": ov["ai_request_log_id"]}

    async def _fence(self, session: AsyncSession) -> None:
        """§6.1 stale-write fence: raise MapReduceFenced if the transcript is superseded or its checksum
        no longer matches the one this run partitioned. Called before each persisted write."""
        transcript = (
            await session.execute(select(Transcript).where(Transcript.id == self._transcript_id))
        ).scalar_one_or_none()
        if (
            transcript is None
            or transcript.lifecycle_state == "superseded"
            or transcript.checksum != self._checksum
        ):
            raise MapReduceFenced(
                f"transcript {self._transcript_id} superseded/changed mid map-reduce; aborting clean"
            )

    async def _find_succeeded_partial(
        self, unit_index: int, partition_hash: str
    ) -> MapUnitSummary | None:
        async with self._factory() as session:
            return (
                await session.execute(
                    select(MapUnitSummary).where(
                        MapUnitSummary.transcript_id == self._transcript_id,
                        MapUnitSummary.unit_index == unit_index,
                        MapUnitSummary.partition_config_hash == partition_hash,
                        MapUnitSummary.source_transcript_checksum == self._checksum,
                        MapUnitSummary.status == "succeeded",
                    )
                )
            ).scalar_one_or_none()

    async def _persist_partial(
        self, unit: MapUnit, partition_hash: str, content: dict, ai_request_log_id: UUID
    ) -> UUID:
        async with self._factory() as session:
            async with session.begin():
                await self._fence(session)  # §6.1: never write a partial for a superseded transcript
                await session.execute(
                    pg_insert(MapUnitSummary)
                    .values(
                        id=uuid7(),
                        transcript_id=self._transcript_id,
                        unit_index=unit.unit_index,
                        start_segment_id=unit.start_segment_id,
                        end_segment_id=unit.end_segment_id,
                        partition_config_hash=partition_hash,
                        source_transcript_checksum=self._checksum,
                        map_prompt_version=MAP_PROMPT_KEY.version,
                        ai_request_log_id=ai_request_log_id,
                        status="succeeded",
                        partial_content=content,
                    )
                    .on_conflict_do_nothing(constraint="uq_map_unit_summaries_identity")
                )
            row = await self._find_succeeded_partial(unit.unit_index, partition_hash)
            if row is None:  # pragma: no cover - defensive (insert + conflict both failed)
                raise MapReduceError("map unit partial vanished immediately after insert")
            return row.id
