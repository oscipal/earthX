"""How the adapter uses a cache — with a double, so the rules are visible.

The rules under test are adr/0005 rule II (two lifetimes, decided by the time window)
and E5 / adr/0001 §9.3: a cache that is empty or broken makes the platform slower,
never wrong. The same behaviour against a real Postgres is in
``backend/tests/integration/test_search_cache.py``.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import pytest

from earthx.adapters import SearchParams, get_item, search_items
from earthx.adapters.cache import SearchCache
from earthx.adapters.earth_search import TTL_CLOSED_S, TTL_ITEM_S, TTL_OPEN_EDGE_S

from .conftest import answering, load

pytestmark = pytest.mark.anyio

NOW = datetime.now(timezone.utc)


class FakeCache:
    """A cache in a dict, which records what it was asked to keep and for how long."""

    def __init__(self, *, fails: bool = False) -> None:
        self.entries: dict[str, dict[str, Any]] = {}
        self.ttls: dict[str, float] = {}
        self.datasets: dict[str, str] = {}
        self.reads: list[str] = []
        self._fails = fails

    async def get(self, key: str) -> dict[str, Any] | None:
        self.reads.append(key)
        if self._fails:
            raise RuntimeError("the cache is having a bad day")
        return self.entries.get(key)

    async def set(self, key: str, value: dict[str, Any], *, ttl_s: float, dataset_id: str) -> None:
        if self._fails:
            raise RuntimeError("the cache is having a bad day")
        self.entries[key] = value
        self.ttls[key] = ttl_s
        self.datasets[key] = dataset_id


def test_the_double_is_a_search_cache() -> None:
    """Otherwise these tests would prove something about a shape nothing else has."""
    assert isinstance(FakeCache(), SearchCache)


class TestTheCacheIsUsed:
    async def test_a_second_identical_search_does_not_reach_the_source(self, dataset_id: str) -> None:
        cache = FakeCache()
        gateway, seen = answering(httpx.Response(200, json=load("search_page_1")))
        async with gateway:
            first = await search_items(dataset_id, SearchParams(limit=2), gateway=gateway, cache=cache)
            second = await search_items(dataset_id, SearchParams(limit=2), gateway=gateway, cache=cache)
        assert len(seen) == 1
        assert first.from_cache is False
        assert second.from_cache is True
        assert [item["id"] for item in second.items] == [item["id"] for item in first.items]

    async def test_a_cached_page_keeps_its_page_token(self, dataset_id: str) -> None:
        """A page out of the cache has to be as usable as a fresh one, marker included."""
        cache = FakeCache()
        gateway, _ = answering(httpx.Response(200, json=load("search_page_1")))
        async with gateway:
            first = await search_items(dataset_id, SearchParams(limit=2), gateway=gateway, cache=cache)
            second = await search_items(dataset_id, SearchParams(limit=2), gateway=gateway, cache=cache)
        assert second.next_page_token == first.next_page_token

    async def test_a_different_search_is_a_different_entry(self, dataset_id: str) -> None:
        cache = FakeCache()
        gateway, seen = answering(httpx.Response(200, json=load("search_empty")))
        async with gateway:
            await search_items(dataset_id, SearchParams(bbox=(8.0, 47.0, 12.0, 51.0)), gateway=gateway, cache=cache)
            await search_items(dataset_id, SearchParams(bbox=(8.0, 47.0, 12.0, 52.0)), gateway=gateway, cache=cache)
        assert len(seen) == 2
        assert len(cache.entries) == 2

    async def test_the_same_search_written_differently_is_one_entry(self, dataset_id: str) -> None:
        """47 and 47.0 are the same box, and so are the same instant in two offsets."""
        cache = FakeCache()
        berlin = timezone(timedelta(hours=2))
        gateway, seen = answering(httpx.Response(200, json=load("search_empty")))
        async with gateway:
            await search_items(
                dataset_id,
                SearchParams(bbox=(8, 47, 12, 51), start=datetime(2024, 6, 1, 2, tzinfo=berlin)),
                gateway=gateway,
                cache=cache,
            )
            await search_items(
                dataset_id,
                SearchParams(bbox=(8.0, 47.0, 12.0, 51.0), start=datetime(2024, 6, 1, 0, tzinfo=timezone.utc)),
                gateway=gateway,
                cache=cache,
            )
        assert len(seen) == 1
        assert len(cache.entries) == 1

    async def test_an_item_is_cached_under_its_id(self, dataset_id: str) -> None:
        cache = FakeCache()
        gateway, seen = answering(httpx.Response(200, json=load("item")))
        async with gateway:
            first = await get_item(dataset_id, "SYNTH_T00AAA_20240601T100000_L2A", gateway=gateway, cache=cache)
            second = await get_item(dataset_id, "SYNTH_T00AAA_20240601T100000_L2A", gateway=gateway, cache=cache)
        assert len(seen) == 1
        assert second == first
        assert set(cache.datasets.values()) == {dataset_id}


class TestTheTwoLifetimes:
    """adr/0005 rule II with Otto's F1: seven days decide, not the age of the request."""

    async def test_a_window_well_behind_us_is_kept_for_a_day(self, dataset_id: str) -> None:
        cache = FakeCache()
        gateway, _ = answering(httpx.Response(200, json=load("search_empty")))
        async with gateway:
            await search_items(
                dataset_id,
                SearchParams(start=NOW - timedelta(days=60), end=NOW - timedelta(days=30)),
                gateway=gateway,
                cache=cache,
            )
        assert set(cache.ttls.values()) == {TTL_CLOSED_S}

    async def test_a_window_that_ends_within_the_last_week_is_kept_for_five_minutes(self, dataset_id: str) -> None:
        """Scenes are still delivered into the days right behind the edge."""
        cache = FakeCache()
        gateway, _ = answering(httpx.Response(200, json=load("search_empty")))
        async with gateway:
            await search_items(
                dataset_id,
                SearchParams(start=NOW - timedelta(days=30), end=NOW - timedelta(days=3)),
                gateway=gateway,
                cache=cache,
            )
        assert set(cache.ttls.values()) == {TTL_OPEN_EDGE_S}

    async def test_an_open_window_is_kept_for_five_minutes(self, dataset_id: str) -> None:
        cache = FakeCache()
        gateway, _ = answering(httpx.Response(200, json=load("search_empty")))
        async with gateway:
            await search_items(dataset_id, SearchParams(start=NOW - timedelta(days=30)), gateway=gateway, cache=cache)
        assert set(cache.ttls.values()) == {TTL_OPEN_EDGE_S}

    async def test_a_single_item_is_kept_for_a_day(self, dataset_id: str) -> None:
        cache = FakeCache()
        gateway, _ = answering(httpx.Response(200, json=load("item")))
        async with gateway:
            await get_item(dataset_id, "SYNTH_T00AAA_20240601T100000_L2A", gateway=gateway, cache=cache)
        assert set(cache.ttls.values()) == {TTL_ITEM_S}


