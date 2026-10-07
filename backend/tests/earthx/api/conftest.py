"""Fixtures of the job API tests (M4-08b): a real queue database, a real pool and hub, a bare app.

The database is the throwaway one of `tests/earthx/jobs/conftest.py`, imported rather than copied.
The app is a bare ``FastAPI`` with the job router, built the way ``api.main`` hands it its state;
what the lifespan opens (store, pool, hub, item source) is built here with the same classes.
Signing a result link opens no connection (adr/0015 §3.2), so the store needs no server.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass

import httpx
import psycopg
import pytest
from fastapi import FastAPI
from psycopg_pool import ConnectionPool

from earthx.api.job_events import JobEvents
from earthx.api.processing_route import JobApi, router
from earthx.catalog.datasets import REGISTRY
from earthx.logging import RequestIdMiddleware
from earthx.objectstore.results import Store
from earthx.processing.operators import OperatorRegistry
from tests.earthx.api.test_intake import FAR, S2, Heads, Source, gateway_for, s2_item
from tests.earthx.processing.testops import OPERATORS
from tests.integration.conftest import _postgres_env, require_postgres_env  # noqa: F401 - fixtures

from ..jobs.conftest import db, jobs_database  # noqa: F401 - fixtures
from ..objectstore.conftest import store_env  # noqa: F401 - fixtures


@dataclass
class Rig:
    app: FastAPI
    api: JobApi
    client: httpx.AsyncClient
    source: Source
    heads: Heads
    db: psycopg.Connection
    pool: ConnectionPool
    events: JobEvents
    store: Store


def build_app(api: JobApi | None, operators: OperatorRegistry = OPERATORS) -> FastAPI:
    """The job router on a bare app, with the state `api.main.build_app` sets."""
    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)
    app.include_router(router)
    app.state.earthx_registry = REGISTRY
    app.state.earthx_operators = operators
    app.state.earthx_job_api = api
    return app


@pytest.fixture
async def rig(db: psycopg.Connection, store_env: dict[str, str]) -> AsyncIterator[Rig]:  # noqa: F811
    store = Store.from_environ(store_env)
    pool = ConnectionPool(conninfo="", min_size=1, max_size=4, kwargs={"autocommit": True}, open=False)
    pool.open(wait=True)
    events = JobEvents(pool)
    await events.start()
    heads = Heads()
    source = Source((S2, s2_item()), (S2, s2_item("S2_FAR", FAR)))
    try:
        async with gateway_for(heads) as gateway:
            api = JobApi(
                registry=REGISTRY,
                operators=OPERATORS,
                item_source=source,
                gateway=gateway,
                store=store,
                pool=pool,
                events=events,
            )
            app = build_app(api)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                yield Rig(app, api, client, source, heads, db, pool, events, store)
    finally:
        await events.stop()
        pool.close()


@pytest.fixture
async def docs_client() -> AsyncIterator[httpx.AsyncClient]:
    """The documents that need no job, on an app that has no queue: its job routes must say so."""
    app = build_app(None)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield client
