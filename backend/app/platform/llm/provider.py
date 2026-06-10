"""LLMProvider — transport adapter only (spec §6.2/§6.3).

The provider knows about HTTP and authentication and nothing else: no rendering, logging, limiting,
or validation. Two implementations share one Protocol so real and deterministic paths are
behaviorally identical behind the gateway:

- ``K2ThinkProvider`` — real transport. In 4.5a it is a STUB whose ``send`` raises
  ``NotImplementedError`` (the first real call lands in 4.5b, gated on 2.B). It makes no network
  call and imports no HTTP client, so the 4.5a hard gate "no K2Think call exists in the codebase"
  holds by construction.
- ``DeterministicTestProvider`` — returns fixed, schema-conformant output so CI exercises the full
  gateway path at the provider boundary only (rule 11). Carries an E2E-only fault switch.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from typing import Iterator, Protocol

from app.platform.config import settings
from app.platform.llm.errors import ProviderTransient
from app.platform.llm.models.prompt import Backend, RenderedPrompt, Usage

VALID_FAULTS = ("invalid_output", "invalid_input", "provider_transient")


@dataclass(frozen=True)
class RawCompletion:
    text: str
    usage: Usage
    model_id_echoed: str
    provider_request_id: str | None = None
    reasoning_level: str | None = None


class LLMProvider(Protocol):
    def send(self, *, rendered: RenderedPrompt, backend: Backend) -> RawCompletion: ...

    def stream_raw(self, *, rendered: RenderedPrompt, backend: Backend) -> Iterator[str]: ...


def _model_for_backend(backend: Backend) -> str:
    return settings.LLM_BRIEF_MODEL_ID if backend == "cerebras" else settings.LLM_DETAILED_MODEL_ID


def _estimate(text: str) -> int:
    return math.ceil(len(text) / 3.5)


class K2ThinkProvider:
    """Real K2Think transport — STUB until 4.5b. Makes no network call in 4.5a."""

    def __init__(self, *, base_url: str | None = None, api_key: str | None = None) -> None:
        self._base_url = base_url or settings.LLM_PROVIDER_BASE_URL
        self._api_key = api_key  # resolved/verified at 2.B; unused in 4.5a

    def send(self, *, rendered: RenderedPrompt, backend: Backend) -> RawCompletion:
        raise NotImplementedError(
            "K2ThinkProvider.send is a 4.5a stub; the first real K2Think call lands in 4.5b (gate 2.B)"
        )

    def stream_raw(self, *, rendered: RenderedPrompt, backend: Backend) -> Iterator[str]:
        raise NotImplementedError("LLM streaming transport lands in Stage 8.3")


class DeterministicTestProvider:
    """Boundary-only test double. ``fault`` forces a classified failure for E2E gate assertions."""

    def __init__(self, *, fault: str | None = None) -> None:
        if fault is None and settings.IS_NON_PROD:
            fault = os.environ.get("LLM_FAULT_INJECTION") or None
        if fault is not None:
            if not settings.IS_NON_PROD:
                raise RuntimeError("LLM fault injection is forbidden outside non-prod environments")
            if fault not in VALID_FAULTS:
                raise ValueError(f"unknown fault {fault!r}; expected one of {VALID_FAULTS}")
        self.fault = fault

    def send(self, *, rendered: RenderedPrompt, backend: Backend) -> RawCompletion:
        if self.fault == "provider_transient":
            raise ProviderTransient(
                "deterministic provider forced a 5xx", error_code="forced_transient"
            )
        text = self._render_output(rendered)
        completion_tokens = _estimate(text)
        prompt_tokens = _estimate(rendered.content)
        usage: Usage = {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        }
        return RawCompletion(
            text=text,
            usage=usage,
            model_id_echoed=_model_for_backend(backend),
            provider_request_id=f"det-{rendered.rendered_prompt_hash[:16]}",
            reasoning_level=rendered.reasoning_level,
        )

    def stream_raw(self, *, rendered: RenderedPrompt, backend: Backend) -> Iterator[str]:
        raise NotImplementedError("LLM streaming transport lands in Stage 8.3")

    def _render_output(self, rendered: RenderedPrompt) -> str:
        name = rendered.prompt_key.name
        forced_invalid = self.fault == "invalid_output"
        if name == "brief_summary":
            if forced_invalid:
                return json.dumps({"wrong": "shape"})  # missing required `text`
            return json.dumps(
                {
                    "text": (
                        "This session introduced the core ideas of the topic, walked through the "
                        "main definitions and a worked example, and highlighted the points most "
                        "likely to matter for assessment."
                    )
                }
            )
        if name == "detailed_summary":
            payload = {
                "overview": "A structured overview of the session's subject matter.",
                "keyConcepts": ["First key concept", "Second key concept"],
                "importantDefinitions": [
                    {"term": "Term A", "definition": "Definition of term A."}
                ],
                "mainExplanations": ["A full-sentence explanation of a central idea."],
                "examples": ["A worked example demonstrating the idea."],
                "examRelevantPoints": ["A point likely to appear in assessment."],
                "labNotes": ["A procedure or observation note."],
            }
            if forced_invalid:
                payload.pop("examples")  # drop a required section
            return json.dumps(payload)
        raise ValueError(f"deterministic provider has no canned output for prompt {name!r}")


def get_provider() -> LLMProvider:
    if settings.LLM_PROVIDER == "k2think":
        return K2ThinkProvider()
    return DeterministicTestProvider()
