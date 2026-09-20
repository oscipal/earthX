"""T-C: the statistics cache against a real Postgres (adr/0006 §5 "Zu Frage 3").

What a unit test cannot show is what the table does: that a row survives a write,
that an expired row reads as missing, and that a failing statement leaves the
connection usable — the last one is what makes "a broken cache is merely slower"
true for the process and not only for the endpoint.

Expiry is measured with ``now()``, the transaction's own clock, so a lifetime of
zero seconds reads back as expired without anyone waiting for it.
"""

from __future__ import annotations

import psycopg
import pytest

from earthx.catalog.schema import discover_migrations
from earthx.catalog.stats_cache import TABLE, TTL_S, PostgresStatsCache

from .conftest import SHIPPED_TABLES

pytestmark = pytest.mark.anyio

VALUE = {"b1": {"percentile_2": 12.0, "percentile_98": 240.0}}


@pytest.fixture
async def cache(aconn: psycopg.AsyncConnection) -> PostgresStatsCache:
    """A cache on a migrated database, inside the transaction that gets rolled back."""
    for table in SHIPPED_TABLES:
        await aconn.execute(f"DROP TABLE IF EXISTS {table}")
    for migration in discover_migrations():
        await aconn.execute(migration.sql)
    return PostgresStatsCache(aconn)


async def test_what_goes_in_comes_back_out(cache: PostgresStatsCache) -> None:
    await cache.set("key", VALUE, dataset_id="sentinel-2-c1-l2a")
    assert await cache.get("key") == VALUE


async def test_a_key_that_was_never_written_is_simply_missing(cache: PostgresStatsCache) -> None:
    assert await cache.get("never-written") is None


async def test_an_expired_entry_reads_as_missing(cache: PostgresStatsCache) -> None:
    await cache.set("key", VALUE, dataset_id="sentinel-2-c1-l2a", ttl_s=0)
    assert await cache.get("key") is None


async def test_writing_the_same_key_again_replaces_it(cache: PostgresStatsCache) -> None:
    await cache.set("key", VALUE, dataset_id="sentinel-2-c1-l2a")
    await cache.set("key", {"b1": {"percentile_2": 0.0}}, dataset_id="sentinel-2-c1-l2a")
    assert await cache.get("key") == {"b1": {"percentile_2": 0.0}}


async def test_the_row_carries_the_dataset_and_a_month_of_life(
    cache: PostgresStatsCache, aconn: psycopg.AsyncConnection
) -> None:
    """30 days, and the dataset beside the key so rows can be dropped per dataset."""
    await cache.set("key", VALUE, dataset_id="sentinel-2-c1-l2a")

    async with aconn.cursor() as cur:
        await cur.execute(
            f"SELECT dataset_id, expires_at - created_at FROM {TABLE} WHERE cache_key = %s", ("key",)
        )
        dataset_id, lifetime = await cur.fetchone()

    assert dataset_id == "sentinel-2-c1-l2a"
    assert abs(lifetime.total_seconds() - TTL_S) < 5


async def test_a_failing_statement_leaves_the_connection_usable(
    cache: PostgresStatsCache, aconn: psycopg.AsyncConnection
) -> None:
    """The savepoint keeps the failure inside the cache: the request it serves goes on."""
    await aconn.execute(f"ALTER TABLE {TABLE} DROP COLUMN payload")

    with pytest.raises(psycopg.Error):
        await cache.set("key", VALUE, dataset_id="sentinel-2-c1-l2a")

    async with aconn.cursor() as cur:
        await cur.execute("SELECT 1")
        assert await cur.fetchone() == (1,)
