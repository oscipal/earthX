"""A supervisor in a process of its own, for the test that kills it with ``SIGKILL``.

``python -m tests.earthx.jobs.supervisor_process`` with the environment of a worker
(`PG*`, `S3_*`) and ``SP_WORKDIR``. Its child hangs, so the run it holds stays open until
the lease runs out.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

from earthx.jobs.config import WorkerConfig
from earthx.jobs.entry import ChildTarget
from earthx.jobs.worker import Supervisor
from earthx.objectstore.results import Store


def main() -> None:
    config = WorkerConfig(
        slots=1,
        lease_seconds=1.0,
        heartbeat_seconds=0.3,
        poll_seconds=0.2,
        sweep_seconds=60.0,
        cleanup_first_seconds=1e9,
        workdir=Path(os.environ["SP_WORKDIR"]),
    )
    supervisor = Supervisor(
        config, Store.from_environ(), target=ChildTarget("tests.earthx.jobs.child_targets", "hang"), name="doomed"
    )
    supervisor.start()
    print("started", flush=True)
    time.sleep(3600)


if __name__ == "__main__":
    main()
