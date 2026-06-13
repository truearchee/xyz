from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypedDict

Backend = Literal["cerebras", "nvidia"]
Priority = Literal["interactive", "background"]
# `detailed_summary_map` / `detailed_summary_reduce` are the map-reduce phases (4.5.1a, F-4.5-51);
# `brief_from_detailed` is the 4.5.1b DAG change (the brief derived from the completed detailed).
SummaryFeature = Literal[
    "summary_brief",
    "summary_detailed",
    "detailed_summary_map",
    "detailed_summary_reduce",
    "brief_from_detailed",
]


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
