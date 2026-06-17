"""Stage 6d — Gate 3 real-provider smoke for reusable quiz pool generation.

Makes ONE real authenticated call through the production K2Think transport for the Stage 6
``quiz_pool_generation`` prompt, validates the provider output with the production
``GeneratedQuizPool`` validator, and asserts rule 11: the provider's echoed model id equals the configured
prompt model id.

Security: the key is read from env and never printed. No Authorization header, request body, key, or
summary text is emitted — only redacted evidence plus PASS/FAIL.

Usage (operator shell, with LLM_API_KEY exported):
    docker run --rm -e LLM_PROVIDER=k2think -e LLM_API_KEY="$LLM_API_KEY" \
      -e LLM_PROVIDER_BASE_URL="${LLM_PROVIDER_BASE_URL:-https://api.k2think.ai}" \
      -e LLM_CONTEXT_FALLBACK_ENABLED=false \
      -v "$PWD/backend:/app" -w /app <backend-image> python scripts/gate3_quiz_pool_smoke.py
"""

from __future__ import annotations

import time

from app.domains.quiz.pool_service import QUIZ_POOL_PROMPT_KEY
from app.platform.config import settings
from app.platform.llm.errors import GatewayError, ProviderAuthError, ProviderConfigError
from app.platform.llm.models.quiz import GeneratedQuizPool
from app.platform.llm.provider import K2ThinkProvider
from app.platform.llm.registry import get_prompt_registry
from app.platform.llm.validation import OutputValidator

SYNTHETIC_SUMMARY = (
    "Overview: This lecture explains relational database transactions. A transaction groups multiple "
    "writes into one atomic unit so either every write commits or every write rolls back. Key concepts: "
    "atomicity prevents partial updates; isolation prevents concurrent transactions from observing "
    "inconsistent intermediate state; unique constraints preserve invariants under concurrency; row locks "
    "serialize updates to a shared resource; idempotency keys let retried jobs avoid duplicate work. "
    "Worked example: two students starting the same shared quiz should create one reusable section pool, "
    "then sample separate attempts from that pool. Exam-relevant points: define atomicity; explain why a "
    "unique constraint plus retry is safer than an application-only check; describe how row locking helps "
    "a worker claim exactly one queued job."
)


def main() -> int:
    if settings.LLM_PROVIDER != "k2think":
        print("FAIL: LLM_PROVIDER must be 'k2think' (export it before running Gate 3).")
        return 2
    if not settings.LLM_API_KEY:
        print("FAIL: LLM_API_KEY is not set in this environment (rotate + export the key).")
        return 2

    provider = K2ThinkProvider()
    validator = OutputValidator()
    registry = get_prompt_registry()
    print("Stage 6d Gate 3 — quiz pool real-provider smoke (synthetic summary; secrets REDACTED)\n")

    rendered = registry.render(QUIZ_POOL_PROMPT_KEY, transcript=SYNTHETIC_SUMMARY, section_type="lecture")
    expected_model = rendered.model_id
    try:
        started = time.monotonic()
        raw = provider.send(rendered=rendered, backend="nvidia")
        elapsed_s = time.monotonic() - started
        parsed: GeneratedQuizPool = validator.validate(
            raw_text=raw.text, output_schema=GeneratedQuizPool, section_type="lecture"
        )
    except ProviderAuthError:
        print("FAIL: provider auth error (401/403) — key not rotated/valid? Body redacted.")
        return 1
    except ProviderConfigError:
        print("FAIL: provider config error (4xx) — model id / request misconfigured? Body redacted.")
        return 1
    except GatewayError as exc:
        print(f"FAIL: {type(exc).__name__} ({exc.error_code}) — output did not validate or transport failed.")
        return 1

    echo_ok = raw.model_id_echoed == expected_model
    usage = raw.usage
    correct_per_q = [sum(1 for option in question.options if option.is_correct) for question in parsed.questions]
    print(f"--- {QUIZ_POOL_PROMPT_KEY} (route nvidia / reasoning) ---")
    print(
        f"  response model echo : {raw.model_id_echoed}  "
        f"(expected {expected_model})  -> {'OK' if echo_ok else 'MISMATCH'}"
    )
    print("  backend_used        : nvidia")
    print(f"  finish_reason       : {raw.finish_reason!r}  ('length' = truncated; 'stop' = complete)")
    print(f"  elapsed             : {elapsed_s:.1f}s  (timeout = {provider._timeout_for('nvidia')}s)")
    print(
        "  usage               : "
        f"prompt={usage['prompt_tokens']} completion={usage['completion_tokens']} total={usage['total_tokens']}"
    )
    print(f"  status_code         : {raw.status_code}")
    print(f"  parseable           : YES (GeneratedQuizPool, {len(parsed.questions)} questions)")
    print(f"  one-correct-per-q   : {'OK' if all(count == 1 for count in correct_per_q) else f'BAD {correct_per_q}'}")
    print()
    if echo_ok:
        print("PASS: quiz pool route returned the configured model id (rule 11) and a parseable pool.")
        return 0
    print("FAIL: model-ID echo MISMATCH — STOP, do not stamp (rule 11 caught a deployment/alias problem).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
