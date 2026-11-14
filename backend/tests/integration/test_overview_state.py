"""What the tile route learns of a pyramid from ``earthx_overview`` (M5-30b part 9, plan §8.11), against a real database."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import psycopg
import pytest

from earthx.catalog.pgstac import OverviewState, overview_state_async
from earthx.catalog.schema import discover_migrations

from .conftest import SHIPPED_TABLES

NOW = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)
FRESH_AFTER = NOW - timedelta(days=30)
DATASET = "cop-dem-glo-30"
V1, V2, V3 = "0123456789abcdef", "1123456789abcdef", "2123456789abcdef"

pytestmark = pytest.mark.anyio


@pytest.fixture
async def rows(aconn: psycopg.AsyncConnection) -> psycopg.AsyncConnection:
    """The tables of the migrations, fresh, inside the test's transaction."""
    for table in SHIPPED_TABLES:
        await aconn.execute(f"DROP TABLE IF EXISTS {table}")
    for migration in discover_migrations():
        await aconn.execute(migration.sql)
    return aconn


async def _row(
    conn: psycopg.AsyncConnection,
    version: str,
    status: str,
    *,
    created: datetime = NOW,
    checked: datetime | None = None,
    confirmed: datetime | None = None,
    kind: str | None = None,
    dataset: str = DATASET,
) -> None:
    await conn.execute(
        """
        INSERT INTO public.earthx_overview
            (dataset_id, version, status, failure_kind, checked_at, confirmed_at, lease_until, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, CASE WHEN %s = 'building' THEN now() + interval '1 hour' END, %s)
        """,
        (dataset, version, status, kind, checked, confirmed, status, created),
    )


async def _state(conn: psycopg.AsyncConnection, dataset: str = DATASET) -> OverviewState:
    return await overview_state_async(conn, dataset, fresh_after=FRESH_AFTER)


async def test_no_row_is_none(rows: psycopg.AsyncConnection) -> None:
    assert await _state(rows) == OverviewState("none")


async def test_a_ready_pyramid_within_its_term_is_ready_with_its_version(rows: psycopg.AsyncConnection) -> None:
    await _row(rows, V1, "ready", checked=NOW - timedelta(days=3))
    assert await _state(rows) == OverviewState("ready", V1)


async def test_the_newest_ready_pyramid_wins_and_a_build_of_a_newer_version_does_not_hide_it(
    rows: psycopg.AsyncConnection,
) -> None:
    await _row(rows, V1, "ready", created=NOW - timedelta(days=9), checked=NOW - timedelta(days=9))
    await _row(rows, V2, "ready", created=NOW - timedelta(days=2), checked=NOW - timedelta(days=2))
    await _row(rows, V3, "building", created=NOW)
    assert await _state(rows) == OverviewState("ready", V2)


async def test_a_ready_pyramid_past_its_term_is_failed_as_expired(rows: psycopg.AsyncConnection) -> None:
    await _row(rows, V1, "ready", checked=FRESH_AFTER - timedelta(seconds=1))
    assert await _state(rows) == OverviewState("failed", failure_kind="expired")


async def test_the_term_ends_where_the_caller_says_it_does(rows: psycopg.AsyncConnection) -> None:
    """A prototype source's term is 7 days: the caller asks with a later ``fresh_after``."""
    await _row(rows, V1, "ready", checked=NOW - timedelta(days=8), dataset="proto-x")
    assert await overview_state_async(rows, "proto-x", fresh_after=NOW - timedelta(days=30)) == OverviewState("ready", V1)
    assert await overview_state_async(rows, "proto-x", fresh_after=NOW - timedelta(days=7)) == OverviewState(
        "failed", failure_kind="expired"
    )


async def test_a_pyramid_the_source_confirmed_after_its_term_is_still_served_until_the_worker_extends_it(
    rows: psycopg.AsyncConnection,
) -> None:
    old = FRESH_AFTER - timedelta(hours=2)
    await _row(rows, V1, "ready", checked=old, confirmed=old + timedelta(days=29, hours=23))
    assert await _state(rows) == OverviewState("ready", V1)


async def test_a_confirmation_older_than_the_check_does_not_keep_a_pyramid(rows: psycopg.AsyncConnection) -> None:
    old = FRESH_AFTER - timedelta(hours=2)
    await _row(rows, V1, "ready", checked=old, confirmed=old - timedelta(days=1))
    assert await _state(rows) == OverviewState("failed", failure_kind="expired")


async def test_a_running_build_is_building_without_a_ready_pyramid(rows: psycopg.AsyncConnection) -> None:
    await _row(rows, V1, "building")
    assert await _state(rows) == OverviewState("building")


async def test_a_running_build_after_a_failure_is_building(rows: psycopg.AsyncConnection) -> None:
    await _row(rows, V1, "failed", kind="source_5xx", created=NOW - timedelta(days=1))
    await _row(rows, V2, "building", created=NOW)
    assert await _state(rows) == OverviewState("building")


async def test_a_failed_build_names_its_kind(rows: psycopg.AsyncConnection) -> None:
    await _row(rows, V1, "failed", kind="source_timeout")
    assert await _state(rows) == OverviewState("failed", failure_kind="source_timeout")


async def test_another_dataset_has_its_own_state(rows: psycopg.AsyncConnection) -> None:
    await _row(rows, V1, "ready", checked=NOW)
    assert await _state(rows, "esa-worldcover-2021") == OverviewState("none")


async def test_a_term_without_a_time_zone_is_refused(rows: psycopg.AsyncConnection) -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        await overview_state_async(rows, DATASET, fresh_after=datetime(2026, 1, 1))
