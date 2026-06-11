"""Per-slot state precedence (Stage 4.7 §6) — the read-side logic core.

A PURE function: given a section type, the active transcript, the latest summary row for one slot, and
the 4.5 status projection for that active transcript, it derives the single student-facing state for
that slot. First match wins, exactly as the spec table reads.

THE TRICKIEST CORRECTNESS POINT (spec §4/§6, ratified ADR-4.7-2/3):

  CORRUPTION   — a row exists for the ACTIVE transcript (id match) but its checksum disagrees with the
                 active transcript's checksum. Transcripts are immutable, so id-match *implies*
                 checksum-match; a mismatch can only mean corruption. → UNAVAILABLE **+ log**.
  SUPERSESSION — no generated row exists for the active transcript yet (e.g. mid-replacement: the new
                 active transcript has no summaries, only the superseded one did). → GENERATING.

``is_summary_eligible`` returns False for BOTH — so this module MUST NOT branch on it to tell them
apart. We inspect the checksum on a present (already id-matched) row separately, and treat "no row" as
the supersession/not-yet path. Collapsing the two would silently delete the corruption signal.

GeneratedLectureSummary is a SUCCESS-ONLY table (no ``status`` column) — a row's existence IS
"generated". "failed" / "generating" are therefore derived from the projection's per-step status +
``overall_state`` (4.5d ``transcript_status``), never from a summary-row status.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.platform.db.models import GeneratedLectureSummary, Transcript

logger = logging.getLogger(__name__)

# Student-facing slot states (spec §6 / §10). Binary on the failure axis: GENERATING vs UNAVAILABLE —
# never the lecturer-only failure taxonomy (failed/rate_limited/invalid_output).
READY = "ready"
GENERATING = "generating"
UNAVAILABLE = "unavailable"
NOT_APPLICABLE = "not_applicable"

SUMMARY_SECTION_TYPES = ("lecture", "lab")

# summary_type → the projection step key it is driven by (transcript_status.JOB_TYPE_TO_STEP).
SUMMARY_TYPE_TO_STEP = {
    "brief": "summary_brief",
    "detailed_study": "summary_detailed",
}

# Coarse per-section list flag (§8.1).
LIST_READY = "ready"
LIST_PARTIAL = "partial"
LIST_GENERATING = "generating"
LIST_NONE = "none"
LIST_NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True)
class SlotResult:
    state: str
    # True only on the completed-but-missing-artifact anomaly (§6 step 4c): the pipeline says this
    # summary step completed but no success-only row exists. Surfaces a LECTURER-side inconsistency
    # (retry/debug, 4.6); for the student it is simply UNAVAILABLE.
    lecturer_inconsistency: bool = False


def _content_is_blank(content_json: dict | None, summary_type: str) -> bool:
    """§6 step 2b — a stored row whose content is empty/blank after trim is an anomaly, not READY."""
    cj = content_json or {}
    if summary_type == "brief":
        return not str(cj.get("text", "")).strip()
    # detailed_study (stored camelCase via model_dump(by_alias=True))
    overview = str(cj.get("overview", "")).strip()
    list_fields = (
        "keyConcepts",
        "importantDefinitions",
        "mainExplanations",
        "examples",
        "examRelevantPoints",
        "labNotes",
    )
    has_list_content = any(cj.get(field) for field in list_fields)
    return not overview and not has_list_content


def derive_slot_state(
    *,
    section_type: str,
    summary_type: str,
    active_transcript: Transcript | None,
    summary_row: GeneratedLectureSummary | None,
    summary_step_status: str | None,
    overall_state: str | None,
    section_id: object = None,
) -> SlotResult:
    """Resolve ONE slot (brief or detailed) to a student-facing state. First match wins (§6).

    ``summary_row`` is the latest row for the ACTIVE transcript's id for this ``summary_type`` (so its
    ``transcript_id`` already equals the active transcript by construction — the only identity check left
    is the checksum tripwire). ``summary_step_status`` / ``overall_state`` come from the 4.5 projection
    for that active transcript; both are None only when there is no active transcript (handled at step 1).
    """
    # Step 0 — section type gate.
    if section_type not in SUMMARY_SECTION_TYPES:
        return SlotResult(NOT_APPLICABLE)

    # Step 1 — no active transcript for the section.
    if active_transcript is None:
        return SlotResult(UNAVAILABLE)

    # Step 2 — a generated row exists for the active transcript (success-only table ⇒ "generated").
    if summary_row is not None:
        # 2a — corruption tripwire. The row is for the active transcript (queried by active.id); a
        # checksum disagreement can only mean corruption. Fail safe and LOG. NEVER collapse with the
        # "no row" supersession path below.
        if summary_row.source_transcript_checksum != active_transcript.checksum:
            logger.error(
                "student-summary corruption tripwire: summary %s for active transcript %s has checksum "
                "%s != active checksum %s (section=%s, type=%s) — failing safe to unavailable",
                summary_row.id,
                active_transcript.id,
                summary_row.source_transcript_checksum,
                active_transcript.checksum,
                section_id,
                summary_type,
            )
            return SlotResult(UNAVAILABLE)
        # 2b — empty/blank content anomaly.
        if _content_is_blank(summary_row.content_json, summary_type):
            logger.warning(
                "student-summary blank-content anomaly: summary %s (active transcript %s, section=%s, "
                "type=%s) — failing safe to unavailable",
                summary_row.id,
                active_transcript.id,
                section_id,
                summary_type,
            )
            return SlotResult(UNAVAILABLE)
        # 2c — READY (latest-by-generatedAt was already applied by the read query).
        return SlotResult(READY)

    # No generated row for the active transcript. Derive from the projection (steps 3 + 4).
    step = (summary_step_status or "not_started")

    # Step 3 — the summary step itself failed (the success-only-table equivalent of "a failed row").
    if step == "failed":
        return SlotResult(UNAVAILABLE)

    # Step 4a — this summary job is in flight.
    if step in ("queued", "running"):
        return SlotResult(GENERATING)

    # Step 4c — the step reports completed but no success-only row exists (completed-but-missing).
    if step == "completed":
        logger.error(
            "student-summary completed-but-missing artifact: active transcript %s reports %s step "
            "completed but no generated row exists (section=%s, type=%s)",
            active_transcript.id,
            summary_type,
            section_id,
            summary_type,
        )
        return SlotResult(UNAVAILABLE, lecturer_inconsistency=True)

    # step == "not_started":
    # Step 4b — upstream pipeline terminally failed: this summary job will never run.
    if overall_state == "failed":
        return SlotResult(UNAVAILABLE)

    # Step 4a — upstream still progressing toward this summary (not terminally failed) → GENERATING.
    # Shown ONLY when generation is still actually possible (the spec's no-forever-spinner rule).
    return SlotResult(GENERATING)


def derive_section_summaries_state(brief_state: str, detailed_state: str) -> str:
    """§8.1 coarse per-section flag from the two slot states (computed without content)."""
    if brief_state == NOT_APPLICABLE and detailed_state == NOT_APPLICABLE:
        return LIST_NOT_APPLICABLE
    states = (brief_state, detailed_state)
    ready = [s == READY for s in states]
    if all(ready):
        return LIST_READY
    if any(ready):
        return LIST_PARTIAL
    if GENERATING in states:
        return LIST_GENERATING
    return LIST_NONE
