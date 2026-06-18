from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypedDict

Backend = Literal["cerebras", "nvidia"]
Priority = Literal["interactive", "background"]
# Widened by addition (Stage 5b → 6a → 7 → 8.1): the gateway serves more than summaries now. The summary
# members are unchanged; ``post_class_quiz`` (5b), ``quiz_pool`` (6a, per-section pool generation),
# ``glossary_definition`` (Stage 7), and ``assistant`` (8.1, interactive study-assistant chat) are added.
# ``GatewayFeature`` is the canonical name for new code; ``SummaryFeature`` stays as a back-compatible
# alias so existing summary call sites are untouched. Mirrors the enumerated ai_request_logs.feature CHECK.
GatewayFeature = Literal[
    "summary_brief",
    "summary_detailed",
    "post_class_quiz",
    "quiz_pool",
    "glossary_definition",
    "assistant",
]
SummaryFeature = GatewayFeature
# Features that MUST carry an ingestion_job_id (transcript-ingestion-bound calls). Enforced at the
# application layer by the gateway — the DB column is nullable (0020) but the summary contract is not.
FEATURES_REQUIRING_INGESTION_JOB: frozenset[str] = frozenset(
    {"summary_brief", "summary_detailed"}
)


class Usage(TypedDict):
    """Token usage reconciled from the provider response."""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass(frozen=True)
class PromptKey:
    """Lookup key into the PromptRegistry."""

    name: str
    version: str

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.name}/{self.version}"


@dataclass(frozen=True)
class RenderedPrompt:
    """A prompt template fully rendered with its variables.

    ``backend``/``model_id`` are the prompt's *declared* defaults; ContextBuilder may select a
    fallback route, in which case the gateway records the effective backend/model on the log row.
    """

    prompt_key: PromptKey
    model_id: str
    backend: Backend
    max_tokens: int
    reasoning_level: str | None
    content: str
    prompt_content_hash: str
    rendered_prompt_hash: str
