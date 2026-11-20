"""Databases of a test run of their own (NM4-23, Otto 26.10.2026: question 3, option 1; M5-61 F2).

The T-C tests share one database when they run one after another: they create and drop tables in
transactions they roll back, drop the `pgstac` schema, and `earthx.catalog.load` commits. Side by
side in several processes they would block or see each other's work, so each process gets a
database of its own, made the way a deployment makes its own: PostGIS, the pgstac migrations from
the pinned `pypgstac`, then the earthx migrations. NM4-23 left the last step out, so the tables
existed only in a worker that had run `earthx.catalog.load` before (DS-04a). The tests that check
the migrations themselves make a database of their own, empty (`create_worker_database(...,
migrate_earthx=False)`).

Every run has an id of its own (M5-61 §3.1 point 2). Its databases are named
``<configured>_t<run>_<part>``: the template ``tpl``, migrated once per run, then one copy per
xdist worker (``gw0``, ...) or ``main`` in a serial run. Two runs on the same Postgres therefore never
touch each other's databases, and none writes to the configured one, which only carries the
administrative connections. While a run lasts, a connection of its own holds an advisory lock on
its id; a run that starts drops the databases of runs whose lock nobody holds, what a killed run
left behind, and never those of a run still going.

The checks of `require_postgres_env` come first: no database is made on a host that is not local,
and with nothing configured nothing happens. A `PGHOSTADDR` or `PGSERVICE` could point libpq
elsewhere than `PGHOST` says, so with either of them none is made either. Nor when the local
Postgres does not answer. In each case the T-C tests then fail with the message of their
fixtures, and every other test runs.
"""

from __future__ import annotations

import os
import re
import secrets
from collections.abc import Mapping, MutableMapping
from dataclasses import dataclass

import psycopg
from dotenv import load_dotenv
from psycopg import sql
from pypgstac.db import PgstacDB
from pypgstac.migrate import Migrate

from earthx.catalog.schema import apply_migrations
from tests.integration.conftest import _ENV_FILE, is_local_host, missing_postgres_env

#: First key of the two-key advisory lock a run holds; the second is its id.
LOCK_CLASS = 0x4D3631

_RUN_ID = re.compile(r"^[0-9a-f]{7}$")


def new_run_id() -> str:
    """Seven hex digits: unique enough per Postgres, and positive as the 32-bit key of the lock."""
    return secrets.token_hex(4)[:7]


def run_database_name(configured: str, run: str, part: str) -> str:
    """``earthx``, ``1a2b3c4`` and ``gw2`` give ``earthx_t1a2b3c4_gw2``."""
    if not _RUN_ID.match(run):
        raise ValueError("a run id is seven hex digits")
    return f"{configured}_t{run}_{part}"


def worker_database_name(current: str, part: str) -> str:
    """A database next to ``current`` for one test: ``earthx_t1a2b3c4_gw1`` and ``probe`` give ``…_gw1_probe``."""
    return f"{current}_{part}"


def create_worker_database(name: str, *, migrate_earthx: bool = True) -> None:
    """Drop what may be left under that name, then make it and migrate it.

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
        # `close` closes the pool, not the connection the migration still holds; a template with a session
        # on it cannot be copied.
        pgstac.disconnect()
        pgstac.close()
    if migrate_earthx:
        with psycopg.connect(dbname=name) as connection:
            apply_migrations(connection)
            connection.commit()


def copy_database(template: str, name: str) -> None:
    """``name`` as a copy of ``template``, which nobody may be connected to."""
    with psycopg.connect(autocommit=True) as admin:
        admin.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name)))
        admin.execute(sql.SQL("CREATE DATABASE {} TEMPLATE {}").format(sql.Identifier(name), sql.Identifier(template)))


def drop_worker_database(name: str, configured: str) -> None:
    """Drop it from a connection to the configured database, never to the one being dropped."""
    with psycopg.connect(dbname=configured, autocommit=True) as admin:
        admin.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name)))


def load_session_env() -> None:
    """`.env.test` of the cloud session, as `_postgres_env` reads it; real variables win."""
    load_dotenv(_ENV_FILE, override=False)


def may_make_databases(environ: Mapping[str, str]) -> bool:
    if missing_postgres_env(environ) or not is_local_host(environ["PGHOST"]):
        return False
    return not (environ.get("PGHOSTADDR") or environ.get("PGSERVICE"))


@dataclass
class TestRun:
    """The run's id, the configured database, the connection that holds the lock and the migrated template."""

    __test__ = False  # not a test class, whatever its name

    run: str
    configured: str
    lock: psycopg.Connection
    template: str

    def end(self) -> None:
        try:
            drop_worker_database(self.template, self.configured)
        finally:
            self.lock.close()


def drop_left_over(admin: psycopg.Connection, configured: str, own: str) -> list[str]:
    """Drop the databases of runs whose lock nobody holds; the names dropped."""
    pattern = re.compile(rf"^{re.escape(configured)}_t([0-9a-f]{{7}})_")
    names = [row[0] for row in admin.execute("SELECT datname FROM pg_database ORDER BY datname").fetchall()]
    dropped = []
    for name in names:
        match = pattern.match(name)
        if match is None or match[1] == own:
            continue
        key = (LOCK_CLASS, int(match[1], 16))
        if not admin.execute("SELECT pg_try_advisory_lock(%s, %s)", key).fetchone()[0]:
            continue
        try:
            admin.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name)))
            dropped.append(name)
        finally:
            admin.execute("SELECT pg_advisory_unlock(%s, %s)", key)
    return dropped


def start_run(environ: Mapping[str, str] = os.environ) -> TestRun | None:
    """Take a run id and its lock, drop what killed runs left, and migrate the run's template; ``None`` if none may be made."""
    if not may_make_databases(environ):
        return None
    run = new_run_id()
    configured = environ["PGDATABASE"]
    try:
        lock = psycopg.connect(autocommit=True)
    except psycopg.OperationalError:
        return None
    try:
        lock.execute("SELECT pg_advisory_lock(%s, %s)", (LOCK_CLASS, int(run, 16)))
        drop_left_over(lock, configured, run)
        template = run_database_name(configured, run, "tpl")
        create_worker_database(template)
    except BaseException:
        lock.close()
        raise
    return TestRun(run, configured, lock, template)


def use_run_database(
    run: str, configured: str, part: str, environ: MutableMapping[str, str] = os.environ
) -> tuple[str, str] | None:
    """Point ``PGDATABASE`` at a fresh copy of the run's template for ``part`` (a worker, or ``main``).

    Returns the new database and the configured one, or ``None`` if none may be made. The run's
    template exists by then, so a copy that fails is an error, never a quiet fall back to the
    configured database.
    """
    if not may_make_databases(environ):
        return None
    name = run_database_name(configured, run, part)
    copy_database(run_database_name(configured, run, "tpl"), name)
    environ["PGDATABASE"] = name
    return name, configured
