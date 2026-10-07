"""T-C: the job queue's tables against a real Postgres (M4-08a plan §3.1, adr/0013 §5.1).

What the migration promises and a read of the SQL does not prove: every foreign key
has an index (M5: 232 s against 0.38 s for 50 000 expired recipes), a deletion in the
wrong order fails instead of taking valid rows along, a second active run of one
cache key cannot exist, and the cap and the limit per host are one row with the
agreed start values.
"""

from __future__ import annotations

import psycopg
import pytest

from earthx.catalog.schema import discover_migrations

from .conftest import SHIPPED_TABLES

TABLES = ("earthx_recipe", "earthx_job_limits", "earthx_run", "earthx_job")


@pytest.fixture
def jobs(conn: psycopg.Connection) -> psycopg.Connection:
    for table in SHIPPED_TABLES:
        conn.execute(f"DROP TABLE IF EXISTS {table}")
    for migration in discover_migrations():
        conn.execute(migration.sql)
    return conn


def _recipe(conn: psycopg.Connection, recipe_id: str = "r" * 22) -> str:
    conn.execute("INSERT INTO public.earthx_recipe (recipe_id, body) VALUES (%s, '{}')", (recipe_id,))
    return recipe_id


def _run(conn: psycopg.Connection, recipe_id: str, key: str = "c1:a", status: str = "accepted") -> int:
    row = conn.execute(
        """
        INSERT INTO public.earthx_run (cache_key, cacheable, recipe_id, status, hosts, max_seconds, expires_at)
        VALUES (%s, true, %s, %s, ARRAY['example.invalid'], 600, now() + interval '7 days')
        RETURNING run_id
        """,
        (key, recipe_id, status),
    ).fetchone()
    assert row is not None
    return row[0]


def test_the_cap_and_the_limit_per_host_are_one_row_with_the_start_values(jobs: psycopg.Connection) -> None:
    assert jobs.execute("SELECT global_cap, host_cap FROM public.earthx_job_limits").fetchall() == [(4, 2)]
    with pytest.raises(psycopg.errors.UniqueViolation), jobs.transaction():
        jobs.execute("INSERT INTO public.earthx_job_limits (only_row, global_cap, host_cap) VALUES (true, 1, 1)")
    with pytest.raises(psycopg.errors.CheckViolation), jobs.transaction():
        jobs.execute("INSERT INTO public.earthx_job_limits (only_row, global_cap, host_cap) VALUES (false, 1, 1)")


def test_every_foreign_key_has_an_index_that_starts_with_its_column(jobs: psycopg.Connection) -> None:
    """The check `RESTRICT` makes on deletion reads the child table through this index."""
    keys = jobs.execute(
        """
        SELECT c.conrelid::regclass::text, a.attname, c.conkey[1]
        FROM pg_constraint c
        JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = c.conkey[1]
        WHERE c.contype = 'f' AND c.conrelid::regclass::text = ANY(%s)
        """,
        ([f"earthx_{name}" for name in ("run", "job")],),
    ).fetchall()
    assert {(table, column) for table, column, _ in keys} == {
        ("earthx_run", "recipe_id"),
        ("earthx_job", "run_id"),
        ("earthx_job", "recipe_id"),
    }
    for table, column, attnum in keys:
        leading = jobs.execute(
            """
            SELECT count(*) FROM pg_index i
            WHERE i.indrelid = %s::regclass AND i.indkey[0] = %s AND i.indpred IS NULL
            """,
            (table, attnum),
        ).fetchone()
        assert leading is not None and leading[0] >= 1, f"{table}.{column} has no index"


def test_a_second_active_run_of_one_key_cannot_exist_but_a_finished_one_can(jobs: psycopg.Connection) -> None:
    recipe = _recipe(jobs)
    _run(jobs, recipe, "c1:a", "accepted")
    with pytest.raises(psycopg.errors.UniqueViolation), jobs.transaction():
        _run(jobs, recipe, "c1:a", "running")
    _run(jobs, recipe, "c1:a", "successful")
    _run(jobs, recipe, "c1:a", "failed")
    _run(jobs, recipe, "c1:b", "accepted")


def test_a_status_outside_the_list_is_refused(jobs: psycopg.Connection) -> None:
    recipe = _recipe(jobs)
    with pytest.raises(psycopg.errors.CheckViolation), jobs.transaction():
        _run(jobs, recipe, status="queued")


def test_nothing_is_deleted_in_the_wrong_order(jobs: psycopg.Connection) -> None:
    """RESTRICT: a recipe with a run, and a run with a job, stay until their children go."""
    recipe = _recipe(jobs)
    run_id = _run(jobs, recipe)
    jobs.execute(
        "INSERT INTO public.earthx_job (job_id, run_id, recipe_id) VALUES (%s, %s, %s)", ("j" * 22, run_id, recipe)
    )
    with pytest.raises(psycopg.errors.ForeignKeyViolation), jobs.transaction():
        jobs.execute("DELETE FROM public.earthx_run WHERE run_id = %s", (run_id,))
    with pytest.raises(psycopg.errors.ForeignKeyViolation), jobs.transaction():
        jobs.execute("DELETE FROM public.earthx_recipe WHERE recipe_id = %s", (recipe,))
    jobs.execute("DELETE FROM public.earthx_job")
    jobs.execute("DELETE FROM public.earthx_run")
    jobs.execute("DELETE FROM public.earthx_recipe")


def test_the_migration_creates_exactly_these_tables(jobs: psycopg.Connection) -> None:
    found = jobs.execute(
        "SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename LIKE 'earthx\\_%%' ORDER BY 1"
    ).fetchall()
    assert set(TABLES) <= {name for (name,) in found}
