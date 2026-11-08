"""One database per pytest-xdist worker (NM4-23, Otto 26.10.2026: question 3, option 1).

The T-C tests share the configured database when they run one after another: they create
and drop tables in transactions they roll back, drop the `pgstac` schema, and
`earthx.catalog.load` commits. Side by side in several processes they would block or see
each other's work. So each worker gets a database of its own, made the way a deployment makes its own: PostGIS,
the pgstac migrations from the pinned `pypgstac`, then the earthx migrations. NM4-23 left the
last step out, so the tables existed only in a worker that had run `earthx.catalog.load`
before; materialize, mixed-search, item-holding and tiler tests failed in the others, by the
order the workers happened to get their tests (DS-04a). The tests that check the migrations
themselves make a database of their own, empty (`create_worker_database(..., migrate_earthx=False)`).

The checks of `require_postgres_env` come first: no database is made on a host that is not
local, and with nothing configured nothing happens. A `PGHOSTADDR` or `PGSERVICE` could point
libpq elsewhere than `PGHOST` says, so with either of them none is made either. Nor when the
local Postgres does not answer. In each case the T-C tests then fail with the message of their
fixtures, as they would in a serial run, and every other test runs.
"""

from __future__ import annotations

import os
from collections.abc import MutableMapping

import psycopg
from dotenv import load_dotenv
from psycopg import sql
from pypgstac.db import PgstacDB
from pypgstac.migrate import Migrate

from earthx.catalog.schema import apply_migrations
from tests.integration.conftest import _ENV_FILE, is_local_host, missing_postgres_env


def worker_database_name(configured: str, worker: str) -> str:
    """``earthx`` and ``gw2`` give ``earthx_gw2``."""
    return f"{configured}_{worker}"


def create_worker_database(name: str, *, migrate_earthx: bool = True) -> None:
    """Drop what a killed run may have left under that name, then make it and migrate it.

    With ``migrate_earthx=False`` only pgstac is migrated: the empty database the tests of the
    earthx migrations themselves start from.
    """
    with psycopg.connect(autocommit=True) as admin:
        admin.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name)))
        # From template0: CREATE DATABASE refuses a template another session is connected to,
        # and tests connect to template1 (test_startup.py, test_worker.py).
        admin.execute(sql.SQL("CREATE DATABASE {} TEMPLATE template0").format(sql.Identifier(name)))
    with psycopg.connect(dbname=name, autocommit=True) as connection:
        connection.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    pgstac = PgstacDB(dsn=psycopg.conninfo.make_conninfo(dbname=name))
    try:
        Migrate(pgstac).run_migration()
    finally:
        pgstac.close()
    if migrate_earthx:
        with psycopg.connect(dbname=name) as connection:
            apply_migrations(connection)
            connection.commit()


def drop_worker_database(name: str, configured: str) -> None:
    """Drop it from a connection to the configured database, never to the one being dropped."""
    with psycopg.connect(dbname=configured, autocommit=True) as admin:
        admin.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name)))


def load_session_env() -> None:
    """`.env.test` of the cloud session, as `_postgres_env` reads it; real variables win."""
    load_dotenv(_ENV_FILE, override=False)


def use_worker_database(worker: str, environ: MutableMapping[str, str] = os.environ) -> tuple[str, str] | None:
    """Point ``PGDATABASE`` at a fresh database for ``worker``.

    Returns the worker's database and the configured one, or ``None`` if none was made.
    """
    if missing_postgres_env(environ) or not is_local_host(environ["PGHOST"]):
        return None
    if environ.get("PGHOSTADDR") or environ.get("PGSERVICE"):
        return None
    name = worker_database_name(environ["PGDATABASE"], worker)
    try:
        create_worker_database(name)
    except psycopg.OperationalError:
        return None
    configured, environ["PGDATABASE"] = environ["PGDATABASE"], name
    return name, configured
