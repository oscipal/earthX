"""T-C: the place-search cache and the shared rate slot of M3-07a against a real
Postgres.

What a mocked connection cannot show: that the migration runs, that jsonb comes back
as the object that went in, that the rate slot's ``clock_timestamp()`` arithmetic
actually spaces reservations a second apart across separate connections, and that a
push-back after a ``429`` really does move the shared pointer forward.
"""

from __future__ import annotations

import psycopg
import pytest

from earthx.catalog.geocode_cache import PostgresGeocodeCache, PostgresRateSlot
from earthx.catalog.schema import discover_migrations

from .conftest import SHIPPED_TABLES

pytestmark = pytest.mark.anyio


@pytest.fixture
async def geocode_cache(aconn: psycopg.AsyncConnection) -> PostgresGeocodeCache:
    """A cache on a migrated database, all inside the transaction that gets rolled
    back — same construction as `tests/integration/test_search_cache.py`."""
    for table in SHIPPED_TABLES:
        await aconn.execute(f"DROP TABLE IF EXISTS {table}")
    for migration in discover_migrations():
        await aconn.execute(migration.sql)
    return PostgresGeocodeCache(aconn)


@pytest.fixture
async def rate_slot(geocode_cache: PostgresGeocodeCache, aconn: psycopg.AsyncConnection) -> PostgresRateSlot:
    """Depends on `geocode_cache` only to force the same migration to run first —
    both tables come from the same file."""
    return PostgresRateSlot(aconn)


class TestTheCache:
    async def test_what_goes_in_comes_back_out(self, geocode_cache: PostgresGeocodeCache) -> None:
        await geocode_cache.set("k", {"v": 1, "results": []}, ttl_s=60)
        assert await geocode_cache.get("k") == {"v": 1, "results": []}

    async def test_a_key_that_was_never_written_is_simply_missing(self, geocode_cache: PostgresGeocodeCache) -> None:
        assert await geocode_cache.get("never-written") is None

    async def test_an_expired_entry_reads_as_missing(self, geocode_cache: PostgresGeocodeCache) -> None:
        """Inside one transaction `now()` stands still, so a row written with no
        lifetime at all is already past its expiry when it is read back."""
        await geocode_cache.set("k", {"v": 1, "results": []}, ttl_s=0)
        assert await geocode_cache.get("k") is None

    async def test_writing_the_same_key_again_replaces_it(self, geocode_cache: PostgresGeocodeCache) -> None:
        await geocode_cache.set("k", {"v": 1, "results": [{"name": "old"}]}, ttl_s=60)
        await geocode_cache.set("k", {"v": 1, "results": [{"name": "new"}]}, ttl_s=60)
        stored = await geocode_cache.get("k")
        assert stored is not None
        assert stored["results"] == [{"name": "new"}]

    async def test_no_dataset_id_column_exists(self, aconn: psycopg.AsyncConnection) -> None:
        """A place search is not tied to a dataset, unlike the search cache."""
        async with aconn.cursor() as cur:
            await cur.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = 'earthx_geocode_cache'"
            )
            columns = {row[0] for row in await cur.fetchall()}
        assert "dataset_id" not in columns


class TestTheRateSlot:
    async def test_the_first_reservation_of_a_new_name_is_free(self, rate_slot: PostgresRateSlot) -> None:
        assert await rate_slot.reserve("nominatim") < 0.1

    async def test_a_second_reservation_right_after_the_first_waits_about_a_second(
        self, rate_slot: PostgresRateSlot
    ) -> None:
        first = await rate_slot.reserve("nominatim")
        second = await rate_slot.reserve("nominatim")
        assert first < 0.1
        assert 0.9 < second < 1.1

    async def test_reservations_stack_by_a_second_each(self, rate_slot: PostgresRateSlot) -> None:
        delays = [await rate_slot.reserve("nominatim") for _ in range(3)]
        assert delays[0] < 0.1
        assert 0.9 < delays[1] < 1.1
        assert 1.9 < delays[2] < 2.1

    async def test_a_different_name_has_its_own_pointer(self, rate_slot: PostgresRateSlot) -> None:
        await rate_slot.reserve("nominatim")
        await rate_slot.reserve("nominatim")
        assert await rate_slot.reserve("some-other-geocoder") < 0.1

    async def test_push_back_moves_the_pointer_forward_by_at_least_that_much(
        self, rate_slot: PostgresRateSlot
    ) -> None:
        await rate_slot.reserve("nominatim")
        await rate_slot.push_back("nominatim", seconds=30.0)
        assert await rate_slot.reserve("nominatim") > 28.0

    async def test_push_back_on_a_name_never_reserved_still_reserves_the_wait(
        self, rate_slot: PostgresRateSlot
    ) -> None:
        await rate_slot.push_back("nominatim", seconds=30.0)
        assert await rate_slot.reserve("nominatim") > 28.0

    async def test_two_independent_objects_share_one_pointer(
        self, rate_slot: PostgresRateSlot, aconn: psycopg.AsyncConnection
    ) -> None:
        """The point of the whole design (plan §9): the pointer lives in the table,
        not in a `PostgresRateSlot` instance — a second object wrapping a request of
        its own sees exactly what the first left behind, the same way two different
        `api` processes would through their own pooled connections."""
        other = PostgresRateSlot(aconn)
        await rate_slot.reserve("nominatim")
        delay = await other.reserve("nominatim")
        assert 0.9 < delay < 1.1
