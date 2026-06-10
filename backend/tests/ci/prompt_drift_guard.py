"""CI prompt-drift guard (spec §6.4).

Fails if a prompt file's content changed without a version bump — i.e. the file's content hash no
longer matches the committed ``prompts/CHECKSUMS.json`` baseline for its ``name/version``. A new
prompt or version must be recorded in the baseline (an intentional act), which is how a version bump
is distinguished from accidental drift.

Run in CI:  ``python -m tests.ci.prompt_drift_guard``  (exit code 1 on drift)
Run in pytest:  ``tests/test_prompt_drift_guard.py`` imports :func:`check_prompt_drift`.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.platform.llm.registry import PromptRegistry, default_prompts_dir


def checksums_path(prompts_dir: Path | None = None) -> Path:
    return (prompts_dir or default_prompts_dir()) / "CHECKSUMS.json"


def check_prompt_drift(prompts_dir: Path | None = None) -> list[str]:
    """Return a list of human-readable drift problems; empty means clean."""
    directory = prompts_dir or default_prompts_dir()
    baseline_path = checksums_path(directory)
    if not baseline_path.is_file():
        return [f"missing checksum baseline: {baseline_path}"]

    baseline: dict[str, str] = json.loads(baseline_path.read_text(encoding="utf-8"))
    registry = PromptRegistry.load_from_dir(directory)
    actual = {
        f"{pf.key.name}/{pf.key.version}": pf.content_hash for pf in registry.all_files()
    }

    problems: list[str] = []
    for key, expected in baseline.items():
        if key not in actual:
            problems.append(f"baseline references a missing prompt file: {key}")
        elif actual[key] != expected:
            problems.append(
                f"prompt {key} content changed without a version bump "
                f"(expected {expected[:12]}…, got {actual[key][:12]}…) — "
                f"bump the version and update CHECKSUMS.json"
            )
    for key in actual:
        if key not in baseline:
            problems.append(
                f"new prompt {key} is not recorded in CHECKSUMS.json — "
                f"add it (this is the version-bump record)"
            )
    return problems


def main() -> int:
    problems = check_prompt_drift()
    if problems:
        print("PROMPT DRIFT GUARD: FAIL")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print("PROMPT DRIFT GUARD: OK")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry
    raise SystemExit(main())
