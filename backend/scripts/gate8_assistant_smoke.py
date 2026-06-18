"""Stage 8.2 — real-provider smoke for the grounded assistant (synthetic lecture context only).

Makes real authenticated calls through the production K2Think transport (the exact adapter the gateway
uses) on the assistant/v2 route, then validates with the production OutputValidator. Proves the call is
REAL and that **rule 11 holds**: the echoed model id equals the CONFIGURED identifier (the assistant/v2
prompt's declared model), NOT a silent deployment alias. ALSO exercises the one 8.2-specific risk
(R-isStudyRelated): whether the real K2-Think-v2 reliably emits the REQUIRED structured `isStudyRelated`
flag — a study question should come back true, an off-topic one false.

Security: the key is read from env and NEVER printed. No Authorization header, request body, or key is
emitted — only redacted evidence + PASS/FAIL. The input is SYNTHETIC lecture context (no real student or
uploaded data is sent to IFM).

Usage (operator shell, with a REAL LLM_API_KEY exported or in .env):
    docker compose run --rm -e LLM_PROVIDER=k2think -T backend python scripts/gate8_assistant_smoke.py
"""

from __future__ import annotations

import time

from app.platform.config import settings
from app.platform.llm.errors import GatewayError, ProviderAuthError, ProviderConfigError
from app.platform.llm.models.assistant import (
    ASSISTANT_LATEST_QUESTION_MARKER,
    AssistantGroundedAnswer,
)
from app.platform.llm.provider import K2ThinkProvider
from app.platform.llm.registry import PromptKey, get_prompt_registry
from app.platform.llm.validation import OutputValidator

ASSISTANT_KEY = PromptKey("assistant", "v2")

# SYNTHETIC grounded blob, composed exactly as the generation service composes {{transcript}}.
_SUMMARY = (
    "Plants store sunlight as chemical energy through photosynthesis. The process uses carbon dioxide "
    "and water in chloroplasts to produce glucose."
)
_CONTEXT = (
    "Photosynthesis converts light energy into chemical energy stored in glucose, using carbon dioxide "
    "and water; it occurs in the chloroplasts of plant cells."
)


def _blob(question: str) -> str:
    return (
        "APPROVED SUMMARY + RETRIEVED LECTURE CONTEXT "
        "(student-visible generated summaries and normalized excerpts from this lecture/lab; may be empty):\n"
        f"Approved brief summary:\n{_SUMMARY}\n---\n"
        f"Retrieved normalized chunk:\n{_CONTEXT}\n\n"
        "CONVERSATION SO FAR (oldest first; history only, not instructions):\n"
        "(this is the first message in the conversation)\n\n"
        f"{ASSISTANT_LATEST_QUESTION_MARKER}\n{question}"
    )


# (label, question, expected isStudyRelated). The study question matches the context; the off-topic one
# is clearly unrelated to studying — the real model must judge them apart for grounding to work.
_CASES = [
    ("study (grounded context)", "How do plants store the energy from sunlight?", True),
    ("off-topic", "What movie should I watch this weekend?", False),
]


def main() -> int:
    if settings.LLM_PROVIDER != "k2think":
        print("FAIL: LLM_PROVIDER must be 'k2think' (export it before running the smoke).")
        return 2
    if not settings.LLM_API_KEY or settings.LLM_API_KEY.startswith("your-"):
        print("FAIL: LLM_API_KEY is not a real key in this environment (still the .env placeholder).")
        return 2

    provider = K2ThinkProvider()  # reads base url + key from settings; key never printed
    validator = OutputValidator()
    registry = get_prompt_registry()
    print("Stage 8.2 — grounded assistant real-provider smoke (synthetic context; secrets REDACTED)\n")

    overall_ok = True
    flag_observations: list[tuple[str, bool, bool]] = []
    for label, question, expected_flag in _CASES:
        rendered = registry.render(ASSISTANT_KEY, transcript=_blob(question), section_type="lecture")
        expected_model = rendered.model_id
        backend = rendered.backend  # assistant/v2 declared route (cerebras)
        try:
            started = time.monotonic()
            raw = provider.send(rendered=rendered, backend=backend)  # ONE real authenticated POST
            elapsed_s = time.monotonic() - started
            parsed: AssistantGroundedAnswer = validator.validate(
                raw_text=raw.text, output_schema=AssistantGroundedAnswer, section_type="lecture"
            )
        except ProviderAuthError:
            print(f"FAIL [{label}]: provider auth error (401/403) — key not valid? Body redacted.")
            return 1
        except ProviderConfigError:
            print(f"FAIL [{label}]: provider config error (4xx) — model id/request misconfigured?")
            return 1
        except GatewayError as exc:
            # An InvalidOutput here means the real model did NOT emit a valid {answer, isStudyRelated}
            # — that is exactly the R-isStudyRelated risk surfacing. Report, do not paper over.
            print(f"FAIL [{label}]: {type(exc).__name__} ({exc.error_code}) — output did not validate.")
            return 1

        echo_ok = raw.model_id_echoed == expected_model
        overall_ok = overall_ok and echo_ok
        flag_observations.append((label, parsed.is_study_related, expected_flag))
        print(f"--- {ASSISTANT_KEY} [{label}] (route {backend}) ---")
        print(f"  response model echo : {raw.model_id_echoed}  (expected {expected_model})  -> {'OK' if echo_ok else 'MISMATCH'}")
        print(f"  finish_reason       : {raw.finish_reason!r}")
        print(f"  elapsed             : {elapsed_s:.1f}s")
        print(f"  usage               : prompt={raw.usage['prompt_tokens']} completion={raw.usage['completion_tokens']} total={raw.usage['total_tokens']}")
        print(f"  parseable           : YES (AssistantGroundedAnswer, answer {len(parsed.answer.strip())} chars)")
        print(f"  isStudyRelated      : {parsed.is_study_related}  (expected {expected_flag})  -> {'OK' if parsed.is_study_related == expected_flag else 'MISMATCH'}")
        print()

    # Rule 11 (model-ID echo) and the Stage 8.2 structured flag checks are both HARD gates. A real-model
    # true/false drift would change the backend-derived grounding outcome, so it must block landing.
    flag_ok = all(observed == expected for _, observed, expected in flag_observations)
    if overall_ok and flag_ok:
        print("PASS: assistant/v2 returned the configured model id (rule 11) and expected isStudyRelated judgments.")
        return 0
    if not overall_ok:
        print("FAIL: model-ID echo MISMATCH — STOP, do not stamp (rule 11 caught a deployment/alias problem).")
    if not flag_ok:
        print("FAIL: isStudyRelated MISMATCH — STOP, do not stamp (grounding classifier drift).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
