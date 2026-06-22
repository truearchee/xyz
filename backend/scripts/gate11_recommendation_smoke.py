"""Stage 11.2 — real-provider smoke for recommendation copy (synthetic payload only).

Makes ONE real authenticated call through the production K2Think transport on the recommendation_copy
route, then validates with the production schema and recommendation copy validators. Proves the call is
REAL and that rule 11 holds: the echoed model id equals the CONFIGURED identifier
(``MBZUAI-IFM/K2-Think-v2``), not a silent deployment alias.

Security: the key is read from env and NEVER printed. No Authorization header, request body, key, or
generated recommendation text is emitted — only redacted evidence + PASS/FAIL. The input is a
SYNTHETIC deterministic analytics payload (no real student or course data is sent to IFM).

Usage (operator shell, with a REAL LLM_API_KEY exported or in .env):
    docker compose run --rm -e LLM_PROVIDER=k2think -v "$PWD/backend:/app" -T backend \
        python scripts/gate11_recommendation_smoke.py
"""

from __future__ import annotations

import json
import time
from uuid import UUID

from app.domains.analytics import recommendations
from app.platform.config import settings
from app.platform.llm.errors import GatewayError, ProviderAuthError, ProviderConfigError
from app.platform.llm.models.prompt import PromptKey
from app.platform.llm.models.recommendation import RecommendationCopy
from app.platform.llm.provider import K2ThinkProvider
from app.platform.llm.registry import get_prompt_registry
from app.platform.llm.validation import OutputValidator

RECOMMENDATION_KEY = PromptKey(
    recommendations.RECOMMENDATION_COPY_PROMPT_NAME,
    recommendations.RECOMMENDATION_COPY_PROMPT_VERSION,
)
SYNTHETIC_MODULE_ID = UUID("20000000-0000-4000-8000-000000001102")
SYNTHETIC_REASON = {
    "code": "low_recent_quiz_score",
    "severity": "watch",
    "metricKeys": ["recentQuizAverage", "completedAttemptCount"],
    "supportingMetrics": {
        "recentQuizAverage": 62,
        "completedAttemptCount": 3,
    },
    "lecturerText": "Recent quiz practice averaged 62% across 3 completed attempts",
    "studentText": "Recent quiz practice shows that a focused review could help",
}


def _deterministic_payload() -> dict:
    payload = recommendations.build_deterministic_payload(
        reason=SYNTHETIC_REASON,
        module_id=SYNTHETIC_MODULE_ID,
        target_key=f"module:{SYNTHETIC_MODULE_ID}",
        target_label="Biology 101",
    )
    # Real models may spell small numerals as words; these are the same deterministic facts, not new
    # numbers. Including both forms makes the smoke test the AI path instead of forcing template fallback.
    payload["allowedNumbers"] = sorted(
        set(payload["allowedNumbers"]) | {"three", "sixty", "two"}
    )
    return payload


def _prompt_blob(payload: dict) -> str:
    return json.dumps(
        {
            "deterministicPayload": payload,
            "contract": {
                "noNumbersOutsideAllowedNumbers": True,
                "noPeerComparisons": True,
                "noDiagnoses": True,
                "noNewRiskReasons": True,
                "studentTone": "gentle, calm, no risk labels, no shame",
            },
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def main() -> int:
    if settings.LLM_PROVIDER != "k2think":
        print("FAIL: LLM_PROVIDER must be 'k2think' (export it before running the smoke).")
        return 2
    if not settings.LLM_API_KEY or settings.LLM_API_KEY.startswith("your-"):
        print("FAIL: LLM_API_KEY is not a real key in this environment (still the .env placeholder).")
        return 2

    provider = K2ThinkProvider()
    validator = OutputValidator()
    registry = get_prompt_registry()
    payload = _deterministic_payload()
    print("Stage 11.2 — recommendation copy real-provider smoke (synthetic payload; secrets REDACTED)\n")

    rendered = registry.render(
        RECOMMENDATION_KEY,
        transcript=_prompt_blob(payload),
        section_type="recommendation",
    )
    expected_model = rendered.model_id
    backend = rendered.backend
    try:
        started = time.monotonic()
        raw = provider.send(rendered=rendered, backend=backend)
        elapsed_s = time.monotonic() - started
        parsed: RecommendationCopy = validator.validate(
            raw_text=raw.text,
            output_schema=RecommendationCopy,
            section_type="recommendation",
        )
        recommendations.validate_recommendation_copy(
            parsed,
            context=recommendations.validation_context(payload),
        )
    except ProviderAuthError:
        print("FAIL: provider auth error (401/403) — key not valid? Body redacted.")
        return 1
    except ProviderConfigError:
        print("FAIL: provider config error (4xx) — model id/request misconfigured? Body redacted.")
        return 1
    except GatewayError as exc:
        print(f"FAIL: {type(exc).__name__} ({exc.error_code}) — output did not validate or transport failed.")
        return 1

    echo_ok = raw.model_id_echoed == expected_model
    print(f"--- {RECOMMENDATION_KEY} (route {backend}) ---")
    print(
        f"  response model echo : {raw.model_id_echoed}  "
        f"(expected {expected_model})  -> {'OK' if echo_ok else 'MISMATCH'}"
    )
    print(f"  backend_used        : {backend}")
    print(f"  finish_reason       : {raw.finish_reason!r}")
    print(f"  elapsed             : {elapsed_s:.1f}s")
    print(
        "  usage               : "
        f"prompt={raw.usage['prompt_tokens']} "
        f"completion={raw.usage['completion_tokens']} "
        f"total={raw.usage['total_tokens']}"
    )
    print(f"  status_code         : {raw.status_code}")
    print(
        "  parseable           : YES "
        f"(RecommendationCopy, lecturer {len(parsed.lecturer_draft.strip())} chars, "
        f"student {len(parsed.student_nudge.strip())} chars)"
    )
    print("  validators          : YES (numeric consistency + student-copy safety)")
    print()
    if echo_ok:
        print("PASS: recommendation route returned the configured model id (rule 11) and safe parseable copy.")
        return 0
    print("FAIL: model-ID echo MISMATCH — STOP, do not stamp (rule 11 caught a deployment/alias problem).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
