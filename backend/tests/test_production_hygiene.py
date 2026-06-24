"""Stage 12b — production-build hygiene gate (fail-on-flag)."""

import pytest

from app.platform.production_hygiene import find_violations, main


def test_clean_env_has_no_violations() -> None:
    safe = {
        "LLM_PROVIDER": "k2think",
        "EMBEDDING_PROVIDER": "sentence_transformers",
        "NEXT_PUBLIC_E2E_TEST_HOOKS": "false",
        "ENVIRONMENT": "production",
    }
    assert find_violations(safe) == []


# A production-safe baseline (the real LLM provider set, no switches). Tests merge ONE bad var into it so
# exactly one violation surfaces — LLM_PROVIDER must be k2think, so it can't simply be left out.
_CLEAN_BASE = {"LLM_PROVIDER": "k2think"}


def test_empty_env_flags_missing_llm_provider() -> None:
    # Unset LLM_PROVIDER defaults to the deterministic test adapter (config.py) with no boot guard, so
    # absence is itself a violation — a forbidden-value check would miss it.
    violations = find_violations({})
    assert len(violations) == 1
    assert "LLM_PROVIDER" in violations[0]


def test_llm_provider_must_be_the_real_provider() -> None:
    assert find_violations({"LLM_PROVIDER": "k2think"}) == []  # real provider → clean
    assert find_violations({"LLM_PROVIDER": "deterministic"})  # test adapter → violation
    assert find_violations({})  # unset (defaults to deterministic) → violation
    assert find_violations({"LLM_PROVIDER": "anything_else"})  # any non-real value → violation


@pytest.mark.parametrize(
    "switch",
    [
        {"NEXT_PUBLIC_E2E_TEST_HOOKS": "true"},
        {"NEXT_PUBLIC_TRACER_ENABLED": "true"},
        {"PIPELINE_FAULT_INJECTION_ENABLED": "true"},
        {"PIPELINE_FAULT_INJECTION": "parse"},
        {"LLM_FAULT_INJECTION": "provider_5xx"},
        {"LLM_PROVIDER": "deterministic"},
        {"EMBEDDING_PROVIDER": "deterministic"},
    ],
)
def test_each_switch_is_a_violation(switch: dict[str, str]) -> None:
    env = {**_CLEAN_BASE, **switch}  # only the switch-under-test should violate
    violations = find_violations(env)
    assert len(violations) == 1
    assert next(iter(switch)) in violations[0]


def test_case_insensitive_and_whitespace_tolerant() -> None:
    assert find_violations({"LLM_PROVIDER": "  Deterministic  "})
    assert find_violations({"NEXT_PUBLIC_E2E_TEST_HOOKS": "TRUE"})


def test_multiple_switches_all_reported() -> None:
    env = {"LLM_PROVIDER": "deterministic", "PIPELINE_FAULT_INJECTION_ENABLED": "true"}
    assert len(find_violations(env)) == 2


def test_main_exits_nonzero_on_violation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "deterministic")
    assert main() == 1


def test_main_exits_zero_when_clean(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "NEXT_PUBLIC_E2E_TEST_HOOKS",
        "NEXT_PUBLIC_TRACER_ENABLED",
        "PIPELINE_FAULT_INJECTION_ENABLED",
        "PIPELINE_FAULT_INJECTION",
        "LLM_FAULT_INJECTION",
    ):
        monkeypatch.delenv(name, raising=False)
    # The backend test environment runs deterministic providers (conftest/.env) — override to prod-safe.
    monkeypatch.setenv("LLM_PROVIDER", "k2think")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "sentence_transformers")
    assert main() == 0
