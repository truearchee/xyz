"""Stage 12b — production-build hygiene gate.

A build-time assertion: exits non-zero if any E2E/test hook or fault-injection switch is enabled in a
production-candidate build. The 4.6 rule ("fault injection impossible outside E2E/test") and the 4.8 hook
hygiene applied to the production-candidate build.

Run it in the deploy/build environment (before the frontend build and before the backend boots):

    python -m app.platform.production_hygiene --env-file .env.production

It checks ``os.environ`` overlaid with an optional env file parsed as data (never shell-sourced) and is
pure (no app imports, no DB), so it slots into a CI step unchanged and is unit-testable via
``find_violations(env)``. The backend already refuses deterministic providers in prod/staging at boot
(``config.py`` / ``provider.py``); this is the explicit, CI-slottable front line that also covers the
frontend ``NEXT_PUBLIC_*`` hooks the backend can't self-guard.
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import sys
from collections.abc import Callable, Mapping

# (env var, predicate(value) -> True if it is a *violation*, human description). The inventory is the one
# recorded in knowledge/steps/findings-12.md; keep the two in sync when a new switch is added.
_FORBIDDEN: tuple[tuple[str, Callable[[str], bool], str], ...] = (
    ("NEXT_PUBLIC_E2E_TEST_HOOKS", lambda v: v.strip().lower() == "true",
     "frontend E2E test-hook bridge (window.__xyzE2E + auth token override)"),
    ("NEXT_PUBLIC_TRACER_ENABLED", lambda v: v.strip().lower() == "true",
     "frontend tracer recovery route"),
    ("PIPELINE_FAULT_INJECTION_ENABLED", lambda v: v.strip().lower() in {"1", "true", "yes", "on"},
     "transcript pipeline fault injection"),
    ("PIPELINE_FAULT_INJECTION", lambda v: bool(v.strip()),
     "transcript pipeline fault-injection step selector"),
    ("LLM_FAULT_INJECTION", lambda v: bool(v.strip()),
     "LLM transport fault injection"),
    ("EMBEDDING_PROVIDER", lambda v: v.strip().lower() == "deterministic",
     "deterministic embedding provider (test adapter)"),
)

# Env vars whose DEFAULT is unsafe, so absence is itself a violation — a forbidden-value check would miss
# them. `LLM_PROVIDER` defaults to "deterministic" (config.py) with NO boot guard (unlike `EMBEDDING_PROVIDER`,
# which IS rejected in prod/staging at boot), and `get_provider()` serves the DeterministicTestProvider for
# any non-"k2think" value. So an unset/forgotten `LLM_PROVIDER` silently serves the test LLM to real users;
# a production build MUST set it to the real provider explicitly.
_REQUIRED_IN_PROD: tuple[tuple[str, str, str], ...] = (
    ("LLM_PROVIDER", "k2think",
     "the real K2Think provider (its default is the deterministic test adapter, unguarded at boot)"),
)

_ENV_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def load_env_file(path: str | Path) -> dict[str, str]:
    """Parse a dotenv-style env file as data, never as shell code.

    This intentionally implements only the subset this deploy path needs: comments, blank lines,
    optional ``export ``, and ``KEY=value`` entries. Values are not interpolated, command substitutions are
    not executed, and shell metacharacters such as ``$`` and backticks are preserved verbatim.
    """
    parsed: dict[str, str] = {}
    for line_number, raw_line in enumerate(
        Path(path).read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = raw_line.lstrip("\ufeff") if line_number == 1 else raw_line
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :]
        if "=" not in line:
            raise ValueError(f"{path}:{line_number}: expected KEY=value")
        key, value = line.split("=", 1)
        key = key.strip()
        if not _ENV_KEY_RE.fullmatch(key):
            raise ValueError(f"{path}:{line_number}: invalid environment variable name {key!r}")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        parsed[key] = value
    return parsed


def find_violations(env: Mapping[str, str]) -> list[str]:
    """Return a human-readable violation per test/fault switch enabled in ``env`` (empty list = clean)."""
    violations: list[str] = []
    for name, is_violation, description in _FORBIDDEN:
        value = env.get(name)
        if value is not None and is_violation(value):
            violations.append(f"{name}={value!r} enables {description}")
    for name, required, why in _REQUIRED_IN_PROD:
        value = env.get(name)
        if value is None or value.strip().lower() != required:
            violations.append(f"{name}={value!r} must be {required!r} — {why}")
    return violations


def main(argv: list[str] | None = None) -> int:
    args = list(argv or [])
    env_file: str | None = None
    if args:
        if len(args) == 2 and args[0] == "--env-file":
            env_file = args[1]
        else:
            print("usage: production_hygiene.py [--env-file PATH]", file=sys.stderr)
            return 2

    env = dict(os.environ)
    if env_file is not None:
        try:
            env.update(load_env_file(env_file))
        except OSError as exc:
            print(f"PRODUCTION HYGIENE CHECK FAILED — cannot read env file: {exc}", file=sys.stderr)
            return 2
        except ValueError as exc:
            print(f"PRODUCTION HYGIENE CHECK FAILED — invalid env file: {exc}", file=sys.stderr)
            return 2

    violations = find_violations(env)
    if violations:
        print(
            "PRODUCTION HYGIENE CHECK FAILED — test/fault switches are enabled in a production build:",
            file=sys.stderr,
        )
        for violation in violations:
            print(f"  - {violation}", file=sys.stderr)
        print(
            "Unset/disable these before building or deploying the production candidate.",
            file=sys.stderr,
        )
        return 1
    print("Production hygiene check passed: no E2E/test hooks or fault-injection switches enabled.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
