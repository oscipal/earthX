"""One database per pytest-xdist worker (NM4-23, Otto 26.10.2026: question 3, option 1).

The T-C tests share the configured database when they run one after another: they create
and drop tables in transactions they roll back, drop the `pgstac` schema, and
`earthx.catalog.load` commits. Side by side in several processes they would block or see
each other's work. So each worker gets a database of its own, made empty the way CI makes
its own: PostGIS, then the pgstac migrations from the pinned `pypgstac`. The earthx
migrations are not applied here; the tests that need them apply them, as they do against
a fresh database in CI.

The checks of `require_postgres_env` come first: no database is made on a host that is not
local, and with nothing configured nothing happens. The T-C tests then fail with that
fixture's own message, as they would in a serial run.
"""

from __future__ import annotations

import os
from collections.abc import MutableMapping

import psycopg
from dotenv import load_dotenv
from psycopg import sql
from pypgstac.db import PgstacDB
from pypgstac.migrate import Migrate

from tests.integration.conftest import _ENV_FILE, is_local_host, missing_postgres_env


def worker_database_name(configured: str, worker: str) -> str:
    """``earthx`` and ``gw2`` give ``earthx_gw2``."""
    return f"{configured}_{worker}"


def create_worker_database(name: str) -> None:
    """Drop what a killed run may have left under that name, then make it empty and migrated."""
    with psycopg.connect(autocommit=True) as admin:
        admin.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name)))
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    with psycopg.connect(dbname=name, autocommit=True) as connection:
        connection.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    pgstac = PgstacDB(dsn=psycopg.conninfo.make_conninfo(dbname=name))
    try:
        Migrate(pgstac).run_migration()
    finally:
        pgstac.close()


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
    name = worker_database_name(environ["PGDATABASE"], worker)
    create_worker_database(name)
    configured, environ["PGDATABASE"] = environ["PGDATABASE"], name
    return name, configured
