"""T-C: the migration runner against a real Postgres.

pgstac keeps its own migrations; this runner is only for what EarthX adds next to it.
What it has to get right is the part that is easy to get wrong: applying a file and
recording it together, noticing a file that changed after it was applied, and doing
nothing on a second run.
"""

from __future__ import annotations

import pytest

from earthx.catalog.schema import (
    MIGRATIONS_DIR,
    MigrationError,
    applied_migrations,
    apply_migrations,
    discover_migrations,
    ensure_bookkeeping,
)


def _drop_bookkeeping(conn) -> None:
    """Start from a database that has never seen these migrations."""
    conn.execute("DROP TABLE IF EXISTS earthx_migrations")


class TestDiscovery:
    def test_the_shipped_migrations_are_readable(self) -> None:
        """Empty in M1-04, and that is the point: pgstac holds the collections.

        The first own migration is the application cache of E4, in M1-06.
        """
        migrations = discover_migrations()
        assert [m.version for m in migrations] == sorted(m.version for m in migrations)

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
        _drop_bookkeeping(conn)
        (tmp_path / "001_first.sql").write_text("CREATE TEMP TABLE first_step (id int);")
        (tmp_path / "002_second.sql").write_text("CREATE TEMP TABLE second_step (id int);")

        assert apply_migrations(conn, tmp_path) == ("001", "002")
        assert set(applied_migrations(conn)) == {"001", "002"}

    def test_a_second_run_applies_nothing(self, conn, tmp_path) -> None:
        _drop_bookkeeping(conn)
        (tmp_path / "001_first.sql").write_text("CREATE TEMP TABLE first_step (id int);")
        apply_migrations(conn, tmp_path)
        assert apply_migrations(conn, tmp_path) == ()

    def test_the_runner_brings_its_own_bookkeeping_table(self, conn) -> None:
        """It is the runner's, not a migration — otherwise every directory needs a copy."""
        _drop_bookkeeping(conn)
        assert applied_migrations(conn) == {}

        apply_migrations(conn)
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('earthx_migrations')")
            assert cur.fetchone()[0] is not None

    def test_ensure_bookkeeping_runs_twice_without_complaint(self, conn) -> None:
        _drop_bookkeeping(conn)
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
        """File and bookkeeping row go in one transaction, or neither does."""
        (tmp_path / "001_broken.sql").write_text("CREATE TEMP TABLE ok (id int); SELECT no_such_function();")
        with pytest.raises(Exception, match="no_such_function"):
            apply_migrations(conn, tmp_path)
        conn.rollback()
        assert "001" not in applied_migrations(conn)

    def test_a_later_migration_is_applied_on_top(self, conn, tmp_path) -> None:
        (tmp_path / "001_first.sql").write_text("CREATE TEMP TABLE first_step (id int);")
        assert apply_migrations(conn, tmp_path) == ("001",)

        (tmp_path / "002_second.sql").write_text("CREATE TEMP TABLE second_step (id int);")
        assert apply_migrations(conn, tmp_path) == ("002",)


def test_the_migrations_directory_explains_why_it_is_empty() -> None:
    """An empty directory with no word on it reads as an oversight."""
    readme = (MIGRATIONS_DIR / "README.md").read_text(encoding="utf-8")
    assert "M1-06" in readme
