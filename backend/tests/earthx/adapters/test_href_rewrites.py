"""DS-04 plan §4.2: the adapter rewrites ``s3://`` addresses onto the asset host, once, before anyone sees them."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from earthx.adapters import SearchParams, stac_api
from earthx.gateway import Policy
from tests.catalog.entries import SENTINEL_1_GRD, SENTINEL_2_L2A

from .conftest import answering, load

pytestmark = pytest.mark.anyio

HOST = "https://sentinel-s1-l1c.s3.eu-central-1.amazonaws.com/"
POLICY = Policy(allowed_hosts=frozenset({"earth-search.aws.element84.com", *SENTINEL_1_GRD.source.asset_hosts}))


class MemoryCache:
    def __init__(self) -> None:
        self.rows: dict[str, Any] = {}

    async def get(self, key: str) -> Any:
        return self.rows.get(key)

    async def set(self, key: str, value: Any, *, ttl_s: float, dataset_id: str) -> None:
        self.rows[key] = value


def hrefs(item: dict[str, Any]) -> list[str]:
    return [asset["href"] for asset in item["assets"].values()]


async def test_every_asset_of_a_search_is_read_over_https_on_the_asset_host() -> None:
    gateway, _ = answering(httpx.Response(200, json=load("sentinel_1_search")), policy=POLICY)
    async with gateway:
        page = await stac_api.search_items(SENTINEL_1_GRD, SearchParams(), gateway=gateway)
    assert len(page.items) == 2
    for item in page.items:
        assert all(href.startswith(HOST) for href in hrefs(item))
    assert page.items[0]["assets"]["vv"]["href"] == HOST + "GRD/2026/6/1/IW/DV/S1X_SYNTHETIC_S1_VVVH/measurement/iw-vv.tiff"


async def test_only_the_href_changes() -> None:
    """Auslegung A4: the wrong `storage:requester_pays` stays as the source wrote it, and so does every other field."""
    source = load("sentinel_1_search")
    gateway, _ = answering(httpx.Response(200, json=source), policy=POLICY)
    async with gateway:
        page = await stac_api.search_items(SENTINEL_1_GRD, SearchParams(), gateway=gateway)
    for ours, theirs in zip(page.items, source["features"], strict=True):
        assert ours["properties"] == theirs["properties"]
        assert ours["properties"]["storage:requester_pays"] is True
        for key, asset in ours["assets"].items():
            assert {k: v for k, v in asset.items() if k != "href"} == {
                k: v for k, v in theirs["assets"][key].items() if k != "href"
            }


async def test_the_cache_holds_the_rewritten_items_and_a_hit_returns_them() -> None:
    """The rewrite is part of `normalize_for`, with the fixed asset keys of M5-08b: what is cached is already ours."""
    cache = MemoryCache()
    gateway, seen = answering(httpx.Response(200, json=load("sentinel_1_search")), policy=POLICY)
    async with gateway:
        first = await stac_api.search_items(SENTINEL_1_GRD, SearchParams(), gateway=gateway, cache=cache)
        second = await stac_api.search_items(SENTINEL_1_GRD, SearchParams(), gateway=gateway, cache=cache)
    assert len(seen) == 1
    assert second.from_cache
    assert second.items == first.items
    (stored,) = cache.rows.values()
    assert all(href.startswith(HOST) for item in stored["features"] for href in hrefs(item))


async def test_an_item_fetch_is_rewritten_live_and_from_the_cache() -> None:
    cache = MemoryCache()
    item = load("sentinel_1_search")["features"][1]
    gateway, seen = answering(httpx.Response(200, json=item), policy=POLICY)
    async with gateway:
        live = await stac_api.get_item(SENTINEL_1_GRD, "S1_HHHV", gateway=gateway, cache=cache)
        cached = await stac_api.get_item(SENTINEL_1_GRD, "S1_HHHV", gateway=gateway, cache=cache)
    assert len(seen) == 1
    assert live == cached
    assert live["assets"]["hh"]["href"].startswith(HOST)


async def test_an_address_outside_the_prefix_stays_and_is_left_to_the_readers() -> None:
    """A bucket the registry does not name keeps its `s3://` address, which `readers` refuses (§4.7)."""
    answer = load("sentinel_1_search")
    answer["features"][0]["assets"]["vv"]["href"] = "s3://another-bucket/x/iw-vv.tiff"
    answer["features"][0]["assets"]["vh"]["href"] = "s3://sentinel-s1-l1c/x/../../iw-vh.tiff"
    gateway, _ = answering(httpx.Response(200, json=answer), policy=POLICY)
    async with gateway:
        page = await stac_api.search_items(SENTINEL_1_GRD, SearchParams(), gateway=gateway)
    assert page.items[0]["assets"]["vv"]["href"] == "s3://another-bucket/x/iw-vv.tiff"
    assert page.items[0]["assets"]["vh"]["href"] == "s3://sentinel-s1-l1c/x/../../iw-vh.tiff"


async def test_an_asset_without_an_href_passes_through() -> None:
    answer = load("sentinel_1_search")
    answer["features"][0]["assets"]["odd"] = {"title": "no address"}
    answer["features"][0]["assets"]["list"] = ["not", "an", "asset"]
    gateway, _ = answering(httpx.Response(200, json=answer), policy=POLICY)
    async with gateway:
        page = await stac_api.search_items(SENTINEL_1_GRD, SearchParams(), gateway=gateway)
    assert page.items[0]["assets"]["odd"] == {"title": "no address"}
    assert page.items[0]["assets"]["list"] == ["not", "an", "asset"]


async def test_an_entry_without_rewrites_returns_the_items_untouched() -> None:
    answer = load("sentinel_1_search")
    gateway, _ = answering(httpx.Response(200, json=answer))
    async with gateway:
        page = await stac_api.search_items(SENTINEL_2_L2A, SearchParams(), gateway=gateway)
    assert list(page.items) == answer["features"]


# Otto's browser check, 10.11.2026: the mosaic refused a Sentinel-1 pass with "the item points at a host this dataset
# does not declare (asset_hosts)". The first form of DS-04b stored the source's items in the cache and rewrote them on
# the way out; once the rewrite moved before the cache (M5-08b), such an entry came out as stored, with `s3://`. What
# leaves the cache is rewritten again, so an entry from before the rewrite reaches no reader with the source's address.


def _stored_as_before(cache: MemoryCache, key: str, value: dict[str, Any]) -> None:
    cache.rows[key] = value


async def test_an_item_the_cache_kept_with_the_source_address_comes_out_rewritten() -> None:
    cache = MemoryCache()
    raw = load("sentinel_1_search")["features"][1]
    assert raw["assets"]["hh"]["href"].startswith("s3://")
    _stored_as_before(cache, stac_api.item_cache_key(SENTINEL_1_GRD.dataset_id, "S1_HHHV"), {"item": raw})
    gateway, seen = answering(httpx.Response(500), policy=POLICY)
    async with gateway:
        item = await stac_api.get_item(SENTINEL_1_GRD, "S1_HHHV", gateway=gateway, cache=cache)
    assert seen == []
    assert all(href.startswith(HOST) for href in hrefs(item))


async def test_a_search_page_the_cache_kept_with_the_source_address_comes_out_rewritten() -> None:
    cache = MemoryCache()
    gateway, seen = answering(httpx.Response(200, json=load("sentinel_1_search")), policy=POLICY)
    async with gateway:
        await stac_api.search_items(SENTINEL_1_GRD, SearchParams(), gateway=gateway, cache=cache)
        (key,) = cache.rows
        cache.rows[key] = {**cache.rows[key], "features": load("sentinel_1_search")["features"]}
        page = await stac_api.search_items(SENTINEL_1_GRD, SearchParams(), gateway=gateway, cache=cache)
    assert len(seen) == 1
    assert page.from_cache
    assert all(href.startswith(HOST) for item in page.items for href in hrefs(item))


async def test_a_rewritten_entry_is_not_rewritten_twice() -> None:
    cache = MemoryCache()
    item = load("sentinel_1_search")["features"][1]
    gateway, _ = answering(httpx.Response(200, json=item), policy=POLICY)
    async with gateway:
        live = await stac_api.get_item(SENTINEL_1_GRD, "S1_HHHV", gateway=gateway, cache=cache)
        again = await stac_api.get_item(SENTINEL_1_GRD, "S1_HHHV", gateway=gateway, cache=cache)
    assert again == live
    assert again["assets"]["hh"]["href"].count(HOST) == 1


async def test_an_entry_without_rewrites_takes_its_cached_items_as_they_are() -> None:
    cache = MemoryCache()
    raw = load("sentinel_1_search")["features"][1]
    cache.rows[stac_api.item_cache_key(SENTINEL_2_L2A.dataset_id, "S1_HHHV")] = {"item": raw}
    gateway, _ = answering(httpx.Response(500))
    async with gateway:
        item = await stac_api.get_item(SENTINEL_2_L2A, "S1_HHHV", gateway=gateway, cache=cache)
    assert item == raw
