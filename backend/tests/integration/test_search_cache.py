"""T-C: the application cache of E4 against a real Postgres.

What the double in ``tests/earthx/adapters/test_cache_use.py`` cannot show: that the
migration runs, that jsonb comes back as the object that went in, that the expiry is
the database's and not ours — and that a cache which breaks mid-flight still leaves a
usable platform (E5, adr/0001 §9.3).
"""

from __future__ import annotations

import httpx
import psycopg
import pytest

from earthx.adapters import SearchParams, get_item, search_items
from earthx.adapters.cache import SearchCache
from earthx.catalog.datasets import SENTINEL_2_L2A
from earthx.catalog.schema import discover_migrations
from earthx.catalog.search_cache import PostgresSearchCache
from earthx.gateway import Policy
from earthx.gateway.client import Gateway

from ..earthx.adapters.conftest import load

pytestmark = pytest.mark.anyio

DATASET = SENTINEL_2_L2A.dataset_id
HOST = "earth-search.aws.element84.com"


@pytest.fixture
async def cache(aconn: psycopg.AsyncConnection) -> PostgresSearchCache:
    """A cache on a migrated database, all inside the transaction that gets rolled back.

    The migration is applied here rather than assumed: that is the only place this
    suite runs the SQL M1-06 ships. It starts from a database that has never seen it,
    because ``earthx.catalog.load`` commits — so a full run leaves the table behind.
    """
    await aconn.execute("DROP TABLE IF EXISTS public.earthx_search_cache")
    for migration in discover_migrations():
        await aconn.execute(migration.sql)
    return PostgresSearchCache(aconn)


def gateway_answering(*responses: httpx.Response) -> tuple[Gateway, list[httpx.Request]]:
    """A gateway that answers from memory; no test here reaches the network either."""
    seen: list[httpx.Request] = []
    queue = list(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return queue.pop(0) if len(queue) > 1 else queue[0]

    async def sleep(seconds: float) -> None:
        return None

    gateway = Gateway(
        Policy(allowed_hosts=frozenset({HOST})),
        transport=httpx.MockTransport(handler),
        resolve=lambda host, port: ("93.184.216.34",),
        sleep=sleep,
    )
    return gateway, seen


class TestTheTableItself:
    def test_the_implementation_fits_the_protocol_it_cannot_inherit(self) -> None:
        """`catalog` must not import `adapters`, so this is the only thing tying them."""
        assert isinstance(PostgresSearchCache(None), SearchCache)  # type: ignore[arg-type]

    async def test_what_goes_in_comes_back_out(self, cache: PostgresSearchCache) -> None:
        await cache.set("k", {"features": [{"id": "one"}], "matched": 1}, ttl_s=60, dataset_id=DATASET)
        assert await cache.get("k") == {"features": [{"id": "one"}], "matched": 1}

    async def test_a_key_that_was_never_written_is_simply_missing(self, cache: PostgresSearchCache) -> None:
        assert await cache.get("never-written") is None

    async def test_an_expired_entry_reads_as_missing(self, cache: PostgresSearchCache) -> None:
        """Written with no lifetime at all: inside one transaction `now()` stands still,
        so the row is already past its expiry when it is read back."""
        await cache.set("k", {"features": []}, ttl_s=0, dataset_id=DATASET)
        assert await cache.get("k") is None

    async def test_writing_the_same_key_again_replaces_it(self, cache: PostgresSearchCache) -> None:
        await cache.set("k", {"features": [{"id": "old"}]}, ttl_s=60, dataset_id=DATASET)
        await cache.set("k", {"features": [{"id": "new"}]}, ttl_s=60, dataset_id=DATASET)
        stored = await cache.get("k")
        assert stored is not None
        assert stored["features"] == [{"id": "new"}]

    async def test_the_row_carries_the_dataset_it_belongs_to(
        self, cache: PostgresSearchCache, aconn: psycopg.AsyncConnection
    ) -> None:
        """So rows can be attributed, and later dropped, without decoding the key."""
        await cache.set("k", {"features": []}, ttl_s=60, dataset_id=DATASET)
        async with aconn.cursor() as cur:
            await cur.execute("SELECT dataset_id FROM public.earthx_search_cache WHERE cache_key = 'k'")
            row = await cur.fetchone()
        assert row is not None and row[0] == DATASET


class TestTheAdapterOnTheRealCache:
    async def test_the_second_search_is_answered_from_postgres(self, cache: PostgresSearchCache) -> None:
        gateway, seen = gateway_answering(httpx.Response(200, json=load("search_page_1")))
        async with gateway:
            first = await search_items(DATASET, SearchParams(limit=2), gateway=gateway, cache=cache)
            second = await search_items(DATASET, SearchParams(limit=2), gateway=gateway, cache=cache)
        assert len(seen) == 1
        assert second.from_cache is True
        assert [item["id"] for item in second.items] == [item["id"] for item in first.items]

    async def test_a_restart_between_search_and_item_does_not_change_anything(
        self, cache: PostgresSearchCache, aconn: psycopg.AsyncConnection
    ) -> None:
        """adr/0001 §8. The page marker is text and the cache is addressed by key, so
        nothing of the first process is needed by the second — here the client, the
        cache object and the gateway are all built anew between the two calls."""
        gateway, _ = gateway_answering(httpx.Response(200, json=load("search_page_1")))
        async with gateway:
            page = await search_items(DATASET, SearchParams(limit=2), gateway=gateway, cache=cache)
        assert page.next_page_token is not None

        after_restart, seen = gateway_answering(httpx.Response(200, json=load("item")))
        async with after_restart:
            item = await get_item(
                DATASET,
                page.items[0]["id"],
                gateway=after_restart,
                cache=PostgresSearchCache(aconn),
            )
        assert item["id"] == page.items[0]["id"]
        assert len(seen) == 1

    async def test_a_cache_that_breaks_only_costs_a_request(
        self, cache: PostgresSearchCache, aconn: psycopg.AsyncConnection
    ) -> None:
        """E5 against a real failure: the table is gone mid-flight, and the search
        still answers from the source instead of turning into an error."""
        gateway, seen = gateway_answering(httpx.Response(200, json=load("search_page_1")))
        async with gateway:
            await search_items(DATASET, SearchParams(limit=2), gateway=gateway, cache=cache)
            await aconn.execute("DROP TABLE public.earthx_search_cache")
            page = await search_items(DATASET, SearchParams(limit=2), gateway=gateway, cache=cache)
        assert len(seen) == 2
        assert len(page.items) == 2
        assert page.from_cache is False

    async def test_a_broken_cache_leaves_the_connection_usable(
        self, cache: PostgresSearchCache, aconn: psycopg.AsyncConnection
    ) -> None:
        """The half of E5 that the test above cannot see.

        A failed statement aborts the whole transaction it runs in, and from M1-07 that
        is the transaction serving the request: the search would answer and everything
        after it would die with InFailedSqlTransaction. Each cache statement therefore
        runs in its own savepoint. Checked on the read *and* on the write, because a
        poisoned connection would also stop the cache from ever storing anything again.
        """
        gateway, _ = gateway_answering(httpx.Response(200, json=load("search_page_1")))
        await aconn.execute("DROP TABLE public.earthx_search_cache")

        async with gateway:
            await search_items(DATASET, SearchParams(limit=2), gateway=gateway, cache=cache)

        async with aconn.cursor() as cur:
            await cur.execute("SELECT 1")
            assert await cur.fetchone() == (1,)
