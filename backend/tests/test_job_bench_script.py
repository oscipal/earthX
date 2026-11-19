"""`scripts/tile-bench/job_bench.py` (NM4-62) still imports what it uses (M5-61 F7).

Its imports sit under ``if __name__ == "__main__"`` (a spawned child must not load `api`), so a name the code no longer
has only showed when someone ran it: `REGISTRY` was gone with M5-13 (M5-36). ``--help`` runs every import of the
script and stops before the database, the object store double and the source.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "tile-bench" / "job_bench.py"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PYTHONPATH": str(REPO / "backend")}
    return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=REPO, env=env, capture_output=True, text=True, timeout=120)


def test_every_import_of_the_script_resolves() -> None:
    result = _run("--help")
    assert result.returncode == 0, result.stderr
    assert "--sequence" in result.stdout


def test_a_case_it_does_not_have_is_refused_before_anything_starts() -> None:
    result = _run("--case", "no-such-case")
    assert result.returncode == 2
    assert "invalid choice" in result.stderr
