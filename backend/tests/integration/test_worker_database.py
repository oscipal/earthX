"""One database per pytest-xdist worker (tests/worker_database.py; NM4-23, question 3).

Against the real Postgres like every T-C test. The test that makes a database names it after
the database this process runs on, so two workers never make the same one.
"""

from __future__ import annotations

import os
import re

import psycopg
import pytest

from tests import worker_database
from tests.worker_database import (
    create_worker_database,
    drop_worker_database,
    use_worker_database,
    worker_database_name,
)


def _no_connection(*args: object, **kwargs: object) -> None:
    raise AssertionError("no connection may be opened")


def test_the_name_is_the_configured_database_and_the_worker() -> None:
    assert worker_database_name("earthx", "gw2") == "earthx_gw2"


@pytest.mark.parametrize(
    "environ",
    [
        {"PGHOST": "db.example.invalid", "PGUSER": "earthx", "PGDATABASE": "earthx"},
        {"PGHOST": "10.0.0.5", "PGUSER": "earthx", "PGDATABASE": "earthx"},
        {"PGUSER": "earthx", "PGDATABASE": "earthx"},
        {},
    ],
    ids=["remote-name", "remote-address", "no-host", "nothing"],
)
def test_nothing_is_made_on_a_host_that_is_not_local_or_without_a_configuration(
    environ: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(worker_database.psycopg, "connect", _no_connection)
    before = dict(environ)
    assert use_worker_database("gw0", environ) is None
    assert environ == before


def test_this_process_runs_on_its_workers_database_or_on_the_configured_one(require_postgres_env: None) -> None:
    with psycopg.connect() as connection:
        current = connection.info.dbname
    worker = os.environ.get("PYTEST_XDIST_WORKER")
    if worker is None:
        assert not re.search(r"_gw\d+$", current), "a serial run keeps the configured database"
    else:
        assert current == os.environ["PGDATABASE"] and current.endswith(f"_{worker}")


def test_a_worker_database_is_made_empty_with_pgstac_and_dropped_again(require_postgres_env: None) -> None:
    configured = os.environ["PGDATABASE"]
    name = worker_database_name(configured, "probe")
    create_worker_database(name)
    try:
        create_worker_database(name)  # what a killed run left is dropped first
        with psycopg.connect(dbname=name) as connection:
            assert connection.execute("SELECT to_regnamespace('pgstac') IS NOT NULL").fetchone() == (True,)
            assert connection.execute("SELECT 1 FROM pg_extension WHERE extname = 'postgis'").fetchone() == (1,)
            assert connection.execute("SELECT to_regclass('public.earthx_migrations')").fetchone() == (None,)
    finally:
        drop_worker_database(name, configured)
    with psycopg.connect(dbname=configured) as connection:
        assert connection.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,)).fetchone() is None
