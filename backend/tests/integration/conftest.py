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

import asyncio
import os
from collections.abc import AsyncIterator, Callable, Iterator, Mapping
from pathlib import Path

import psycopg
import pytest
from dotenv import load_dotenv

import earthx.api.main
from earthx.catalog.load import main as load_catalog
from earthx.catalog.registry import DatasetRegistry
from earthx.catalog.search_index import SearchIndexMismatch, write_search_index

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
SHIPPED_TABLES = (
    "public.earthx_search_cache",
    "public.earthx_stats_cache",
    "public.earthx_materialize_runs",
    "public.earthx_geocode_cache",
    "public.earthx_rate_slots",
    "public.earthx_job",
    "public.earthx_run",
    "public.earthx_job_limits",
    "public.earthx_recipe",
    "public.earthx_permalink",
    "public.earthx_bundle",
    "public.earthx_dataset_search",
    "public.earthx_mosaic_selection",
    "public.earthx_overview_request",
    "public.earthx_overview",
    "public.earthx_overview_upkeep",
    "public.earthx_overview_omitted",
    "public.earthx_overview_host",
    "public.earthx_region_part",
    "public.earthx_municipality",
    "public.earthx_region",
    "public.earthx_listing_batch_entry",
    "public.earthx_listing_batch",
    "public.earthx_listed_entry",
    "public.earthx_source_host",
    "public.earthx_source_lease",
    "public.earthx_state_transition",
    "public.earthx_record_state",
    "public.earthx_raw_record",
    "public.earthx_harvest_source",
    "public.earthx_harvest_run",
    "public.earthx_materialize_group",
    "public.earthx_materialize_unit",
)


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


