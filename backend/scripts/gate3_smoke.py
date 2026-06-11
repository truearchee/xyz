"""Stage 4.5d — Gate 3 full-stage real-provider smoke (synthetic transcript only).

Makes ONE real authenticated call per route through the production K2Think transport
(``K2ThinkProvider`` — the exact adapter the gateway uses), then validates the output with the
production ``OutputValidator``. Proves the call is REAL: the rule-11 model-ID echo, token usage,
reasoning level, and a parseable BriefSummary / DetailedSummary.

Security: the API key is read from the environment and NEVER printed. No Authorization header, no
request body, no key, and no transcript text is emitted — only redacted evidence + PASS/FAIL.
Run it via a throwaway container that receives the key from your shell (see the close-out runbook);
nothing is persisted.

Usage (operator shell, with LLM_API_KEY exported):
    docker compose run --rm \
      -e LLM_PROVIDER=k2think -e LLM_API_KEY="$LLM_API_KEY" \
      -e LLM_PROVIDER_BASE_URL="${LLM_PROVIDER_BASE_URL:-https://api.k2think.ai}" \
      -e LLM_CONTEXT_FALLBACK_ENABLED=false -e ENABLE_DETAILED_SUMMARY=true \
      -v "$PWD/backend:/app" -w /app backend python scripts/gate3_smoke.py
"""

from __future__ import annotations

import sys
import time

from app.platform.config import settings
from app.platform.llm.errors import GatewayError, ProviderAuthError, ProviderConfigError
from app.platform.llm.models.summary import BriefSummary, DetailedSummary
from app.platform.llm.provider import K2ThinkProvider
from app.platform.llm.registry import PromptKey, get_prompt_registry
from app.platform.llm.validation import OutputValidator

# A SHORT SYNTHETIC transcript — no real student / uploaded / production data is sent to IFM. Sized to
# a realistic lecture (~320 words) so brief + detailed both produce valid-length, well-sectioned output.
SYNTHETIC_TRANSCRIPT = (
    "Okay, can everyone hear me at the back? Great, let's begin. Today's lecture is an introduction "
    "to supervised learning, one of the central paradigms in machine learning. In supervised "
    "learning we are given a dataset of labelled examples; each example pairs an input with a known "
    "correct output, and the goal is to learn a function that maps inputs to outputs and generalises "
    "to new, unseen inputs. The central object is the loss function. A loss function measures how "
    "wrong a single prediction is compared with the true label; common choices are squared error for "
    "regression and cross-entropy for classification. Training is the process of adjusting the "
    "model's parameters to minimise the average loss over the training set, usually by gradient "
    "descent, which repeatedly steps the parameters in the direction that most reduces the loss. A "
    "crucial concept is overfitting: a model overfits when it fits the training data extremely well, "
    "even its noise, yet performs poorly on unseen data because it has memorised rather than "
    "generalised. We diagnose it by comparing training error with validation error, where a large "
    "gap signals overfitting. As a worked example, consider fitting a straight line to noisy points "
    "by least squares: we choose the slope and intercept that minimise the sum of squared residuals, "
    "which has a closed-form solution. To combat overfitting we use regularisation, which penalises "
    "large parameter values and trades a little training accuracy for better generalisation. For the "
    "exam you should be able to define the loss function, explain the difference between training "
    "error and generalisation error, describe gradient descent in words, and state why regularisation "
    "helps. That's all for today; the reading is chapter three, and next week we turn to classification."
)

BRIEF_KEY = PromptKey("brief_summary", "v1")
DETAILED_KEY = PromptKey("detailed_summary", "v1")


