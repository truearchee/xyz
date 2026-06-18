"""LLMProvider — transport adapter only (spec §6.2/§6.3).

The provider knows about HTTP and authentication and nothing else: no rendering, logging, limiting,
or validation. Two implementations share one Protocol so real and deterministic paths are
behaviorally identical behind the gateway:

- ``K2ThinkProvider`` — the real transport (4.5b). One ``send`` is ONE HTTP POST to the OpenAI-shaped
  ``/v1/chat/completions`` endpoint; the model id comes from the rendered prompt (config), never
  hardcoded (rule 11). Every HTTP outcome is mapped to a typed gateway error (§8); the in-call 429
  backoff that turns a transient 429 into multiple POSTs lives in the gateway, not here. Response
  bodies and headers are never put into an exception message — a 4xx carries its status code only
  (§0/§8) so a bad key or a stray header can never reach a log.
- ``DeterministicTestProvider`` — returns fixed, schema-conformant output so CI exercises the full
  gateway path at the provider boundary only. Carries a fault switch covering every §8 outcome so the
  classification + 429 backoff are provable without a network or a real key.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from typing import Iterator, Protocol

import httpx

from app.platform.config import SettingsError, settings
from app.platform.llm.errors import (
    InvalidOutput,
    ProviderAuthError,
    ProviderConfigError,
    ProviderTransient,
    RateLimited,
)
from app.platform.llm.models.prompt import Backend, RenderedPrompt, Usage

VALID_FAULTS = (
    "invalid_output",
    "invalid_input",
    "provider_transient",
    "rate_limited",
    "provider_config",
    "provider_auth",
    "timeout",
)

# Size of the deterministic section-pool fixture (Stage 6a). Within the validator's
# [QUIZ_POOL_MIN_COUNT, QUIZ_POOL_MAX_COUNT] band and mirrors the domain POOL_TARGET so a gate samples a
# realistic pool. Platform must not import domains (rule 8), so it is a local constant kept in sync.
# Trimmed 24→16 alongside POOL_TARGET_SIZE / the prompt's requested count (F-6e live-latency fix).
_DETERMINISTIC_POOL_SIZE = 16

# ── Per-request fault injection (Stage 5b / D-C) ─────────────────────────────────────────────────
# A FIFO sequence the DeterministicTestProvider consults once per ``send()`` (before its constructor
# ``fault``), so a single process can drive inject→clear→succeed — the sequence the global
# ``LLM_FAULT_INJECTION`` flag cannot express, and which the stuck-`generating` recovery paths (S5/S6)
# require to be testable. Safety is AT LEAST as strong as the global flag: it can ONLY affect the
# DeterministicTestProvider (prod uses K2ThinkProvider, see ``get_provider``), AND the setter refuses
# to arm outside non-prod. ``invalid_input`` is excluded — it is a pre-transport gateway fault, not a
# provider-boundary outcome, so it cannot be expressed through ``send()``.
_UNSET = object()
_REQUEST_FAULTS: list[str | None] = []


def set_request_faults(faults: list[str | None]) -> None:
    """Arm a per-request fault sequence (non-prod only). Each entry is a VALID_FAULTS name or None
    (None = this call succeeds normally). Raises outside non-prod — same gate as the global flag."""
    if not settings.IS_NON_PROD:
        raise RuntimeError("LLM fault injection is forbidden outside non-prod environments")
    for fault in faults:
        if fault is None:
            continue
        if fault not in VALID_FAULTS:
            raise ValueError(f"unknown fault {fault!r}; expected one of {VALID_FAULTS} or None")
        if fault == "invalid_input":
            raise ValueError(
                "invalid_input cannot be injected per-request (it is a pre-transport gateway fault)"
            )
    _REQUEST_FAULTS.clear()
    _REQUEST_FAULTS.extend(faults)


def clear_request_faults() -> None:
    _REQUEST_FAULTS.clear()


@dataclass(frozen=True)
class RawCompletion:
    text: str
    usage: Usage
    model_id_echoed: str
    provider_request_id: str | None = None
    reasoning_level: str | None = None
    # HTTP status of the successful transport (200 for the real provider; None for the
    # deterministic double, which makes no HTTP call). Recorded as last_provider_status_code.
    status_code: int | None = None
    # The choice's finish_reason ('stop' | 'length' | …). 'length' means the answer was truncated by
    # max_tokens — important for a reasoning model that spends the budget thinking inline in content.
    finish_reason: str | None = None


class LLMProvider(Protocol):
    def send(self, *, rendered: RenderedPrompt, backend: Backend) -> RawCompletion: ...

    def stream_raw(self, *, rendered: RenderedPrompt, backend: Backend) -> Iterator[str]: ...


def _model_for_backend(backend: Backend) -> str:
    return settings.LLM_BRIEF_MODEL_ID if backend == "cerebras" else settings.LLM_DETAILED_MODEL_ID


def _estimate(text: str) -> int:
    return math.ceil(len(text) / 3.5)


class K2ThinkProvider:
    """Real K2Think transport (4.5b). One ``send`` == one HTTP POST; the gateway owns retries."""

    _CHAT_PATH = "/v1/chat/completions"

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout_seconds: int | None = None,
        detailed_timeout_seconds: int | None = None,
        json_mode: bool | None = None,
    ) -> None:
        self._base_url = (base_url or settings.LLM_PROVIDER_BASE_URL).rstrip("/")
        self._api_key = api_key if api_key is not None else settings.LLM_API_KEY
        if not self._api_key:
            # Required iff LLM_PROVIDER='k2think' (§11). Failing here keeps a keyless real provider
            # from ever issuing a doomed authenticated call.
            raise SettingsError("LLM_API_KEY is required when LLM_PROVIDER='k2think'")
        # Route-aware timeout (F-4.5-49): the detailed (Nvidia) reasoning generation needs materially
        # more wall-clock than brief, so it gets its own (longer) timeout rather than inflating brief.
        self._base_timeout = (
            timeout_seconds
            if timeout_seconds is not None
            else settings.LLM_PROVIDER_TIMEOUT_SECONDS
        )
        self._detailed_timeout = (
            detailed_timeout_seconds
            if detailed_timeout_seconds is not None
            else settings.LLM_DETAILED_TIMEOUT_SECONDS
        )
        self._json_mode = settings.LLM_PROVIDER_JSON_MODE if json_mode is None else json_mode

    def _timeout_for(self, backend: Backend) -> int:
        return self._detailed_timeout if backend == "nvidia" else self._base_timeout

    @property
    def endpoint(self) -> str:
        """Callers never pass a full endpoint — the base url is appended with the chat path (§11)."""
        return f"{self._base_url}{self._CHAT_PATH}"

    def build_payload(self, rendered: RenderedPrompt, *, backend: Backend) -> dict:
        payload: dict = {
            "model": rendered.model_id,  # config (prompt YAML), NEVER a hardcoded id (rule 11)
            "messages": [{"role": "user", "content": rendered.content}],
            "max_tokens": rendered.max_tokens,
            "temperature": 0,
            "stream": False,
        }
        # Routing split (4.5c, Option A / ADR-025): the Nvidia route is requested via
        # metadata.use_nvidia; the Cerebras route is the provider default (no metadata). We control
        # the REQUEST route only — the served backend is not echoed (backend_route_source='requested').
        if backend == "nvidia":
            payload["metadata"] = {"use_nvidia": True}
        # response_format is opt-in until the smoke confirms K2-Think-v2 honors it (§7.1); the
        # tolerant-extract validator is the safety net either way.
        if self._json_mode:
            payload["response_format"] = {"type": "json_object"}
        return payload

    def send(self, *, rendered: RenderedPrompt, backend: Backend) -> RawCompletion:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        try:
            with httpx.Client(timeout=self._timeout_for(backend)) as client:
                response = client.post(
                    self.endpoint,
                    headers=headers,
                    json=self.build_payload(rendered, backend=backend),
                )
        except httpx.TimeoutException:
            raise ProviderTransient(
                "provider request timed out", error_code="provider_timeout", status_code=408
            ) from None
        except httpx.HTTPError:
            # Connection/transport error. No url, headers, or key in the message (§0).
            raise ProviderTransient(
                "provider transport error", error_code="provider_network"
            ) from None

        if response.status_code == 200:
            return self._parse_ok(response)
        raise self._error_for_status(response.status_code)

    @staticmethod
    def _error_for_status(status: int):
        """Map a non-200 status to a typed error. Status code ONLY — no body, no headers (§0/§8)."""
        if status == 400:
            return ProviderConfigError(
                "provider rejected the request (400)",
                error_code="provider_400",
                status_code=400,
            )
        if status in (401, 403):
            return ProviderAuthError(
                f"provider authentication failed ({status})",
                error_code=f"provider_{status}",
                status_code=status,
            )
        if status == 408:
            return ProviderTransient(
                "provider request timed out (408)",
                error_code="provider_408",
                status_code=408,
            )
        if status == 429:
            return RateLimited(
                "provider rate limited (429)", error_code="provider_429", status_code=429
            )
        if 500 <= status < 600:
            return ProviderTransient(
                f"provider server error ({status})",
                error_code=f"provider_{status}",
                status_code=status,
            )
        # Any other 4xx (404/422/…) is a misconfiguration, NOT transient — terminate, don't storm.
        if 400 <= status < 500:
            return ProviderConfigError(
                f"provider rejected the request ({status})",
                error_code=f"provider_{status}",
                status_code=status,
            )
        return ProviderTransient(
            f"unexpected provider status ({status})",
            error_code=f"provider_{status}",
            status_code=status,
        )

    def _parse_ok(self, response: httpx.Response) -> RawCompletion:
        try:
            body = response.json()
        except (json.JSONDecodeError, ValueError):
            raise InvalidOutput(
                "provider returned a non-JSON body", error_code="provider_body_not_json"
            ) from None
        if not isinstance(body, dict):
            raise InvalidOutput(
                "provider body is not a JSON object", error_code="provider_body_not_object"
            )
        try:
            choice = body["choices"][0]
            content = choice["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise InvalidOutput(
                "provider response missing choices/message/content",
                error_code="provider_no_content",
            ) from None
        if not isinstance(content, str) or not content.strip():
            raise InvalidOutput(
                "provider response content is empty", error_code="provider_empty_content"
            )
        request_id = body.get("id")
        finish_reason = choice.get("finish_reason") if isinstance(choice, dict) else None
        return RawCompletion(
            text=content,
            usage=self._usage(body),
            # rule-11 model-ID echo: the live K2-Think-v2 echoes the served model; assertion is LIVE.
            model_id_echoed=str(body.get("model") or ""),
            provider_request_id=str(request_id) if request_id else None,
            # reasoning_content is present-but-null on K2-Think-v2 (F-4.5-04). No confirmed request
            # parameter, so reasoning_level is logged null and NEVER faked.
            reasoning_level=None,
            status_code=200,
            finish_reason=str(finish_reason) if finish_reason else None,
        )

    @staticmethod
    def _usage(body: dict) -> Usage:
        raw = body.get("usage") or {}
        prompt = int(raw.get("prompt_tokens") or 0)
        completion = int(raw.get("completion_tokens") or 0)
        total = int(raw.get("total_tokens") or (prompt + completion))
        return {
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "total_tokens": total,
        }

    def stream_raw(self, *, rendered: RenderedPrompt, backend: Backend) -> Iterator[str]:
        raise NotImplementedError("LLM streaming transport lands in Stage 8.3")


class DeterministicTestProvider:
    """Boundary-only test double. ``fault`` forces a classified failure for gate assertions — one
    fault per §8 outcome so the error map and the in-call 429 backoff are provable without a key."""

    is_deterministic_test_provider = True

    def __init__(self, *, fault: str | None = None) -> None:
        if fault is None and settings.IS_NON_PROD:
            fault = os.environ.get("LLM_FAULT_INJECTION") or None
        if fault is not None:
            if not settings.IS_NON_PROD:
                raise RuntimeError("LLM fault injection is forbidden outside non-prod environments")
            if fault not in VALID_FAULTS:
                raise ValueError(f"unknown fault {fault!r}; expected one of {VALID_FAULTS}")
        self.fault = fault

    def _resolve_active_fault(self) -> str | None:
        # A per-request fault (non-prod only) takes precedence over the constructor fault, popped once.
        if settings.IS_NON_PROD and _REQUEST_FAULTS:
            return _REQUEST_FAULTS.pop(0)
        return self.fault

    def send(self, *, rendered: RenderedPrompt, backend: Backend) -> RawCompletion:
        active_fault = self._resolve_active_fault()
        self._maybe_raise_transport_fault(active_fault)
        text = self._render_output(rendered, active_fault)
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

    def _maybe_raise_transport_fault(self, fault: object = _UNSET) -> None:
        # ``invalid_input`` is raised by the gateway (before transport); ``invalid_output`` is a
        # wrong-shaped success body. Everything else is a transport-boundary outcome (§8).
        active = self.fault if fault is _UNSET else fault
        if active == "provider_transient":
            raise ProviderTransient(
                "deterministic provider forced a 5xx", error_code="forced_transient", status_code=503
            )
        if active == "timeout":
            raise ProviderTransient(
                "deterministic provider forced a timeout", error_code="forced_timeout", status_code=408
            )
        if active == "rate_limited":
            raise RateLimited(
                "deterministic provider forced a 429", error_code="forced_429", status_code=429
            )
        if active == "provider_config":
            raise ProviderConfigError(
                "deterministic provider forced a 400", error_code="forced_400", status_code=400
            )
        if active == "provider_auth":
            raise ProviderAuthError(
                "deterministic provider forced a 403", error_code="forced_403", status_code=403
            )

    def stream_raw(self, *, rendered: RenderedPrompt, backend: Backend) -> Iterator[str]:
        raise NotImplementedError("LLM streaming transport lands in Stage 8.3")

    def _render_output(self, rendered: RenderedPrompt, fault: object = _UNSET) -> str:
        name = rendered.prompt_key.name
        active = self.fault if fault is _UNSET else fault
        forced_invalid = active == "invalid_output"
        if name == "post_class_quiz_generation":
            return self._quiz_fixture(forced_invalid)
        if name == "quiz_pool_generation":
            return self._pool_fixture(forced_invalid)
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

    @staticmethod
    def _quiz_fixture(forced_invalid: bool) -> str:
        """A schema-valid 10-question quiz with KNOWN correct options (option A correct in every
        question), so a deterministic E2E can reach 100% (always pick the is_correct option, resolved
        from the DB) and craft specific wrong answers. ``forced_invalid`` drops a question so the
        validator's exactly-10 rule fires (validator/retry test)."""
        questions = [
            {
                "questionText": f"Deterministic question {i + 1}: which option is correct?",
                "options": [
                    {"text": f"Q{i + 1} option A (correct)", "isCorrect": True},
                    {"text": f"Q{i + 1} option B", "isCorrect": False},
                    {"text": f"Q{i + 1} option C", "isCorrect": False},
                    {"text": f"Q{i + 1} option D", "isCorrect": False},
                ],
                "explanation": f"Option A is the correct answer for question {i + 1}.",
            }
            for i in range(10)
        ]
        if forced_invalid:
            questions.pop()  # 9 questions → fails the exactly-10 validator rule
        return json.dumps({"questions": questions})

    @staticmethod
    def _pool_fixture(forced_invalid: bool) -> str:
        """A schema-valid section POOL with KNOWN correct options (option A correct in every question).

        ``_DETERMINISTIC_POOL_SIZE`` questions (within the validator's [min, max] band) so a gate can
        deterministically sample, snapshot, and resolve correctness from the DB. Questions are numbered so
        a seeded sampler's selection is observable and reproducible. ``forced_invalid`` returns too few
        questions so the pool count rule fires (validator/retry test)."""
        questions = [
            {
                "questionText": f"Pool question {i + 1}: which option is correct?",
                "options": [
                    {"text": f"Pool Q{i + 1} option A (correct)", "isCorrect": True},
                    {"text": f"Pool Q{i + 1} option B", "isCorrect": False},
                    {"text": f"Pool Q{i + 1} option C", "isCorrect": False},
                    {"text": f"Pool Q{i + 1} option D", "isCorrect": False},
                ],
                "explanation": f"Option A is the correct answer for pool question {i + 1}.",
            }
            for i in range(_DETERMINISTIC_POOL_SIZE)
        ]
        if forced_invalid:
            questions = questions[:5]  # below QUIZ_POOL_MIN_COUNT → fails the pool count rule
        return json.dumps({"questions": questions})


def get_provider() -> LLMProvider:
    if settings.LLM_PROVIDER == "k2think":
        return K2ThinkProvider()
    return DeterministicTestProvider()
