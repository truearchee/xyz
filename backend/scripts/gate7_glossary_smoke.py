"""Stage 7 — real-provider smoke for glossary definition generation (synthetic term only).

Makes ONE real authenticated call through the production K2Think transport (the exact adapter the
gateway uses) on the glossary route, then validates with the production OutputValidator. Proves the
call is REAL and that **rule 11 holds**: the echoed model id equals the CONFIGURED identifier
(the glossary_definition prompt's declared model), NOT a silent deployment alias.

Security: the key is read from the env and NEVER printed. No Authorization header, request body, key,
or definition text key material is emitted — only redacted evidence + PASS/FAIL. The input is a
SYNTHETIC term/context (no real student or uploaded data is sent to IFM).

Usage (operator shell, with a REAL LLM_API_KEY in .env / exported):
    docker compose run --rm -e LLM_PROVIDER=k2think -v "$PWD/backend:/app" -T backend \
        python scripts/gate7_glossary_smoke.py
"""

from __future__ import annotations

import time

from app.platform.config import settings
from app.platform.llm.errors import GatewayError, ProviderAuthError, ProviderConfigError
from app.platform.llm.models.summary import BriefSummary
from app.platform.llm.provider import K2ThinkProvider
from app.platform.llm.registry import PromptKey, get_prompt_registry
from app.platform.llm.validation import OutputValidator

GLOSSARY_KEY = PromptKey("glossary_definition", "v1")

# SYNTHETIC localized input, composed exactly as GatewayTranslationService does (language baked into the
# rendered input — decision B1). Arabic target so the smoke also exercises the RTL/non-Latin path.
SYNTHETIC_INPUT = (
    "Target language: Arabic. Write the definition ENTIRELY in Arabic.\n"
    'Course / subject: "Biology 101".\n'
    "Entry type: term.\n"
    "Term: mitochondria\n"
    "Context from the lecture: The mitochondria is the organelle that produces most of the cell's ATP "
    "through aerobic cellular respiration."
)

_ARABIC = ("؀", "ۿ")


def _has_arabic(text: str) -> bool:
    return any(_ARABIC[0] <= ch <= _ARABIC[1] for ch in text)


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
    print("Stage 7 — glossary definition real-provider smoke (synthetic term; secrets REDACTED)\n")

    rendered = registry.render(GLOSSARY_KEY, transcript=SYNTHETIC_INPUT, section_type="term")
    expected_model = rendered.model_id
    backend = rendered.backend  # the glossary prompt's declared route (cerebras)
    try:
        started = time.monotonic()
        raw = provider.send(rendered=rendered, backend=backend)  # ONE real authenticated POST
        elapsed_s = time.monotonic() - started
        # Reuse the production validator branch (BriefSummary — the glossary definition shape, D3).
        parsed: BriefSummary = validator.validate(
            raw_text=raw.text, output_schema=BriefSummary, section_type="term"
        )
    except ProviderAuthError:
        print("FAIL: provider auth error (401/403) — key not valid? Body redacted.")
        return 1
    except ProviderConfigError:
        print("FAIL: provider config error (4xx) — model id / request misconfigured? Body redacted.")
        return 1
    except GatewayError as exc:
        print(f"FAIL: {type(exc).__name__} ({exc.error_code}) — output did not validate or transport failed.")
        return 1

    echo_ok = raw.model_id_echoed == expected_model
    usage = raw.usage
    definition_len = len(parsed.text.strip())
    arabic = _has_arabic(parsed.text)
    print(f"--- {GLOSSARY_KEY} (route {backend}) ---")
    print(f"  response model echo : {raw.model_id_echoed}  (expected {expected_model})  -> {'OK' if echo_ok else 'MISMATCH'}")
    print(f"  backend_used        : {backend}")
    print(f"  finish_reason       : {raw.finish_reason!r}  ('length' = truncated by max_tokens; 'stop' = complete)")
    print(f"  elapsed             : {elapsed_s:.1f}s")
    print(f"  usage               : prompt={usage['prompt_tokens']} completion={usage['completion_tokens']} total={usage['total_tokens']}")
    print(f"  status_code         : {raw.status_code}")
    print(f"  parseable           : YES (BriefSummary, definition {definition_len} chars)")
    print(f"  arabic-script (soft): {'present' if arabic else 'ABSENT (logged-only soft signal, not a gate fail)'}")
    print()
    if echo_ok:
        print("PASS: glossary route returned the configured model id (rule 11) and a parseable definition.")
        return 0
    print("FAIL: model-ID echo MISMATCH — STOP, do not stamp (rule 11 caught a deployment/alias problem).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
