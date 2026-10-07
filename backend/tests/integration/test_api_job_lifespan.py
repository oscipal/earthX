"""What `api` opens for the job API, and what it needs before it starts (M4-08b F7, adr/0013 §5.4).

Real Postgres. The object store needs no server here: signing a link opens no connection
(adr/0015 §3.2), and `conftest.py` gives the process an invented configuration.
"""

from __future__ import annotations

import asyncio

import httpx
import psycopg
import pytest

from earthx.api import main
from earthx.api.job_events import APPLICATION_NAME
from earthx.api.processing_route import JobApi
from earthx.catalog.registry import DatasetRegistry
from earthx.objectstore.errors import StoreConfigError

pytestmark = pytest.mark.anyio


def listen_connections(conn) -> int:
    # An autocommit connection: inside a transaction `pg_stat_activity` keeps its first snapshot.
    row = conn.execute(
        "SELECT count(*) FROM pg_stat_activity WHERE application_name = %s AND datname = current_database()",
        (APPLICATION_NAME,),
    ).fetchone()
    return row[0]


class TestStart:
    async def test_the_lifespan_opens_what_the_routes_need_and_closes_it_again(self, require_postgres_env) -> None:
        conn = psycopg.connect(autocommit=True)
        app = main.build_app(DatasetRegistry(()))
        assert app.state.earthx_job_api is None
        async with app.router.lifespan_context(app):
            api = app.state.earthx_job_api
            assert isinstance(api, JobApi)
            assert api.events.listening and listen_connections(conn) >= 1
            assert api.operators is app.state.earthx_operators
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                assert (await client.get("/processing/conformance")).json() == {"conformsTo": []}
                gone = await client.get("/processing/jobs/" + "A" * 22)
                assert gone.status_code == 404 and gone.headers["content-type"] == "application/problem+json"
                assert (await client.get("/health")).status_code == 200, "the compose healthcheck is unchanged"
        assert app.state.earthx_job_api is None
        assert not api.events.listening
        for _ in range(100):  # the server notices the closed connection a moment later
            if listen_connections(conn) == 0:
                break
            await asyncio.sleep(0.05)
        assert listen_connections(conn) == 0, "the process gives its LISTEN connection back"

    @pytest.mark.parametrize(
        "name",
        ["S3_ENDPOINT", "S3_PUBLIC_ENDPOINT", "S3_REGION", "S3_BUCKET", "S3_ACCESS_KEY", "S3_SECRET_KEY"],
    )
    async def test_without_the_object_stores_configuration_it_does_not_start(
        self, name: str, monkeypatch: pytest.MonkeyPatch, require_postgres_env
    ) -> None:
        monkeypatch.delenv(name)
        app = main.build_app(DatasetRegistry(()))
        with pytest.raises(StoreConfigError) as raised:
            async with app.router.lifespan_context(app):
                pytest.fail("the process started without the object store's configuration")
        assert name in str(raised.value)
        assert "GKtestaccesskey0001" not in str(raised.value) and "test-secret-key" not in str(raised.value)

    async def test_a_key_in_a_file_that_cannot_be_read_stops_the_start_without_naming_the_path_content(
        self, monkeypatch: pytest.MonkeyPatch, require_postgres_env
    ) -> None:
        monkeypatch.delenv("S3_ACCESS_KEY")
        monkeypatch.setenv("S3_ACCESS_KEY_FILE", "/nonexistent/access_key")
        app = main.build_app(DatasetRegistry(()))
        with pytest.raises(StoreConfigError, match="S3_ACCESS_KEY_FILE"):
            async with app.router.lifespan_context(app):
                pytest.fail("started")
