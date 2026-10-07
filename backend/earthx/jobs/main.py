"""Process entrypoint for `worker` (architekturplan.md 3.2).

The process is a small FastAPI app with `/health` and, in its lifespan, the supervisor
(`worker.py`, adr/0013 §5.3, §6.2): it picks up runs from the queue and computes each in a
child process. Since M4-06 the process reaches the object store and does not start without
the bucket rule that expires `results/` (adr/0015 §7.3, F8): the rule is the net under the
7 days of Q10, and nothing here would notice it missing later. Since M4-08a it also does not
start without the queue tables (migration 006, `catalog-load`) or with a bad `WORKER_*`
value.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager

import psycopg
from fastapi import FastAPI, Response
from fastapi.concurrency import run_in_threadpool

from earthx.jobs.config import WorkerConfig, WorkerConfigError
from earthx.jobs.worker import Supervisor
from earthx.logging import RequestIdMiddleware, configure_logging
from earthx.objectstore.errors import LifecycleMissing, ObjectStoreError
from earthx.objectstore.results import Store, lifecycle_ok

# M3-16: this process's own JSON logging, before anything can log a line
# (K-01/K-02) — the compose command starts it with `--no-access-log`, so
# `RequestIdMiddleware` below is this process's only access log.
configure_logging()

logger = logging.getLogger(__name__)


def open_object_store(environ: Mapping[str, str] | None = None) -> Store:
    """The store from the environment, with its lifecycle rule checked, read only.

    `S3_LIFECYCLE_CHECK=off` is for a provider without lifecycle rules (adr/0015
    §9.3); it skips the check with exactly one warning that names no value from
    the configuration (Auflage F8). docker-compose.yml never sets it.
    """
    store = Store.from_environ(environ)
    if store.config.lifecycle_check == "off":
        logger.warning(
            "object store lifecycle check is switched off (S3_LIFECYCLE_CHECK): nothing checks "
            "that the bucket expires results/ after 7 days"
        )
        return store
    if not lifecycle_ok(store):
        raise LifecycleMissing(
            "the bucket has no enabled lifecycle rule that expires results/ after 7 days and aborts "
            "multipart uploads after 1 day (adr/0015 §7.3)"
        )
    return store


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    try:
        app.state.store = open_object_store()
    except ObjectStoreError as exc:
        # The messages of this module name variables and S3 error codes, never a value.
        logger.error("worker not started: %s", exc)
        raise
    supervisor = None
    try:
        supervisor = Supervisor(WorkerConfig.from_environ(), app.state.store)
        await run_in_threadpool(supervisor.start)
    except (WorkerConfigError, RuntimeError) as exc:
        # Our own texts: they name a variable or a missing migration, never a value.
        logger.error("worker not started: %s", exc)
        raise
    except psycopg.Error as exc:
        # The class only: the text of a database error can carry a value.
        logger.error("worker not started: the database is not reachable (%s)", type(exc).__name__)
        raise
    app.state.supervisor = supervisor
    try:
        yield
    finally:
        await run_in_threadpool(supervisor.stop)
        app.state.supervisor = None


app = FastAPI(title="earthx-worker", lifespan=lifespan)
app.add_middleware(RequestIdMiddleware)


@app.get("/health")
def health(response: Response) -> dict:
    """200 while the supervisor reached the database within the last 30 s and all its threads live (adr/0013 §5.3).

    An app whose lifespan did not run has no supervisor to ask and answers 200, as it always did.
    """
    supervisor = getattr(app.state, "supervisor", None)
    if supervisor is not None and not supervisor.healthy():
        response.status_code = 503
        return {"status": "unavailable", "service": "worker"}
    return {"status": "ok", "service": "worker"}