def _run_route(provider: K2ThinkProvider, validator: OutputValidator, *, key, backend, schema, section_type):
    registry = get_prompt_registry()
    rendered = registry.render(key, transcript=SYNTHETIC_TRANSCRIPT, section_type=section_type)
    started = time.monotonic()
    raw = provider.send(rendered=rendered, backend=backend)  # ONE real authenticated POST
    elapsed_s = time.monotonic() - started
    parsed = validator.validate(raw_text=raw.text, output_schema=schema, section_type=section_type)
    expected_model = rendered.model_id
    echo_ok = raw.model_id_echoed == expected_model
    usage = raw.usage
    print(f"--- {key} (route {backend}) ---")
    print(f"  response model echo : {raw.model_id_echoed}  (expected {expected_model})  -> {'OK' if echo_ok else 'MISMATCH'}")
    print(f"  backend_used        : {backend}")
    print(f"  backend_route_source: requested")
    print(f"  finish_reason       : {raw.finish_reason!r}  ('length' = truncated by max_tokens; 'stop' = complete)")
    print(f"  elapsed             : {elapsed_s:.1f}s  (timeout for this route = {provider._timeout_for(backend)}s)")
    print(f"  usage               : prompt={usage['prompt_tokens']} completion={usage['completion_tokens']} total={usage['total_tokens']}")
    print(f"  reasoning_level     : {raw.reasoning_level!r}  (present-but-null on K2-Think-v2 → logged null, never faked)")
    print(f"  status_code         : {raw.status_code}")
    print(f"  parseable           : YES ({type(parsed).__name__})")
    return echo_ok


def _probe_response_format(validator: OutputValidator) -> None:
    """Lever check (§7): does K2-Think-v2 honor response_format={'type':'json_object'}? If so, content
    is a single clean JSON object (no inline reasoning to extract around) and we can flip the default
    LLM_PROVIDER_JSON_MODE on. Informational — does not affect PASS/FAIL of the prompt-only path."""
    print("--- response_format probe (brief route, json_object mode) ---")
    try:
        json_provider = K2ThinkProvider(json_mode=True)
        rendered = get_prompt_registry().render(BRIEF_KEY, transcript=SYNTHETIC_TRANSCRIPT, section_type="lecture")
        raw = json_provider.send(rendered=rendered, backend="cerebras")
        validator.validate(raw_text=raw.text, output_schema=BriefSummary, section_type="lecture")
        print(f"  HONORED: finish_reason={raw.finish_reason!r}, content_length={len(raw.text)}, parseable=YES")
        print("  -> response_format is honored; LLM_PROVIDER_JSON_MODE=true can be set as default.")
    except ProviderConfigError:
        print("  NOT HONORED: 400 on response_format -> stay prompt-only (LLM_PROVIDER_JSON_MODE=false).")
    except Exception as exc:  # noqa: BLE001 - informational probe; never fails the gate
        print(f"  INCONCLUSIVE: {type(exc).__name__} -> rely on prompt-only + last-valid extractor + max_tokens.")


def main() -> int:
    if settings.LLM_PROVIDER != "k2think":
        print("FAIL: LLM_PROVIDER must be 'k2think' (export it before running Gate 3).")
        return 2
    if not settings.LLM_API_KEY:
        print("FAIL: LLM_API_KEY is not set in this environment (rotate + export the key).")
        return 2

    provider = K2ThinkProvider()  # reads base url + key from settings; key never printed
    validator = OutputValidator()
    print("Stage 4.5d Gate 3 — real-provider smoke (synthetic transcript; secrets REDACTED)\n")

    try:
        brief_ok = _run_route(
            provider, validator, key=BRIEF_KEY, backend="cerebras",
            schema=BriefSummary, section_type="lecture",
        )
        detailed_ok = _run_route(
            provider, validator, key=DETAILED_KEY, backend="nvidia",
            schema=DetailedSummary, section_type="lecture",
        )
    except ProviderAuthError:
        print("\nFAIL: provider auth error (401/403) — key not rotated/valid? Body redacted.")
        return 1
    except ProviderConfigError:
        print("\nFAIL: provider config error (4xx) — model id / request misconfigured? Body redacted.")
        return 1
    except GatewayError as exc:
        print(f"\nFAIL: {type(exc).__name__} ({exc.error_code}) — output did not validate or transport failed.")
        return 1

    _probe_response_format(validator)

    print()
    if brief_ok and detailed_ok:
        print("PASS: both routes returned the configured model id (rule 11) and parseable summaries.")
        return 0
    print("FAIL: model-ID echo MISMATCH on a route — STOP, do not stamp (rule 11 caught a deployment/alias problem).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