@pytest.fixture(autouse=True)
def _object_store_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Since M4-08b `api` signs result links, so its lifespan needs the object store's configuration.

    Signing opens no connection (adr/0015 §3.2), so invented values are enough; the host is a
    reserved name, so nothing here can reach a real store.
    """
    for name, value in {
        "S3_ENDPOINT": "http://objectstore.invalid:3900",
        "S3_PUBLIC_ENDPOINT": "http://localhost:3900",
        "S3_REGION": "garage",
        "S3_BUCKET": "earthx",
        "S3_ACCESS_KEY": "GKtestaccesskey0001",
        "S3_SECRET_KEY": "test-secret-key-0000000000000000",
    }.items():
        monkeypatch.setenv(name, value)
    for name in ("S3_ACCESS_KEY_FILE", "S3_SECRET_KEY_FILE"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def _search_index_of_the_app(monkeypatch: pytest.MonkeyPatch) -> None:
    """Write the search index for the registry of the `api` a test starts where it is not that one, then run the start
    check unchanged.

    `api` refuses to start on an index that is not the one of its registry (M5-22 plan §3.4, A3). These tests build
    `api` with registries of their own; a deployment runs `catalog-load` with the registry of the process first, and
    this does the same for the test's registry, committed, right before the check. `test_search_index.py` puts the
    bare check back to test the refusal itself.

    Committed, unlike the rest of these tests: the check reads over a connection of the app's own pool. Every run has
    databases of its own (tests/worker_database.py), so nothing of this outlives it.
    """
    check = earthx.api.main.check_search_index

    def write(registry: DatasetRegistry) -> None:
        with psycopg.connect() as connection:
            write_search_index(connection, registry)
            connection.commit()

    async def write_then_check(registry: DatasetRegistry, conn: object) -> None:
        # Mostly the index an earlier start of the same registry wrote: then there is nothing to write. Each pass builds
        # the search texts, about a second (M5-61 §3.2).
        try:
            await check(registry, conn)
            return
        except SearchIndexMismatch:
            pass
        await asyncio.to_thread(write, registry)
        await check(registry, conn)

    monkeypatch.setattr(earthx.api.main, "check_search_index", write_then_check)


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


#: What `catalog-load` writes (`earthx/catalog/load.py`), plus the rows the overview of a prototype source leaves.
#: Not the index of the dataset search: every `api` a test starts writes it for its own registry first
#: (`_search_index_of_the_app`), so it changes with each test that brings a registry of its own, and no test reads
#: what `catalog-load` left in it.
CATALOGUE_TABLES = (
    "public.earthx_migrations",
    "pgstac.collections",
    "public.earthx_region",
    "public.earthx_region_part",
    "public.earthx_municipality",
    "public.earthx_listed_entry",
    "public.earthx_overview",
    "public.earthx_overview_request",
)


def catalogue_fingerprint() -> tuple[object, ...]:
    """Rows and the newest committed transaction of each catalogue table: whatever is written, deleted or rewritten
    changes one of the two. A table that is not there (pgstac dropped) gives ``None`` for it."""
    seen: list[object] = []
    with psycopg.connect(autocommit=True) as conn:
        for table in CATALOGUE_TABLES:
            try:
                seen.append(conn.execute(f"SELECT count(*), max(xmin::text::bigint) FROM {table}").fetchone())
            except psycopg.errors.UndefinedTable:
                seen.append(None)
    return tuple(seen)


class Catalogue:
    """The catalogue of the worker's database, loaded once and again only when a test changed it (M5-61 F1).

    The T-C tests of the API ran ``catalog-load`` before every test, 2.6 s and more each (M5-61 §2.3). Before a test
    :meth:`ensure` compares :func:`catalogue_fingerprint` with what it was right after the last load: the same, nothing
    happens; not the same, or another ``state`` was asked for, it undoes the last state (``undo``), loads, and sets up
    the one asked for (``setup``). A test that leaves the catalogue changed costs the next one a load, as before.
    """

    def __init__(self) -> None:
        self.state: str | None = None
        self.fingerprint: tuple[object, ...] | None = None
        self.undo: Callable[[], None] | None = None
        self.owner: str | None = None
        self.loads = 0

    def ensure(
        self,
        state: str = "registry",
        *,
        setup: Callable[[], None] | None = None,
        undo: Callable[[], None] | None = None,
        owner: str | None = None,
    ) -> None:
        """``owner``, the fixture that asks for a state with an ``undo``: :meth:`leave` keeps the state while the next
        test asks for that fixture too."""
        if state == self.state and catalogue_fingerprint() == self.fingerprint:
            return
        self.forget()
        assert load_catalog() == 0
        self.loads += 1
        if setup is not None:
            setup()
        self.state, self.undo, self.owner, self.fingerprint = state, undo, owner, catalogue_fingerprint()

    def forget(self) -> None:
        """Undo the state set up last, if it has an ``undo``; the next :meth:`ensure` loads."""
        undo = self.undo
        self.state, self.undo, self.owner, self.fingerprint = None, None, None, None
        if undo is not None:
            undo()

    def leave(self, next_fixtures: list[str] | None) -> None:
        """After a test: a state with an ``undo`` stays only for a next test that asks for its owner."""
        if self.undo is not None and (next_fixtures is None or self.owner not in next_fixtures):
            self.forget()


_CATALOGUE = pytest.StashKey[Catalogue]()


@pytest.fixture(scope="session")
def catalogue_state(require_postgres_env: None, pytestconfig: pytest.Config) -> Catalogue:
    return pytestconfig.stash.setdefault(_CATALOGUE, Catalogue())


@pytest.hookimpl(trylast=True)
def pytest_runtest_teardown(item: pytest.Item, nextitem: pytest.Item | None) -> None:
    catalogue = item.config.stash.get(_CATALOGUE, None)
    if catalogue is not None:
        catalogue.leave(None if nextitem is None else list(nextitem.fixturenames))


@pytest.fixture
def catalogue_loaded(catalogue_state: Catalogue) -> None:
    """The registry in pgstac and everything else `catalog-load` writes, as right after it ran."""
    catalogue_state.ensure()
