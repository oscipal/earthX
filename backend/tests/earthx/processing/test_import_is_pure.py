"""Importing the worker core loads no platform service (KLAERUNGEN B9, Q4, R2; plan M4-07a).

`.importlinter` checks the import graph statically; this checks what a fresh process
actually has loaded after ``import earthx.processing`` — the state of a child process
in `jobs` (adr/0013 §5.3) and of the local runner.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[3]

FORBIDDEN = ("psycopg", "psycopg_pool", "asyncpg", "botocore", "boto3", "earthx.objectstore")


def _loaded_after(statement: str) -> list[str]:
    script = f"import json, sys\n{statement}\nprint(json.dumps(sorted(sys.modules)))"
    output = subprocess.run(
        [sys.executable, "-c", script], cwd=BACKEND, capture_output=True, text=True, check=True, timeout=120
    )
    return json.loads(output.stdout.strip().splitlines()[-1])


def test_the_worker_core_loads_no_database_and_no_object_store_client() -> None:
    loaded = _loaded_after("import earthx.processing")
    assert "earthx.processing.core" in loaded
    assert not [name for name in loaded if name.split(".")[0] in FORBIDDEN or name.startswith(FORBIDDEN)]


def test_the_check_would_see_one() -> None:
    """Counter-sample: the same probe does see psycopg where something imports it."""
    assert "psycopg" in _loaded_after("import earthx.processing, psycopg")
