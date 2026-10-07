"""The child of a supervisor that lives under a real `uvicorn` (adr/0013 §6.2, plan M4-08a §7 "spawn unter uvicorn").

`spawn` re-imports the parent's main module in the child. Under uvicorn that is uvicorn's own
entry point and not the app; this proves it with the console script the compose file runs, and
that a SIGTERM, which is what `docker compose stop` sends, ends the supervisor cleanly.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
from pathlib import Path

import psycopg
import pytest

from earthx.jobs.submit import job_status, submit
from tests.earthx.jobs.support import make_recipe, wait_until

BACKEND = Path(__file__).resolve().parents[3]
FORBIDDEN = ("psycopg", "psycopg_pool", "asyncpg", "botocore", "boto3", "earthx.objectstore")


def test_a_child_of_a_supervisor_under_uvicorn_loads_no_database_and_the_supervisor_stops_on_sigterm(
    db: psycopg.Connection, tmp_path: Path
) -> None:
    probe = tmp_path / "modules.json"
    # No PYTHONPATH: in the image `earthx` is found only because uvicorn puts the working directory on
    # `sys.path`, and the child has to find it the same way (spawn hands the parent's `sys.path` on).
    env = {**os.environ, "SP_WORKDIR": str(tmp_path / "work"), "PROBE_OUT": str(probe)}
    env.pop("PYTHONPATH", None)
    uvicorn = Path(sys.executable).with_name("uvicorn")
    server = subprocess.Popen(
        [str(uvicorn), "tests.earthx.jobs.uvicorn_app:app", "--port", "0", "--no-access-log"],
        cwd=BACKEND,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        assert server.stdout is not None
        started = False
        for line in server.stdout:
            if line.strip() == "started":
                started = True
                break
        assert started, "the supervisor did not start"
        job_id = submit(db, make_recipe())
        wait_until(lambda: probe.exists(), timeout=60)
        wait_until(lambda: (job_status(db, job_id) or None) is not None and job_status(db, job_id).status == "failed")  # type: ignore[union-attr]
    finally:
        server.send_signal(signal.SIGTERM)
        try:
            remaining, _ = server.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            server.kill()
            remaining, _ = server.communicate()
            pytest.fail("the server did not end on SIGTERM within 30 s")
    loaded = json.loads(probe.read_text())
    assert "earthx.jobs.child" in loaded
    offenders = [name for name in loaded if name.split(".")[0] in FORBIDDEN or name.startswith(FORBIDDEN)]
    assert offenders == []
    assert [
        name for name in loaded if name in {"earthx.jobs.worker", "earthx.jobs.main", "tests.earthx.jobs.uvicorn_app"}
    ] == []
    assert "stopped" in remaining
    # uvicorn runs its shutdown and then re-raises the signal, so the status says SIGTERM: a clean end.
    assert server.returncode in (0, -signal.SIGTERM)
