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
    prompt_key=PromptKey("brief_summary", "v1"),
    output_schema=BriefSummary,
    summary_type="brief",
    content_schema_version=BRIEF_SCHEMA_VERSION,
)
DETAILED = SummarySpec(
    job_type="generate_detailed_summary",
    feature="summary_detailed",
    prompt_key=PromptKey("detailed_summary", "v1"),
    output_schema=DetailedSummary,
    summary_type="detailed_study",
    content_schema_version=DETAILED_SCHEMA_VERSION,
)
SUMMARY_SPECS: dict[str, SummarySpec] = {BRIEF.job_type: BRIEF, DETAILED.job_type: DETAILED}
SUMMARY_JOB_TYPES = tuple(SUMMARY_SPECS)

# Expected prompt version per summary_type — the activation/eligibility layer requires the stored
# summary row to match the current prompt version for the active transcript (ADR-46-A §3.3).
EXPECTED_PROMPT_VERSION_BY_SUMMARY_TYPE: dict[str, str] = {
    BRIEF.summary_type: BRIEF.prompt_key.version,
    DETAILED.summary_type: DETAILED.prompt_key.version,
}
