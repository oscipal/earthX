"""T-C: the tables of the overview pyramid against a real Postgres (M5-30b part 8b, migration 018).

What the migration promises and a read of the SQL does not prove: one function names a version in the key and the
request carries it as a generated column, a request is idempotent per dataset and version, and a pyramid row cannot
be in a state that contradicts its columns (a failure without a kind, a ready pyramid without a time, a lease on a
pyramid that is not building).
"""

from __future__ import annotations

import hashlib

import psycopg
import pytest

from earthx.catalog.schema import discover_migrations

from .conftest import SHIPPED_TABLES


@pytest.fixture
def schema(conn: psycopg.Connection) -> psycopg.Connection:
    for table in SHIPPED_TABLES:
        conn.execute(f"DROP TABLE IF EXISTS {table}")
    for migration in discover_migrations():
        conn.execute(migration.sql)
    return conn


def _overview(conn: psycopg.Connection, status: str, **columns: object) -> None:
    values = {"dataset_id": "d", "version": "0123456789abcdef", "status": status, **columns}
    conn.execute(
        f"INSERT INTO public.earthx_overview ({', '.join(values)}) VALUES ({', '.join(['%s'] * len(values))})",
        tuple(values.values()),
    )


def test_the_version_is_sixteen_hex_digits_of_the_sha256(schema: psycopg.Connection) -> None:
    for source_version in ('"etag-1"', "2026-01-01T00:00:00Z", "ä/ö"):
        row = schema.execute("SELECT public.earthx_overview_version(%s)", (source_version,)).fetchone()
        assert row == (hashlib.sha256(source_version.encode()).hexdigest()[:16],)


def test_a_request_carries_the_version_of_its_source_version(schema: psycopg.Connection) -> None:
    schema.execute("INSERT INTO public.earthx_overview_request (dataset_id, source_version) VALUES ('d', 'v1')")
    row = schema.execute(
        "SELECT version = public.earthx_overview_version(source_version) FROM public.earthx_overview_request"
    ).fetchone()
    assert row == (True,)


def test_a_request_cannot_be_given_a_version_by_hand(schema: psycopg.Connection) -> None:
    with pytest.raises(psycopg.errors.GeneratedAlways), schema.transaction():
        schema.execute(
            "INSERT INTO public.earthx_overview_request (dataset_id, source_version, version) VALUES ('d', 'v1', 'x')"
        )


def test_one_request_per_dataset_and_source_version(schema: psycopg.Connection) -> None:
    schema.execute("INSERT INTO public.earthx_overview_request (dataset_id, source_version) VALUES ('d', 'v1')")
    schema.execute("INSERT INTO public.earthx_overview_request (dataset_id, source_version) VALUES ('d', 'v2')")
    schema.execute("INSERT INTO public.earthx_overview_request (dataset_id, source_version) VALUES ('e', 'v1')")
    with pytest.raises(psycopg.errors.UniqueViolation), schema.transaction():
        schema.execute("INSERT INTO public.earthx_overview_request (dataset_id, source_version) VALUES ('d', 'v1')")


def test_one_overview_per_dataset_and_version(schema: psycopg.Connection) -> None:
    _overview(schema, "failed", failure_kind="unknown")
    with pytest.raises(psycopg.errors.UniqueViolation), schema.transaction():
        _overview(schema, "failed", failure_kind="unknown")


@pytest.mark.parametrize("version", ["", "0123456789ABCDEF", "0123456789abcde", "0123456789abcdefg", "../etc/passwd"])
def test_a_version_that_cannot_be_part_of_a_key_is_refused(schema: psycopg.Connection, version: str) -> None:
    with pytest.raises(psycopg.errors.CheckViolation), schema.transaction():
        _overview(schema, "failed", failure_kind="unknown", version=version)


def test_a_status_outside_the_three_is_refused(schema: psycopg.Connection) -> None:
    with pytest.raises(psycopg.errors.CheckViolation), schema.transaction():
        _overview(schema, "done")


@pytest.mark.parametrize(
    ("status", "columns"),
    [
        ("failed", {}),  # a failure without a kind
        ("building", {"failure_kind": "unknown", "lease_until": "2030-01-01"}),  # a kind on a pyramid that did not fail
        ("ready", {"checked_at": None}),  # ready without a time
        ("ready", {"checked_at": "2030-01-01", "lease_until": "2030-01-01"}),  # a lease on a pyramid that is not building
        ("building", {}),  # building without a lease
    ],
)
def test_a_row_that_contradicts_itself_is_refused(schema: psycopg.Connection, status: str, columns: dict) -> None:
    with pytest.raises(psycopg.errors.CheckViolation), schema.transaction():
        _overview(schema, status, **columns)


def test_the_states_that_make_sense_are_accepted(schema: psycopg.Connection) -> None:
    _overview(schema, "building", version="0000000000000001", lease_until="2030-01-01")
    _overview(schema, "ready", version="0000000000000002", checked_at="2030-01-01")
    _overview(schema, "failed", version="0000000000000003", failure_kind="source_timeout")
    row = schema.execute(
        "SELECT status, attempts, progress, base_hashes, hosts FROM public.earthx_overview ORDER BY version"
    ).fetchall()
    assert [r[0] for r in row] == ["building", "ready", "failed"]
    assert all(r[1:] == (1, 0, {}, []) for r in row)


@pytest.mark.parametrize("progress", [-1, 101])
def test_progress_is_a_percentage(schema: psycopg.Connection, progress: int) -> None:
    with pytest.raises(psycopg.errors.CheckViolation), schema.transaction():
        _overview(schema, "failed", failure_kind="unknown", progress=progress)
