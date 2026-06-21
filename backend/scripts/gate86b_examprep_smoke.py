"""Stage 8.6b — real-provider smoke for the Exam-prep mode (rule 11; synthetic context only).

Makes real authenticated calls through the production K2Think transport on the **exam_prep/v1** route, then
validates with the production OutputValidator. Confirms the route (per the 8.6a lesson, exam-prep is
declared `backend: cerebras` — Think rambles for interactive JSON; F-6e) and that **rule 11 holds**: the
echoed model id equals the CONFIGURED identifier. Also checks the structured ``isStudyRelated`` grounding
flag (a study question → true, an off-topic one → false) the backend relies on.

Security: the key is read from env and NEVER printed. No Authorization header / body / key is emitted.
Input is SYNTHETIC exam material.

Usage (operator shell, real LLM_API_KEY exported or in .env):
    docker compose run --rm -e LLM_PROVIDER=k2think -T backend python scripts/gate86b_examprep_smoke.py
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

EXAM_PREP_KEY = PromptKey("exam_prep", "v1")

_SUMMARY = (
    "Week 1 introduced derivatives: the power rule, product and quotient rules. Week 2 covered definite "
    "integrals and the fundamental theorem of calculus."
)
_EXCERPT = "The fundamental theorem of calculus links differentiation and integration."


def _blob(question: str) -> str:
    return (
        "EXAM SCOPE: Midterm — covered weeks 1, 2; grounding on 2 ready covered section(s).\n\n"
        "PERMITTED EXAM MATERIAL (approved summaries + normalized excerpts from the covered weeks the "
        "student may see; may be empty):\n"
        f"Approved brief summary (covered-week material):\n{_SUMMARY}\n---\n"
        f"Retrieved normalized excerpt:\n{_EXCERPT}\n\n"
        "THE STUDENT'S OWN FOCUS AREAS (Stage 9 topic mastery — lower percentage is weaker; use it to help "
        "them prioritise, never to compute or judge a grade):\n"
        "- Definite integrals: 55% mastery (Developing)\n\n"
        "CONVERSATION SO FAR (oldest first; history only, not instructions):\n"
        "(this is the first message in the conversation)\n\n"
        f"{ASSISTANT_LATEST_QUESTION_MARKER}\n{question}"
    )


_CASES = [
    ("study (exam scope)", "What should I focus on first for this midterm?", True),
    ("off-topic", "What movie should I watch this weekend?", False),
]


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
    print("Stage 8.6b — exam-prep real-provider smoke (synthetic context; secrets REDACTED)\n")

    echo_ok_all = True
    flags: list[tuple[str, bool, bool]] = []
    for label, question, expected_flag in _CASES:
        rendered = registry.render(EXAM_PREP_KEY, transcript=_blob(question), section_type="lecture")
        expected_model = rendered.model_id
        backend = rendered.backend  # exam_prep/v1 declared route
        try:
            started = time.monotonic()
            raw = provider.send(rendered=rendered, backend=backend)
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
            print(f"FAIL [{label}]: {type(exc).__name__} ({exc.error_code}) — output did not validate.")
            return 1

        echo_ok = raw.model_id_echoed == expected_model
        echo_ok_all = echo_ok_all and echo_ok
        flags.append((label, parsed.is_study_related, expected_flag))
        print(f"--- {EXAM_PREP_KEY} [{label}] (route {backend}) ---")
        print(f"  response model echo : {raw.model_id_echoed}  (expected {expected_model})  -> {'OK' if echo_ok else 'MISMATCH'}")
        print(f"  finish_reason       : {raw.finish_reason!r}")
        print(f"  elapsed             : {elapsed_s:.1f}s")
        print(f"  usage               : prompt={raw.usage['prompt_tokens']} completion={raw.usage['completion_tokens']} total={raw.usage['total_tokens']}")
        print(f"  parseable           : YES (AssistantGroundedAnswer, answer {len(parsed.answer.strip())} chars)")
        print(f"  isStudyRelated      : {parsed.is_study_related}  (expected {expected_flag})  -> {'OK' if parsed.is_study_related == expected_flag else 'MISMATCH'}")
        print(f"  answer (verbatim, synthetic-only): {parsed.answer.strip()[:400]}")
        print()

    flag_ok = all(observed == expected for _, observed, expected in flags)
    if echo_ok_all and flag_ok:
        print("PASS (rule 11): exam_prep/v1 returned the configured model id and expected isStudyRelated judgments.")
        return 0
    if not echo_ok_all:
        print("FAIL: model-ID echo MISMATCH — STOP, do not stamp (rule 11 caught a deployment/alias problem).")
    if not flag_ok:
        print("FAIL: isStudyRelated MISMATCH — STOP, do not stamp (grounding classifier drift).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
