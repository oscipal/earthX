"""Process entrypoint for `worker` (architekturplan.md 3.2).

Real job execution lands on this module from M4 (architekturplan.md 3.1:
"Queue, Worker, Fortschritt, Ergebnisse"). Since M4-06 the process reaches the
object store and does not start without the bucket rule that expires
`results/` (adr/0015 §7.3, F8): the rule is the net under the 7 days of Q10,
and nothing here would notice it missing later.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager

from fastapi import FastAPI

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
    yield


app = FastAPI(title="earthx-worker", lifespan=lifespan)
app.add_middleware(RequestIdMiddleware)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "worker"}
