"""T-C: the migration runner against a real Postgres.

pgstac keeps its own migrations; this runner is only for what EarthX adds next to it.
What it has to get right is the part that is easy to get wrong: applying a file and
recording it together, noticing a file that changed after it was applied, and doing
nothing on a second run.
"""

from __future__ import annotations

import psycopg
import pytest

from earthx.catalog.schema import (
    MIGRATIONS_DIR,
    MigrationError,
    applied_migrations,
    apply_migrations,
    discover_migrations,
    ensure_bookkeeping,
)
from tests.integration.conftest import is_local_host, missing_postgres_env


def _forget_migrations(conn) -> None:
    """Start from a database that has never seen these migrations.

    Both tables, because ``earthx.catalog.load`` commits: after a full run the
    database really has the bookkeeping row of the shipped migration and the table it
    created, and a test that reuses version 002 for a file of its own would otherwise
    read that row as "the same migration, edited".
    """
    conn.execute("DROP TABLE IF EXISTS earthx_migrations")
    conn.execute("DROP TABLE IF EXISTS public.earthx_search_cache")


class TestDiscovery:
    def test_the_only_shipped_migration_is_the_search_cache(self) -> None:
        """pgstac holds the collections; our own first table is M1-06's cache (E4)."""
        assert [(m.version, m.name) for m in discover_migrations()] == [("002", "search_cache")]

    def test_a_missing_directory_is_an_error_not_an_empty_run(self, tmp_path) -> None:
        """A typo in a path must not read as "nothing to apply"."""
        with pytest.raises(MigrationError, match="not a directory"):
            discover_migrations(tmp_path / "typo")

    def test_a_badly_named_file_is_an_error_not_a_skip(self, tmp_path) -> None:
        """A migration nobody notices is exactly what this guards against."""
        (tmp_path / "add_cache.sql").write_text("SELECT 1;")
        with pytest.raises(MigrationError, match="nnn"):
            discover_migrations(tmp_path)

    def test_two_files_with_the_same_number_are_an_error(self, tmp_path) -> None:
        (tmp_path / "001_a.sql").write_text("SELECT 1;")
        (tmp_path / "001_b.sql").write_text("SELECT 2;")
        with pytest.raises(MigrationError, match="duplicate"):
            discover_migrations(tmp_path)


class TestApplying:
    def test_a_fresh_database_gets_every_migration(self, conn, tmp_path) -> None:
        _forget_migrations(conn)
        (tmp_path / "001_first.sql").write_text("CREATE TEMP TABLE first_step (id int);")
        (tmp_path / "002_second.sql").write_text("CREATE TEMP TABLE second_step (id int);")

        assert apply_migrations(conn, tmp_path) == ("001", "002")
        assert set(applied_migrations(conn)) == {"001", "002"}

    def test_a_second_run_applies_nothing(self, conn, tmp_path) -> None:
        _forget_migrations(conn)
        (tmp_path / "001_first.sql").write_text("CREATE TEMP TABLE first_step (id int);")
        apply_migrations(conn, tmp_path)
        assert apply_migrations(conn, tmp_path) == ()

    def test_the_runner_brings_its_own_bookkeeping_table(self, conn) -> None:
        """It is the runner's, not a migration — otherwise every directory needs a copy."""
        _forget_migrations(conn)
        assert applied_migrations(conn) == {}

        apply_migrations(conn)
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('earthx_migrations')")
            assert cur.fetchone()[0] is not None

    def test_ensure_bookkeeping_runs_twice_without_complaint(self, conn) -> None:
        _forget_migrations(conn)
        ensure_bookkeeping(conn)
        ensure_bookkeeping(conn)
        assert applied_migrations(conn) == {}

    def test_an_edited_migration_is_refused(self, conn, tmp_path) -> None:
        """Editing an applied migration would leave databases silently different."""
        (tmp_path / "001_thing.sql").write_text("CREATE TEMP TABLE thing (id int);")
        apply_migrations(conn, tmp_path)

        (tmp_path / "001_thing.sql").write_text("CREATE TEMP TABLE thing (id bigint);")
        with pytest.raises(MigrationError, match="changed after it was applied"):
            apply_migrations(conn, tmp_path)

    def test_a_failing_migration_records_nothing(self, conn, tmp_path) -> None:
        """File and bookkeeping row go in one transaction, or neither does.

        No rollback here on purpose: rolling back would also undo the bookkeeping
        table and make ``applied_migrations`` return {} whatever the runner did — the
        assertion would then hold even without a transaction around the migration.
        The savepoint is what leaves the connection usable after the failure, so
        reading the bookkeeping straight afterwards is the actual test.
        """
        (tmp_path / "001_broken.sql").write_text("CREATE TEMP TABLE ok (id int); SELECT no_such_function();")
        with pytest.raises(psycopg.errors.UndefinedFunction):
            apply_migrations(conn, tmp_path)

        assert "001" not in applied_migrations(conn)

    def test_a_failure_leaves_the_migrations_before_it_applied(self, conn, tmp_path) -> None:
        """Each migration is its own savepoint, so the run stops where it broke."""
        _forget_migrations(conn)
        (tmp_path / "001_first.sql").write_text("CREATE TEMP TABLE first_step (id int);")
        (tmp_path / "002_broken.sql").write_text("SELECT no_such_function();")

        with pytest.raises(psycopg.errors.UndefinedFunction):
            apply_migrations(conn, tmp_path)

        applied = applied_migrations(conn)
        assert "001" in applied
        assert "002" not in applied

    def test_a_later_migration_is_applied_on_top(self, conn, tmp_path) -> None:
        _forget_migrations(conn)
        (tmp_path / "001_first.sql").write_text("CREATE TEMP TABLE first_step (id int);")
        assert apply_migrations(conn, tmp_path) == ("001",)

        (tmp_path / "002_second.sql").write_text("CREATE TEMP TABLE second_step (id int);")
        assert apply_migrations(conn, tmp_path) == ("002",)


def test_the_migrations_directory_says_what_lies_in_it_and_why() -> None:
    """A numbering that starts at 002 reads as a lost file unless it is explained."""
    readme = (MIGRATIONS_DIR / "README.md").read_text(encoding="utf-8")
    assert "002_search_cache.sql" in readme
    assert "M1-06" in readme


class TestTheGuardsOnTheFixtures:
    """The path that may break without anyone noticing, because it hides the others."""

    def test_every_required_variable_is_reported(self) -> None:
        assert missing_postgres_env({}) == ("PGHOST", "PGUSER", "PGDATABASE")

    def test_an_empty_value_counts_as_missing(self) -> None:
        env = {"PGHOST": "", "PGUSER": "earthx", "PGDATABASE": "earthx"}
        assert missing_postgres_env(env) == ("PGHOST",)

    def test_a_complete_environment_reports_nothing(self) -> None:
        env = {"PGHOST": "127.0.0.1", "PGUSER": "earthx", "PGDATABASE": "earthx"}
        assert missing_postgres_env(env) == ()

    @pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1", "postgres"])
    def test_local_hosts_are_allowed(self, host: str) -> None:
        assert is_local_host(host)

    @pytest.mark.parametrize("host", ["db.example.com", "10.0.0.5", "127.0.0.1.example.com"])
    def test_anything_else_is_not(self, host: str) -> None:
        """These tests drop schemas; a shared database must not be reachable by accident."""
        assert not is_local_host(host)
