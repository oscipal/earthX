"""The worker's shape under a real `uvicorn` process, without the object store: a lifespan that runs a supervisor.

``uvicorn tests.earthx.jobs.uvicorn_app:app`` with `PG*`, ``SP_WORKDIR`` and ``PROBE_OUT``. The supervisor
has no store (nothing is uploaded: the child fails after it wrote what it had loaded).
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from earthx.jobs.config import WorkerConfig
from earthx.jobs.entry import ChildTarget
from earthx.jobs.worker import Supervisor


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    config = WorkerConfig(
        slots=1,
        lease_seconds=3.0,
        heartbeat_seconds=0.3,
        poll_seconds=0.2,
        sweep_seconds=60.0,
        cleanup_first_seconds=1e9,
        workdir=Path(os.environ["SP_WORKDIR"]),
    )
    supervisor = Supervisor(
        config,
        None,
        target=ChildTarget("tests.earthx.jobs.child_targets", "write_modules"),  # type: ignore[arg-type]
    )
    supervisor.start()
    print("started", flush=True)
    yield
    supervisor.stop(30)
    print("stopped", flush=True)


app = FastAPI(lifespan=lifespan)
