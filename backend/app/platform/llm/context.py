"""ContextBuilder — token budget + route selection (spec §3-D2, §9, adr-025).

D2: a conservative over-counting prompt-token estimator (``chars / 3.5``). tiktoken's o200k_base
may replace this later only if it over-estimates on real transcript samples; until then the simple
estimator avoids a heavy dependency and is intentionally pessimistic.

Routing (D3 — no truncation, ever): a request fits a backend when
``estimated_prompt_tokens + max_tokens <= context_window``. A brief (declared Cerebras) falls back
to Nvidia only when it exceeds the Cerebras window; if it also exceeds Nvidia → ``InvalidInput``.
A detailed summary (declared Nvidia) has no fallback.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from app.platform.config import settings
from app.platform.llm.errors import InvalidInput
from app.platform.llm.models.prompt import Backend, RenderedPrompt

CHARS_PER_TOKEN = 3.5


def estimate_tokens(text: str) -> int:
    """Conservative prompt-token over-estimate (D2)."""
    return math.ceil(len(text) / CHARS_PER_TOKEN)


def context_window(backend: Backend) -> int:
    if backend == "cerebras":
        return settings.LLM_CEREBRAS_CONTEXT_WINDOW_TOKENS
    return settings.LLM_NVIDIA_CONTEXT_WINDOW_TOKENS


def model_for_backend(backend: Backend) -> str:
    if backend == "cerebras":
        return settings.LLM_BRIEF_MODEL_ID
    return settings.LLM_DETAILED_MODEL_ID


@dataclass(frozen=True)
class FitResult:
    backend: Backend
    model_id: str
    estimated_prompt_tokens: int
    reserved_tokens: int
    fell_back: bool


class ContextBuilder:
    def fit(self, rendered: RenderedPrompt, *, estimated_prompt_tokens: int | None = None) -> FitResult:
        est = (
            estimated_prompt_tokens
            if estimated_prompt_tokens is not None
            else estimate_tokens(rendered.content)
        )
        reserved = est + rendered.max_tokens
        declared = rendered.backend

        if reserved <= context_window(declared):
            return FitResult(declared, model_for_backend(declared), est, reserved, fell_back=False)

        # Brief (Cerebras) falls back to Nvidia only on over-context (adr-025) — and only when the
        # fallback is enabled. Under the single-model 4.5b deviation the two routes are NOT proven to
        # share a context window, so the fallback is disabled: an over-limit prompt becomes
        # invalid_input rather than silently rerouting onto an unverified window (§12, F-4.5-37). The
        # mechanism stays here, dormant, and reactivates when the dual-model split returns.
        if (
            settings.LLM_CONTEXT_FALLBACK_ENABLED
            and declared == "cerebras"
            and reserved <= context_window("nvidia")
        ):
            return FitResult("nvidia", model_for_backend("nvidia"), est, reserved, fell_back=True)

        raise InvalidInput(
            f"prompt over context window: estimated {est} prompt tokens + {rendered.max_tokens} "
            f"reserved completion = {reserved}; no backend can serve it",
            error_code="over_context",
        )
