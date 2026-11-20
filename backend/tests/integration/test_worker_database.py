"""The databases of a test run (tests/worker_database.py; NM4-23, question 3; DS-04a; M5-61 F2).

Against the real Postgres like every T-C test. A test that makes a database names it after the
database this process runs on, so two workers or two runs never make the same one.
"""

from __future__ import annotations

import os
import re

import psycopg
import pytest
from psycopg import sql

from earthx.catalog.schema import applied_migrations, apply_migrations, discover_migrations
from tests import worker_database
from tests.integration.conftest import SHIPPED_TABLES
from tests.worker_database import (
    LOCK_CLASS,
    copy_database,
    create_worker_database,
    drop_left_over,
    drop_worker_database,
    run_database_name,
    start_run,
    use_run_database,
    worker_database_name,
)

RUN_DATABASE = re.compile(r"^(?P<configured>.+)_t(?P<run>[0-9a-f]{7})_(?P<part>gw\d+|main)$")


def _no_connection(*args: object, **kwargs: object) -> None:
    raise AssertionError("no connection may be opened")


def _this_run() -> re.Match[str]:
    match = RUN_DATABASE.match(os.environ["PGDATABASE"])
    assert match is not None, os.environ["PGDATABASE"]
    return match


def test_the_name_is_the_configured_database_the_run_and_the_part() -> None:
    assert run_database_name("earthx", "1a2b3c4", "gw2") == "earthx_t1a2b3c4_gw2"
    assert worker_database_name("earthx_t1a2b3c4_gw2", "probe") == "earthx_t1a2b3c4_gw2_probe"


@pytest.mark.parametrize("run", ["", "1a2b3c", "1a2b3c4d", "1A2B3C4", "1a2b3c;", "../../x"])
def test_a_run_id_is_seven_hex_digits(run: str) -> None:
    with pytest.raises(ValueError, match="seven hex digits"):
        run_database_name("earthx", run, "gw0")


@pytest.mark.parametrize(
    "environ",
    [
        {"PGHOST": "db.example.invalid", "PGUSER": "earthx", "PGDATABASE": "earthx"},
        {"PGHOST": "192.0.2.10", "PGUSER": "earthx", "PGDATABASE": "earthx"},
        {"PGHOST": "localhost", "PGHOSTADDR": "192.0.2.10", "PGUSER": "earthx", "PGDATABASE": "earthx"},
        {"PGHOST": "localhost", "PGSERVICE": "elsewhere", "PGUSER": "earthx", "PGDATABASE": "earthx"},
        {"PGUSER": "earthx", "PGDATABASE": "earthx"},
        {},
    ],
    ids=["remote-name", "remote-address", "local-name-remote-address", "service-file", "no-host", "nothing"],
)
def test_nothing_is_made_on_a_host_that_is_not_local_or_without_a_configuration(
    environ: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(worker_database.psycopg, "connect", _no_connection)
    before = dict(environ)
    assert start_run(environ) is None
    assert use_run_database("1a2b3c4", "earthx", "gw0", environ) is None
    assert environ == before


def test_a_local_postgres_that_does_not_answer_makes_none_and_stops_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    def unreachable(*args: object, **kwargs: object) -> None:
        raise psycopg.OperationalError("connection refused")

    monkeypatch.setattr(worker_database.psycopg, "connect", unreachable)
    environ = {"PGHOST": "127.0.0.1", "PGUSER": "earthx", "PGDATABASE": "earthx"}
    assert start_run(environ) is None
    assert environ["PGDATABASE"] == "earthx"


def test_this_process_runs_on_a_database_of_its_run_and_never_on_the_configured_one(require_postgres_env: None) -> None:
    with psycopg.connect() as connection:
        current = connection.info.dbname
    assert current == os.environ["PGDATABASE"]
    part = _this_run()["part"]
    assert part == os.environ.get("PYTEST_XDIST_WORKER", "main")


def test_the_run_holds_its_lock_while_it_lasts(require_postgres_env: None) -> None:
    run = int(_this_run()["run"], 16)
    with psycopg.connect(dbname=_this_run()["configured"], autocommit=True) as other:
        assert other.execute("SELECT pg_try_advisory_lock(%s, %s)", (LOCK_CLASS, run)).fetchone() == (False,)


def _make_empty(name: str, configured: str) -> None:
    with psycopg.connect(dbname=configured, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {} TEMPLATE template0").format(sql.Identifier(name)))


def _exists(name: str, configured: str) -> bool:
    with psycopg.connect(dbname=configured) as connection:
        return connection.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,)).fetchone() is not None


