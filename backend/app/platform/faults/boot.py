"""Boot-time fault-injection backstop (Stage 4.8 §8).

The step-level guard (``pipeline_faults._assert_safe_to_inject``) raises only when a faulted step
actually runs — a misconfigured deploy could sit there with a fault flag set and never trip it until
a job happens to run. This refuses to **boot** when any fault-injection flag is active in a HOSTED
environment, so the failure is immediate and loud instead of latent.

Predicate is shared with the step-level guard: ``IS_NON_PROD`` (``ENVIRONMENT`` ∉ {production,
staging}). It is deliberately NOT narrowed to {test, e2e}: the local fault harness
(``docker-compose.fault.yml``) runs under ``ENVIRONMENT=development``, and development is not hosted,
so refusing there would break local recovery testing for zero security gain (adr ruling O1). The
``check-staging-env`` script closes the residual gap by asserting ``ENVIRONMENT=staging`` explicitly,
so a misconfigured ``ENVIRONMENT=development`` in the staging deploy is caught there.

Only flag NAMES and ``ENVIRONMENT`` are surfaced in the message — never flag VALUES — so this can
never leak a secret-ish payload to the logs.
"""

from __future__ import annotations

import os

from app.platform.config import settings

# Presence-based flags: a step name / transport value being present at all means injection is armed.
_PRESENCE_FLAGS = ("PIPELINE_FAULT_INJECTION", "LLM_FAULT_INJECTION")


def assert_fault_injection_safe() -> None:
    """Refuse to boot if any fault-injection flag is active while not in a non-prod environment."""
    if settings.IS_NON_PROD:
        return
    offenders: list[str] = []
    if settings.PIPELINE_FAULT_INJECTION_ENABLED:  # bool: '=false' is correctly NOT an offender
        offenders.append("PIPELINE_FAULT_INJECTION_ENABLED")
    offenders += [name for name in _PRESENCE_FLAGS if (os.environ.get(name) or "").strip()]
    if offenders:
        raise SystemExit(
            f"FATAL: fault-injection flag(s) {sorted(set(offenders))} active while "
            f"ENVIRONMENT={settings.ENVIRONMENT!r} (hosted). Fault injection must never run in "
            "production/staging — refusing to boot."
        )
