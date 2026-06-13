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

# Brief-from-detailed (4.5.1b, ADR-052): the brief is derived from the COMPLETED detailed summary in one
# small call (BRIEF route), NOT re-summarized from the transcript. SINGLE source of truth, imported by
# summary_service. The legacy BRIEF.prompt_key (brief_summary/v2) remains the transcript-based fallback
# used only when ENABLE_DETAILED_SUMMARY is off (OB1 — a degraded, truncated, non-quiz-eligible mode).
BRIEF_FROM_DETAILED_PROMPT_KEY = PromptKey("brief_from_detailed", "v1")
BRIEF_FROM_DETAILED_FEATURE: SummaryFeature = "brief_from_detailed"

# Accepted prompt versions per summary_type — the activation/eligibility layer requires the stored
# summary row to match a CURRENT prompt version for the active transcript (ADR-46-A §3.3). A TUPLE
# (accept-set) because a type can legitimately carry more than one current producing-prompt version:
#  - brief: the brief-from-detailed prompt (the default mode-A) OR the transcript-based fallback used
#    when detailed is disabled (mode-B). Both are "current"; prompt_version stays the true producing
#    prompt's version (no contract-version stamping). A future bump drops the old version from the set.
#  - detailed: the REDUCE prompt (the artifact-producing call of the map-reduce DAG; the map prompt
#    version lives in generationMetadata — strategy-aware quiz gating is is_full_coverage_detailed).
EXPECTED_PROMPT_VERSION_BY_SUMMARY_TYPE: dict[str, tuple[str, ...]] = {
    BRIEF.summary_type: (BRIEF_FROM_DETAILED_PROMPT_KEY.version, BRIEF.prompt_key.version),
    DETAILED.summary_type: (REDUCE_PROMPT_KEY.version,),
}
