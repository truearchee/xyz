"""Summary job specifications (brief / detailed_study).

Extracted from ``summary_service`` so the lightweight eligibility/activation layer
(``summary_eligibility``, ``activation``) can read the expected prompt versions and job types WITHOUT
importing the gateway-heavy ``summary_service`` (which would create an import cycle once
``summary_service`` triggers activation). Pure data — no DB, no gateway, no side effects.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.platform.llm.models.prompt import PromptKey, SummaryFeature
from app.platform.llm.models.summary import (
    BRIEF_SCHEMA_VERSION,
    DETAILED_SCHEMA_VERSION,
    BriefSummary,
    DetailedSummary,
)


@dataclass(frozen=True)
class SummarySpec:
    job_type: str
    feature: SummaryFeature
    prompt_key: PromptKey
    output_schema: type[BriefSummary] | type[DetailedSummary]
    summary_type: str
    content_schema_version: str


BRIEF = SummarySpec(
    job_type="generate_brief_summary",
    feature="summary_brief",
    prompt_key=PromptKey("brief_summary", "v2"),  # v2: transcript truncated to budget (F-4.5-50)
    output_schema=BriefSummary,
    summary_type="brief",
    content_schema_version=BRIEF_SCHEMA_VERSION,
)
DETAILED = SummarySpec(
    job_type="generate_detailed_summary",
    feature="summary_detailed",
    prompt_key=PromptKey("detailed_summary", "v2"),  # v2: transcript truncated to budget (F-4.5-50)
    output_schema=DetailedSummary,
    summary_type="detailed_study",
    content_schema_version=DETAILED_SCHEMA_VERSION,
)
SUMMARY_SPECS: dict[str, SummarySpec] = {BRIEF.job_type: BRIEF, DETAILED.job_type: DETAILED}
SUMMARY_JOB_TYPES = tuple(SUMMARY_SPECS)

# Map-reduce prompt keys (4.5.1a, F-4.5-51) — SINGLE source of truth, imported by map_reduce.py so the
# engine and the eligibility expectation below can never drift. Detailed is now produced by map → reduce;
# the DETAILED.prompt_key above is the legacy single-call prompt, retained only for the processor_version
# label and not used to generate.
MAP_PROMPT_KEY = PromptKey("detailed_summary_map", "v1")
REDUCE_PROMPT_KEY = PromptKey("detailed_summary_reduce", "v1")

# Expected prompt version per summary_type — the activation/eligibility layer requires the stored
# summary row to match the current prompt version for the active transcript (ADR-46-A §3.3). The
# persisted GeneratedLectureSummary.prompt_version comes from the artifact-producing AIRequestLog: the
# brief's own call for brief, and the REDUCE call for the map-reduce detailed summary — so detailed
# expects the reduce version (the map prompt version lives in generationMetadata; strategy-aware gating
# is Stage 4.5.1b).
EXPECTED_PROMPT_VERSION_BY_SUMMARY_TYPE: dict[str, str] = {
    BRIEF.summary_type: BRIEF.prompt_key.version,
    DETAILED.summary_type: REDUCE_PROMPT_KEY.version,
}
