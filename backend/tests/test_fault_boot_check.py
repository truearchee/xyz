"""Stage 4.8 (B4) — fault-injection FAIL-LOUD boot check.

The boot check refuses to start when a fault-injection flag is active in a HOSTED env. Predicate is
``IS_NON_PROD`` (ENVIRONMENT ∉ {production, staging}) — shared with the step-level guard and
deliberately NOT narrowed to {test, e2e}, so the local fault harness (ENVIRONMENT=development) is
unaffected (adr ruling O1). check-staging-env separately asserts ENVIRONMENT=staging.
"""

from __future__ import annotations

import pytest

from app.platform.faults.boot import assert_fault_injection_safe


def test_refuses_boot_in_staging_with_pipeline_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "staging")
    monkeypatch.setenv("PIPELINE_FAULT_INJECTION_ENABLED", "true")
    with pytest.raises(SystemExit) as exc:
        assert_fault_injection_safe()
    message = str(exc.value)
    assert "PIPELINE_FAULT_INJECTION_ENABLED" in message  # names the offender
    assert "staging" in message
    assert "true" not in message  # never leaks the flag VALUE, only its name + ENVIRONMENT


def test_refuses_boot_in_production_with_llm_fault(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("LLM_FAULT_INJECTION", "summary_detailed")
    with pytest.raises(SystemExit):
        assert_fault_injection_safe()


def test_refuses_boot_in_staging_with_pipeline_step_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "staging")
    monkeypatch.delenv("PIPELINE_FAULT_INJECTION_ENABLED", raising=False)
    monkeypatch.setenv("PIPELINE_FAULT_INJECTION", "embed")  # presence alone is armed
    with pytest.raises(SystemExit):
        assert_fault_injection_safe()


def test_allows_boot_in_development_with_flags_set(monkeypatch: pytest.MonkeyPatch) -> None:
    # O1: the local fault harness runs under development; refusing here would break local recovery
    # testing for zero security gain (development is not hosted).
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("PIPELINE_FAULT_INJECTION_ENABLED", "true")
    monkeypatch.setenv("PIPELINE_FAULT_INJECTION", "embed")
    assert_fault_injection_safe()  # no raise


def test_allows_boot_in_staging_when_flag_explicitly_false(monkeypatch: pytest.MonkeyPatch) -> None:
    # '=false' is explicitly disabled → not an offender (bool semantics, not mere presence).
    monkeypatch.setenv("ENVIRONMENT", "staging")
    monkeypatch.setenv("PIPELINE_FAULT_INJECTION_ENABLED", "false")
    monkeypatch.delenv("PIPELINE_FAULT_INJECTION", raising=False)
    monkeypatch.delenv("LLM_FAULT_INJECTION", raising=False)
    assert_fault_injection_safe()  # no raise


def test_allows_boot_in_staging_with_no_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "staging")
    monkeypatch.delenv("PIPELINE_FAULT_INJECTION_ENABLED", raising=False)
    monkeypatch.delenv("PIPELINE_FAULT_INJECTION", raising=False)
    monkeypatch.delenv("LLM_FAULT_INJECTION", raising=False)
    assert_fault_injection_safe()  # no raise