def test_a_run_drops_what_a_killed_run_left_and_nothing_of_a_run_still_going(require_postgres_env: None) -> None:
    this = _this_run()
    configured = this["configured"]
    dead, alive = "0dead00", "0a11ce0"
    dead_name = run_database_name(configured, dead, "gw0")
    alive_name = run_database_name(configured, alive, "gw0")
    unrelated = f"{configured}_tnotarun_gw0"
    for name in (dead_name, alive_name, unrelated):
        _make_empty(name, configured)
    holder = psycopg.connect(dbname=configured, autocommit=True)
    try:
        holder.execute("SELECT pg_advisory_lock(%s, %s)", (LOCK_CLASS, int(alive, 16)))
        with psycopg.connect(dbname=configured, autocommit=True) as admin:
            dropped = drop_left_over(admin, configured, this["run"])
        assert dead_name in dropped
        assert not _exists(dead_name, configured)
        assert _exists(alive_name, configured), "another run still holds its lock"
        assert _exists(unrelated, configured), "not a run's name"
        assert _exists(os.environ["PGDATABASE"], configured), "this run's own"
    finally:
        holder.close()
        for name in (dead_name, alive_name, unrelated):
            drop_worker_database(name, configured)


def test_a_copy_of_the_runs_template_has_pgstac_and_every_earthx_table(require_postgres_env: None) -> None:
    this = _this_run()
    configured = this["configured"]
    name = worker_database_name(os.environ["PGDATABASE"], "copy")
    copy_database(run_database_name(configured, this["run"], "tpl"), name)
    try:
        with psycopg.connect(dbname=name) as connection:
            assert connection.execute("SELECT to_regnamespace('pgstac') IS NOT NULL").fetchone() == (True,)
            assert set(applied_migrations(connection)) == {m.version for m in discover_migrations()}
        assert {table.removeprefix("public.") for table in SHIPPED_TABLES} <= _tables(name)
    finally:
        drop_worker_database(name, configured)


def _tables(name: str) -> set[str]:
    with psycopg.connect(dbname=name) as connection:
        return {row[0] for row in connection.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")}


def test_a_worker_database_has_pgstac_and_every_earthx_table_and_is_dropped_again(require_postgres_env: None) -> None:
    configured = os.environ["PGDATABASE"]
    name = worker_database_name(configured, "probe")
    create_worker_database(name)
    try:
        create_worker_database(name)  # what a killed run left is dropped first
        with psycopg.connect(dbname=name) as connection:
            assert connection.execute("SELECT to_regnamespace('pgstac') IS NOT NULL").fetchone() == (True,)
            assert connection.execute("SELECT 1 FROM pg_extension WHERE extname = 'postgis'").fetchone() == (1,)
            assert set(applied_migrations(connection)) == {m.version for m in discover_migrations()}
        assert {table.removeprefix("public.") for table in SHIPPED_TABLES} <= _tables(name)
    finally:
        drop_worker_database(name, configured)
    with psycopg.connect(dbname=configured) as connection:
        assert connection.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,)).fetchone() is None


def test_a_database_of_its_own_can_be_made_without_the_earthx_migrations(require_postgres_env: None) -> None:
    """What the tests of the migrations themselves start from: pgstac, no earthx table at all."""
    configured = os.environ["PGDATABASE"]
    name = worker_database_name(configured, "empty")
    create_worker_database(name, migrate_earthx=False)
    try:
        with psycopg.connect(dbname=name) as connection:
            assert connection.execute("SELECT to_regnamespace('pgstac') IS NOT NULL").fetchone() == (True,)
            assert applied_migrations(connection) == {}
            assert apply_migrations(connection) == tuple(m.version for m in discover_migrations())
        assert {table.removeprefix("public.") for table in SHIPPED_TABLES} <= _tables(name)
    finally:
        drop_worker_database(name, configured)
