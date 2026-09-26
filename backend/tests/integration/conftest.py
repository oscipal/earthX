"""T-C fixtures: a real Postgres, in the cloud session and in CI (adr/0002 §2).

Two decisions here are deliberate and worth keeping:

* **No skipping.** A T-C test that skips itself when the database is missing would be
  green in both places it is supposed to run and would never be noticed. adr/0002 §6
  says every test runs in at least two places or is marked ``local_only``; a test that
  quietly runs nowhere is the third case, which is an error. Missing connection
  details fail with a message that says what to set.
* **No mocking.** The point of T-C is that pgstac really answers (CLAUDE.md: nothing
  is mocked, nothing replaced).

Every test runs in a transaction that is rolled back afterwards, so tests do not see
each other's collections and the developer's database is left as it was found.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator, Mapping
from pathlib import Path

import psycopg
import pytest
from dotenv import load_dotenv

# Written by scripts/setup-cloud-session.sh. Reading it here is what lets a session
# run the same bare `pytest` that CI runs (adr/0002 §6); CI sets the variables on the
# job instead, and real environment variables win over the file either way.
_ENV_FILE = Path(__file__).resolve().parents[3] / ".env.test"

# libpq reads these itself; PGHOST is the one that decides whether anything was set up
# at all. scripts/setup-cloud-session.sh writes them, CI sets them on the job.
_REQUIRED_ENV = ("PGHOST", "PGUSER", "PGDATABASE")

# These tests drop and recreate schemas. libpq is C code, so the no_network guard in
# backend/tests/conftest.py never sees psycopg's connections and cannot stop them —
# the check that the database is a local throwaway has to happen here.
_LOCAL_HOSTS = frozenset({"127.0.0.1", "::1", "localhost", "postgres"})

_REMOTE_DB = """\
PGHOST is {host}, which is not a local database.

These tests drop schemas and write collections; they are meant for the throwaway
Postgres of a cloud session or a CI service container, never for anything shared.
Point PGHOST at one of: {allowed}.
"""

_MISSING_DB = """\
No Postgres for the T-C tests. They run in the cloud session and in CI
(docs/adr/0002-testaufteilung.md §2) and are not skipped, because a test that skips
itself in both places is a test that never runs.

Missing: {missing}

In a cloud session: scripts/setup-cloud-session.sh sets these up and writes .env.test,
which these tests read.
Locally: point PGHOST/PGPORT/PGUSER/PGPASSWORD/PGDATABASE at a Postgres with PostGIS
and run `pypgstac migrate` against it.
"""


# One table per migration this package ships. Listed rather than derived from the SQL,
# so that a migration whose table nobody drops fails the suite instead of leaving a
# table behind that the next run reads as "already applied" — `earthx.catalog.load`
# commits, so a full run really does leave them there.
SHIPPED_TABLES = ("public.earthx_search_cache", "public.earthx_stats_cache", "public.earthx_materialize_runs")


@pytest.fixture(scope="session", autouse=True)
def _postgres_env() -> None:
    if _ENV_FILE.exists():
        load_dotenv(_ENV_FILE, override=False)


def missing_postgres_env(environ: Mapping[str, str]) -> tuple[str, ...]:
    """Which of the required variables are unset or empty. Its own function so the
    message it drives can be tested without taking the database away."""
    return tuple(name for name in _REQUIRED_ENV if not environ.get(name))


def is_local_host(host: str) -> bool:
    return host in _LOCAL_HOSTS


@pytest.fixture(scope="session")
def require_postgres_env(_postgres_env: None) -> None:
    """Stop with a usable message rather than a connection error or a silent skip."""
    missing = missing_postgres_env(os.environ)
    if missing:
        pytest.fail(_MISSING_DB.format(missing=", ".join(missing)), pytrace=False)
    host = os.environ["PGHOST"]
    if not is_local_host(host):
        pytest.fail(_REMOTE_DB.format(host=host, allowed=", ".join(sorted(_LOCAL_HOSTS))), pytrace=False)


@pytest.fixture
def anyio_backend() -> str:
    """The async T-C tests run on asyncio, through the plugin `anyio` ships."""
    return "asyncio"


@pytest.fixture
async def aconn(require_postgres_env: None) -> AsyncIterator[psycopg.AsyncConnection]:
    """The same throwaway database, for the code that talks to it asynchronously.

    The application cache is read and written from the async API process, so its tests
    use the async driver rather than proving something about a connection nobody uses.
    Rolled back like its synchronous sibling.
    """
    try:
        connection = await psycopg.AsyncConnection.connect(autocommit=False)
    except psycopg.OperationalError as error:
        pytest.fail(f"Postgres is configured but not reachable: {error}", pytrace=False)
    try:
        yield connection
    finally:
        await connection.rollback()
        await connection.close()


@pytest.fixture
def conn(require_postgres_env: None) -> Iterator[psycopg.Connection]:
    """A connection whose work is rolled back when the test ends."""
    try:
        # libpq takes host, user, password and database from the environment.
        connection = psycopg.connect(autocommit=False)
    except psycopg.OperationalError as error:
        pytest.fail(
            f"Postgres is configured but not reachable: {error}\n"
            "In a cloud session: `service postgresql start`, or re-run "
            "scripts/setup-cloud-session.sh.",
            pytrace=False,
        )
    try:
        yield connection
    finally:
        connection.rollback()
        connection.close()
