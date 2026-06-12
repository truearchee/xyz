"""Stage 4.8b (MF1) — the release-abort PROOF: a failed migration aborts the release before the
bootstrap runs. This is the assertion that, if faked, defeats migrate-as-release entirely (a deploy
that succeeds against a broken migration). The hosted both-directions abort/revert is the developer's
run (deploy/staging-runbook.md); this is the local half.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_RELEASE_SH = _BACKEND_ROOT / "scripts" / "release.sh"


def test_release_sh_aborts_and_skips_bootstrap_on_alembic_failure(tmp_path: Path) -> None:
    """Prove release.sh's `set -e` ACTUALLY propagates a non-zero `alembic` exit (not merely that the
    line is written) AND that the bootstrap is gated behind migrate success. A fake `alembic` exits
    non-zero (a poison migration's signal); a fake `python` would touch a marker if the bootstrap were
    reached. Expect: release.sh exits non-zero and the marker NEVER appears."""
    assert _RELEASE_SH.exists()
    fakebin = tmp_path / "bin"
    fakebin.mkdir()
    marker = tmp_path / "bootstrap_ran"
    (fakebin / "alembic").write_text("#!/bin/sh\necho 'POISON: migration upgrade failed' >&2\nexit 1\n")
    (fakebin / "python").write_text(f"#!/bin/sh\ntouch '{marker}'\nexit 0\n")
    (fakebin / "alembic").chmod(0o755)
    (fakebin / "python").chmod(0o755)

    env = {**os.environ, "PATH": f"{fakebin}:{os.environ['PATH']}"}
    result = subprocess.run(
        ["sh", str(_RELEASE_SH)], env=env, capture_output=True, text=True
    )

    assert result.returncode != 0, f"release.sh did not abort:\n{result.stdout}\n{result.stderr}"
    assert not marker.exists(), "bootstrap ran despite a failed migration — set -e / ordering is broken"


@pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"), reason="real-poison rehearsal needs TEST_DATABASE_URL"
)
def test_real_poison_revision_makes_alembic_exit_nonzero(tmp_path: Path) -> None:
    """Confirm the premise: a real poison revision at head (upgrade raises) makes `alembic upgrade head`
    exit non-zero. Fully isolated — the real alembic/versions tree is NEVER touched."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    src_alembic = _BACKEND_ROOT / "alembic"
    dst_alembic = tmp_path / "alembic"
    shutil.copytree(src_alembic, dst_alembic)

    cfg = Config()
    cfg.set_main_option("script_location", str(src_alembic))
    head = ScriptDirectory.from_config(cfg).get_current_head()

    (dst_alembic / "versions" / "zzzz_poison_release_abort.py").write_text(
        'revision = "poison_release_abort"\n'
        f'down_revision = "{head}"\n'
        "branch_labels = None\n"
        "depends_on = None\n\n\n"
        "def upgrade():\n"
        "    raise RuntimeError('poison: deliberate release-abort rehearsal')\n\n\n"
        "def downgrade():\n"
        "    pass\n"
    )

    ini = tmp_path / "alembic.ini"
    real_ini = (_BACKEND_ROOT / "alembic.ini").read_text()
    ini.write_text(real_ini.replace("script_location = alembic", f"script_location = {dst_alembic}"))

    test_db = os.environ["TEST_DATABASE_URL"]
    env = {**os.environ, "DIRECT_DATABASE_URL": test_db, "DATABASE_URL": test_db}
    result = subprocess.run(
        ["alembic", "-c", str(ini), "upgrade", "head"],
        env=env,
        capture_output=True,
        text=True,
        cwd=str(_BACKEND_ROOT),
    )
    assert result.returncode != 0, f"poison migration did not abort alembic:\n{result.stdout}\n{result.stderr}"
    assert "poison" in (result.stdout + result.stderr).lower()
