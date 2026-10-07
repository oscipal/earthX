"""Fixtures for the queue and the worker: a real Postgres of their own, and the object store double.

The queue tests need rows that really are committed (several connections, several
processes), which the rollback fixture of the T-C tests cannot give. So the session
creates a throwaway database next to the configured one, applies the migrations to
it, and drops it at the end. `PGDATABASE` points at it for every test, so a spawned
child and `psycopg.connect()` with no arguments find it too.

Like the T-C tests this never skips: a missing or non-local Postgres fails with a
message that says what to set (adr/0002 §2, tests/integration/conftest.py).
"""

from __future__ import annotations

import secrets
from collections.abc import Iterator

import psycopg
import pytest
from psycopg import sql

from earthx.catalog.schema import apply_migrations
from tests.integration.conftest import _postgres_env, require_postgres_env  # noqa: F401 - fixtures

from ..objectstore.conftest import store, store_env  # noqa: F401 - fixtures


@pytest.fixture(scope="session")
def jobs_database(require_postgres_env: None) -> Iterator[str]:  # noqa: F811 - the fixture it needs
    name = f"earthx_jobs_{secrets.token_hex(4)}"
    try:
        admin = psycopg.connect(autocommit=True)
    except psycopg.OperationalError as error:
        pytest.fail(f"Postgres is configured but not reachable: {error}", pytrace=False)
    try:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        with psycopg.connect(dbname=name) as connection:
            apply_migrations(connection)
        yield name
    finally:
        admin.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name)))
        admin.close()


@pytest.fixture
def db(jobs_database: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[psycopg.Connection]:
    """An autocommit connection to the throwaway database, with empty queue tables."""
    monkeypatch.setenv("PGDATABASE", jobs_database)
    connection = psycopg.connect(autocommit=True)
    reset(connection)
    try:
        yield connection
    finally:
        reset(connection)
        connection.close()


def reset(connection: psycopg.Connection) -> None:
    connection.execute("TRUNCATE public.earthx_job, public.earthx_run, public.earthx_recipe RESTART IDENTITY")
    connection.execute("UPDATE public.earthx_job_limits SET global_cap = 4, host_cap = 2")
