"""Stage 11.6 — real-provider smoke for grade-forecast advice (synthetic payload only).

Makes real authenticated calls through the production K2Think transport on the grade_forecast_advice
route, then validates with the production schema + the numeric/contradiction + student-copy-safety
validators. Proves the call is REAL and that rule 11 holds: the echoed model id equals the CONFIGURED
identifier (``MBZUAI-IFM/K2-Think-v2``), not a silent deployment alias.

Security: the key is read from env and NEVER printed. No Authorization header, request body, key, or
generated advice text is emitted — only redacted evidence + PASS/FAIL. The inputs are SYNTHETIC
deterministic forecast payloads (no real student or course data is sent to IFM).

Usage (operator shell, with a REAL LLM_API_KEY exported or in .env):
    docker compose run --rm -e LLM_PROVIDER=k2think -v "$PWD/backend:/app" -T backend \
        python scripts/gate11_advice_smoke.py
"""

from __future__ import annotations

import time
from decimal import Decimal

from app.domains.analytics import forecast_advice
from app.domains.progress.forecast import ForecastResult
from app.platform.config import settings
from app.platform.llm.errors import GatewayError, ProviderAuthError, ProviderConfigError
from app.platform.llm.models.forecast_advice import GradeForecastAdvice
from app.platform.llm.models.prompt import PromptKey
from app.platform.llm.provider import K2ThinkProvider
from app.platform.llm.registry import get_prompt_registry
from app.platform.llm.validation import OutputValidator

ADVICE_KEY = PromptKey(forecast_advice.ADVICE_PROMPT_NAME, forecast_advice.ADVICE_PROMPT_VERSION)
MODULE_TITLE = "Biology 101"

# requires_high_score: 4/5 @ 93.75 → earned 75, remaining 0.2, max 95, required average 90.
REACHABLE = ForecastResult(
    state="requires_high_score",
    target_letter_grade="A",
    target_points=Decimal("93"),
    earned_so_far=Decimal("75"),
    remaining_weight=Decimal("0.2"),
    min_reachable=Decimal("75"),
    max_reachable=Decimal("95"),
    current_letter_grade="C",
    best_reachable_letter_grade="A",
    required_remaining_average=Decimal("90"),
)
# impossible: 4/5 @ 82.50 → earned 66, remaining 0.2, max 86 < 93, best B+.
IMPOSSIBLE = ForecastResult(
    state="impossible",
    target_letter_grade="A",
    target_points=Decimal("93"),
    earned_so_far=Decimal("66"),
    remaining_weight=Decimal("0.2"),
    min_reachable=Decimal("66"),
    max_reachable=Decimal("86"),
    current_letter_grade="F",
    best_reachable_letter_grade="B+",
    required_remaining_average=Decimal("135"),
)


# K2-Think reasons inline in `content` with no request-level reasoning control and variable trace
# length, so a single call can occasionally truncate/return non-JSON. Production already retries twice
# then falls back to the deterministic template; the smoke mirrors that retry to prove the route can
# produce valid, validated advice (rule 11 is about the route + model-ID echo, not one-shot luck).
SMOKE_MAX_ATTEMPTS = 3


def _run_case(label: str, forecast: ForecastResult, provider: K2ThinkProvider, validator: OutputValidator) -> bool:
    registry = get_prompt_registry()
    payload = forecast_advice.build_deterministic_payload(forecast, module_title=MODULE_TITLE)
    rendered = registry.render(
        ADVICE_KEY,
        transcript=forecast_advice.advice_prompt_blob(payload),
        section_type=forecast_advice.ADVICE_SECTION_TYPE,
    )
    expected_model = rendered.model_id
    backend = rendered.backend
    raw = None
    parsed: GradeForecastAdvice | None = None
    elapsed_s = 0.0
    attempts = 0
    last_error: str | None = None
    for attempts in range(1, SMOKE_MAX_ATTEMPTS + 1):
        try:
            started = time.monotonic()
            raw = provider.send(rendered=rendered, backend=backend)
            elapsed_s = time.monotonic() - started
            parsed = validator.validate(
                raw_text=raw.text,
                output_schema=GradeForecastAdvice,
                section_type=forecast_advice.ADVICE_SECTION_TYPE,
            )
            forecast_advice.validate_forecast_advice(
                parsed,
                context=forecast_advice.advice_validation_context(payload),
            )
            break
        except ProviderAuthError:
            print(f"FAIL [{label}]: provider auth error (401/403) — key not valid? Body redacted.")
            return False
        except ProviderConfigError:
            print(f"FAIL [{label}]: provider config error (4xx) — model id/request misconfigured? Body redacted.")
            return False
        except GatewayError as exc:
            last_error = f"{type(exc).__name__} ({exc.error_code})"
            parsed = None
            continue
    if parsed is None or raw is None:
        print(f"FAIL [{label}]: {last_error} after {SMOKE_MAX_ATTEMPTS} attempts — output did not validate or transport failed.")
        return False

    echo_ok = raw.model_id_echoed == expected_model
    print(f"--- {ADVICE_KEY} [{label}: {forecast.state}] (route {backend}) ---")
    print(
        f"  response model echo : {raw.model_id_echoed}  "
        f"(expected {expected_model})  -> {'OK' if echo_ok else 'MISMATCH'}"
    )
    print(f"  finish_reason       : {raw.finish_reason!r}")
    print(f"  attempts            : {attempts}/{SMOKE_MAX_ATTEMPTS}")
    print(f"  elapsed             : {elapsed_s:.1f}s")
    print(
        "  usage               : "
        f"prompt={raw.usage['prompt_tokens']} "
        f"completion={raw.usage['completion_tokens']} "
        f"total={raw.usage['total_tokens']}"
    )
    print(f"  status_code         : {raw.status_code}")
    print(f"  parseable           : YES (GradeForecastAdvice, {len(parsed.advice.strip())} chars)")
    print("  validators          : YES (numeric consistency + contradiction + student-copy safety)")
    print()
    return echo_ok


def main() -> int:
    if settings.LLM_PROVIDER != "k2think":
        print("FAIL: LLM_PROVIDER must be 'k2think' (export it before running the smoke).")
        return 2
    if not settings.LLM_API_KEY or settings.LLM_API_KEY.startswith("your-"):
        print("FAIL: LLM_API_KEY is not a real key in this environment (still the .env placeholder).")
        return 2

    provider = K2ThinkProvider()
    validator = OutputValidator()
    print("Stage 11.6 — grade-forecast advice real-provider smoke (synthetic payloads; secrets REDACTED)\n")

    results = [
        _run_case("reachable", REACHABLE, provider, validator),
        _run_case("impossible", IMPOSSIBLE, provider, validator),
    ]
    if all(results):
        print("PASS: advice route returned the configured model id (rule 11) and safe, validated advice.")
        return 0
    print("FAIL: model-ID echo MISMATCH or validation failure — STOP, do not stamp (rule 11/validators).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
