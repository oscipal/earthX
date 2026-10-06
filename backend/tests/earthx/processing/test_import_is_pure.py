"""Importing the worker core loads no platform service (KLAERUNGEN B9, Q4, R2; plan M4-07a).

`.importlinter` checks the import graph statically; this checks what a fresh process
actually has loaded after ``import earthx.processing`` — the state of a child process
in `jobs` (adr/0013 §5.3) and of the local runner.

**The probe runs as the image does: without ``boto3``.** ``rasterio.session``
imports ``boto3`` whenever it is installed, and ``boto3`` brings ``botocore``. The
image has neither ``boto3`` nor ``s3transfer`` (``requirements.lock``, guarded by
``test_backend_lock.py``); the development environment has ``boto3`` only through
``moto``, the object store's test double (M4-06). So the probe hides ``boto3``
before anything is imported, and everything else must stay out on its own.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[3]

FORBIDDEN = ("psycopg", "psycopg_pool", "asyncpg", "botocore", "boto3", "earthx.objectstore")


#: As the image is: no boto3 to find (see the module docstring).
AS_IN_THE_IMAGE = "sys.modules['boto3'] = None"


def _loaded_after(statement: str) -> list[str]:
    loaded = "sorted(name for name, module in sys.modules.items() if module is not None)"
    script = f"import json, sys\n{AS_IN_THE_IMAGE}\n{statement}\nprint(json.dumps({loaded}))"
    output = subprocess.run(
        [sys.executable, "-c", script], cwd=BACKEND, capture_output=True, text=True, check=True, timeout=120
    )
    return json.loads(output.stdout.strip().splitlines()[-1])


def test_the_worker_core_loads_no_database_and_no_object_store_client() -> None:
    loaded = _loaded_after("import earthx.processing")
    assert "earthx.processing.core" in loaded
    assert not [name for name in loaded if name.split(".")[0] in FORBIDDEN or name.startswith(FORBIDDEN)]


@pytest.mark.parametrize("client", ["psycopg", "botocore"])
def test_the_check_would_see_one(client: str) -> None:
    """Counter-sample: the same probe, boto3 hidden, still sees a client something imports."""
    assert client in _loaded_after(f"import earthx.processing, {client}")