class TestACacheThatIsNotThere:
    """E5: a failing cache makes the platform slower, never a 404."""

    async def test_without_a_cache_the_answer_is_the_same(self, dataset_id: str) -> None:
        gateway, seen = answering(httpx.Response(200, json=load("search_page_1")))
        async with gateway:
            with_none = await search_items(dataset_id, SearchParams(limit=2), gateway=gateway, cache=None)
        assert len(seen) == 1
        assert len(with_none.items) == 2

    async def test_a_cache_that_cannot_be_read_is_asked_past(self, dataset_id: str) -> None:
        cache = FakeCache(fails=True)
        gateway, seen = answering(httpx.Response(200, json=load("search_page_1")))
        async with gateway:
            page = await search_items(dataset_id, SearchParams(limit=2), gateway=gateway, cache=cache)
        assert cache.reads  # it was asked
        assert len(seen) == 1  # and the source answered instead
        assert len(page.items) == 2

    async def test_a_cache_that_cannot_be_written_does_not_lose_the_answer(self, dataset_id: str) -> None:
        """The answer is already in hand; failing now would throw it away over bookkeeping."""
        cache = FakeCache(fails=True)
        gateway, _ = answering(httpx.Response(200, json=load("item")))
        async with gateway:
            item = await get_item(dataset_id, "SYNTH_T00AAA_20240601T100000_L2A", gateway=gateway, cache=cache)
        assert item["id"] == "SYNTH_T00AAA_20240601T100000_L2A"

    async def test_an_emptied_cache_only_costs_another_request(self, dataset_id: str) -> None:
        cache = FakeCache()
        gateway, seen = answering(httpx.Response(200, json=load("search_page_1")))
        async with gateway:
            before = await search_items(dataset_id, SearchParams(limit=2), gateway=gateway, cache=cache)
            cache.entries.clear()
            after = await search_items(dataset_id, SearchParams(limit=2), gateway=gateway, cache=cache)
        assert len(seen) == 2
        assert [item["id"] for item in after.items] == [item["id"] for item in before.items]
        assert after.next_page_token == before.next_page_token
