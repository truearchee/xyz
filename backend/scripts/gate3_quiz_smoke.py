"""Stage 5d — Gate 3 real-provider smoke for quiz generation (synthetic summary only).

Makes ONE real authenticated call through the production K2Think transport (the exact adapter the
gateway uses) on the reasoning route, then validates with the production OutputValidator. Proves the
call is REAL and that **rule 11 holds**: the echoed model id equals the CONFIGURED identifier
(``LLM_DETAILED_MODEL_ID`` — the K2-Think-v2 named deviation), NOT the slice's documented K2-Think-v0.
A silent alias mismatch is exactly what rule 11 exists to catch.

Security: the key is read from the env and NEVER printed. No Authorization header, request body, key,
or summary text is emitted — only redacted evidence + PASS/FAIL.

Usage (operator shell, with LLM_API_KEY exported):
    docker run --rm -e LLM_PROVIDER=k2think -e LLM_API_KEY="$LLM_API_KEY" \
      -e LLM_PROVIDER_BASE_URL="${LLM_PROVIDER_BASE_URL:-https://api.k2think.ai}" \
      -e LLM_CONTEXT_FALLBACK_ENABLED=false \
      -v "$PWD/backend:/app" -w /app <backend-image> python scripts/gate3_quiz_smoke.py
"""

from __future__ import annotations

import time

from app.platform.config import settings
from app.platform.llm.errors import GatewayError, ProviderAuthError, ProviderConfigError
from app.platform.llm.models.quiz import PostClassQuiz
from app.platform.llm.provider import K2ThinkProvider
from app.platform.llm.registry import PromptKey, get_prompt_registry
from app.platform.llm.validation import OutputValidator

QUIZ_KEY = PromptKey("post_class_quiz_generation", "v1")

# A SHORT SYNTHETIC detailed-summary TEXT — the quiz prompt's input is the summary, not a transcript.
# No real student / uploaded / production data is sent to IFM.
SYNTHETIC_SUMMARY = (
    "Overview: This session introduced supervised learning. In supervised learning a model is trained "
    "on labelled examples, each pairing an input with a known correct output, and the goal is to learn "
    "a function that generalises to new inputs. Key concepts: the loss function measures how wrong a "
    "single prediction is (squared error for regression, cross-entropy for classification); training "
    "minimises the average loss by gradient descent; overfitting occurs when a model fits the training "
    "data (including its noise) but generalises poorly, diagnosed by a large gap between training and "
    "validation error; regularisation penalises large parameters to improve generalisation. Worked "
    "example: fitting a line to noisy points by least squares minimises the sum of squared residuals. "
    "Exam-relevant points: define the loss function; distinguish training error from generalisation "
    "error; describe gradient descent in words; explain why regularisation helps."
)


def main() -> int:
    if settings.LLM_PROVIDER != "k2think":
        print("FAIL: LLM_PROVIDER must be 'k2think' (export it before running Gate 3).")
        return 2
    if not settings.LLM_API_KEY:
        print("FAIL: LLM_API_KEY is not set in this environment (rotate + export the key).")
        return 2

    provider = K2ThinkProvider()  # reads base url + key from settings; key never printed
    validator = OutputValidator()
    registry = get_prompt_registry()
    print("Stage 5d Gate 3 — quiz real-provider smoke (synthetic summary; secrets REDACTED)\n")

    rendered = registry.render(QUIZ_KEY, transcript=SYNTHETIC_SUMMARY, section_type="lecture")
    expected_model = rendered.model_id
    try:
        started = time.monotonic()
        raw = provider.send(rendered=rendered, backend="nvidia")  # ONE real authenticated POST
        elapsed_s = time.monotonic() - started
        parsed: PostClassQuiz = validator.validate(
            raw_text=raw.text, output_schema=PostClassQuiz, section_type="lecture"
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
    correct_per_q = [sum(1 for o in q.options if o.is_correct) for q in parsed.questions]
    print(f"--- {QUIZ_KEY} (route nvidia / reasoning) ---")
    print(f"  response model echo : {raw.model_id_echoed}  (expected {expected_model})  -> {'OK' if echo_ok else 'MISMATCH'}")
    print(f"  backend_used        : nvidia")
    print(f"  finish_reason       : {raw.finish_reason!r}  ('length' = truncated by max_tokens; 'stop' = complete)")
    print(f"  elapsed             : {elapsed_s:.1f}s  (timeout = {provider._timeout_for('nvidia')}s)")
    print(f"  usage               : prompt={usage['prompt_tokens']} completion={usage['completion_tokens']} total={usage['total_tokens']}")
    print(f"  status_code         : {raw.status_code}")
    print(f"  parseable           : YES (PostClassQuiz, {len(parsed.questions)} questions)")
    print(f"  one-correct-per-q   : {'OK' if all(c == 1 for c in correct_per_q) else f'BAD {correct_per_q}'}")
    print()
    if echo_ok:
        print("PASS: quiz route returned the configured model id (rule 11) and a parseable 10-question quiz.")
        return 0
    print("FAIL: model-ID echo MISMATCH — STOP, do not stamp (rule 11 caught a deployment/alias problem).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
