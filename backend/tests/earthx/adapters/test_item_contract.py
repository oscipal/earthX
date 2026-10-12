"""The item contract of every adapter (adr/0011 §5.3; M4-22).

Every item that ``search``, ``fetch`` or ``materialize`` of an entry of the adapter
table delivers is STAC 1.0 and carries only ``https`` hrefs on its assets. That is
the form and the scheme — not the host: the fixtures point at ``example.invalid`` on
purpose, and one holds an asset on a foreign host, which the resolution refuses when
it opens the asset, not the adapter.

The answers are the synthetic fixtures of the adapter tests, driven through the
dispatcher with the real table, so the check sees what ``api`` and ``discovery`` see.
A guard fails when the table gains an adapter, or an adapter a capability, that has
no fixture here: the contract is a rule for every future source, not an intention.
"""

from __future__ import annotations

import copy
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import replace
from typing import Any
from urllib.parse import urlsplit

import httpx
import pytest
from pydantic import ValidationError
from stac_pydantic import Item as StacItem

from earthx.adapters import ADAPTER_SPECS, get_item, materialize_items, search_items
from earthx.adapters.spec import AdapterSpec, AdapterSpecs
from earthx.catalog.datasets import COP_DEM_GLO_30, SENTINEL_2_L2A, SENTINEL_2_L2A_ZARR3
from earthx.catalog.registry import AdapterKind, DatasetConfig
from earthx.gateway import Policy, host_of
from tests.earthx.adapters.conftest import FIXTURES as EARTH_SEARCH_FIXTURES
from tests.earthx.adapters.conftest import answering, load
from tests.earthx.adapters.test_cop_dem_bucket import HOST as DEM_HOST
from tests.earthx.adapters.test_cop_dem_bucket import TILE_NE, TILE_SW, bucket

pytestmark = pytest.mark.anyio

EOPF_FIXTURES = EARTH_SEARCH_FIXTURES.parent / "eopf_stac"

# What the adapter table can offer an item through (``AdapterSpec`` fields).
ITEM_CAPABILITIES = ("search", "fetch", "materialize")

Capability = tuple[AdapterKind, str]
Producer = Callable[[], Awaitable[list[dict[str, Any]]]]


def violations_of(item: object) -> list[str]:
    """Why ``item`` breaks the item contract (adr/0011 §5.3, points 1 and 2); empty if it keeps it."""
    if not isinstance(item, Mapping):
        return ["the item is not a JSON object"]
    problems: list[str] = []
    if item.get("stac_version") != "1.0.0":
        problems.append(f"stac_version is {item.get('stac_version')!r}, not '1.0.0'")
    try:
        StacItem.model_validate(item)
    except ValidationError as error:
        problems.append(f"not a STAC item: {len(error.errors())} problem(s), first at {error.errors()[0]['loc']}")
    assets = item.get("assets")
    if not isinstance(assets, Mapping):
        return [*problems, "assets is not an object"]
    for key, asset in assets.items():
        if not isinstance(asset, Mapping):
            problems.append(f"asset {key!r} is not an object")
            continue
        if "bands" in asset:
            problems.append(f"asset {key!r} carries 'bands', which is STAC 1.1 (1.0 says eo:bands)")
        href = asset.get("href")
        parts = urlsplit(href) if isinstance(href, str) else None
        if parts is None or parts.scheme != "https" or not parts.netloc:
            problems.append(f"asset {key!r} has no https href")
    return problems


def _source_gateway(config: DatasetConfig, response: httpx.Response):
    policy = Policy(allowed_hosts=frozenset({host_of(config.source.endpoint)}))
    return answering(response, policy=policy)[0]


async def _searched(config: DatasetConfig, fixtures: Any, *names: str) -> list[dict[str, Any]]:
    delivered: list[dict[str, Any]] = []
    for name in names:
        gateway = _source_gateway(config, httpx.Response(200, json=load(name, fixtures=fixtures)))
        async with gateway:
            page = await search_items(config, None, adapters=ADAPTER_SPECS, gateway=gateway)
        delivered.extend(page.items)
    return delivered


async def _fetched(config: DatasetConfig, fixtures: Any, *names: str) -> list[dict[str, Any]]:
    delivered: list[dict[str, Any]] = []
    for name in names:
        payload = load(name, fixtures=fixtures)
        gateway = _source_gateway(config, httpx.Response(200, json=payload))
        async with gateway:
            delivered.append(await get_item(config, payload["id"], adapters=ADAPTER_SPECS, gateway=gateway))
    return delivered


async def _materialized() -> list[dict[str, Any]]:
    config = replace(
        COP_DEM_GLO_30, source=replace(COP_DEM_GLO_30.source, endpoint=f"https://{DEM_HOST}", asset_hosts=(DEM_HOST,))
    )
    gateway, _ = bucket(tile_list_names=[TILE_NE, TILE_SW])
    async with gateway:
        outcome = await materialize_items(config, adapters=ADAPTER_SPECS, gateway=gateway, known_version=None)
    return list(outcome.items)


# One producer per entry of the table and capability that delivers items. A new adapter,
# or a new capability of an old one, adds a line here, with its own synthetic fixtures.
PRODUCERS: Mapping[Capability, Producer] = {
    (AdapterKind.EARTH_SEARCH_V1, "search"): lambda: _searched(
        SENTINEL_2_L2A, EARTH_SEARCH_FIXTURES, "search_page_1", "search_no_count", "search_real_shape"
    ),
    (AdapterKind.EARTH_SEARCH_V1, "fetch"): lambda: _fetched(
        SENTINEL_2_L2A, EARTH_SEARCH_FIXTURES, "item", "item_asset_hosts"
    ),
    (AdapterKind.EOPF_STAC_V1, "search"): lambda: _searched(SENTINEL_2_L2A_ZARR3, EOPF_FIXTURES, "search_page_1"),
    (AdapterKind.EOPF_STAC_V1, "fetch"): lambda: _fetched(SENTINEL_2_L2A_ZARR3, EOPF_FIXTURES, "item"),
    (AdapterKind.COP_DEM_BUCKET, "materialize"): _materialized,
}


def capabilities_without_fixtures(adapters: AdapterSpecs, producers: Mapping[Capability, Producer]) -> set[Capability]:
    """What ``adapters`` can deliver items through and ``producers`` has nothing for."""
    offered = {
        (kind, capability)
        for kind, spec in adapters.items()
        for capability in ITEM_CAPABILITIES
        if getattr(spec, capability) is not None
    }
    return offered - set(producers)


class TestEveryAdapterKeepsTheContract:
    @pytest.mark.parametrize("capability", sorted(PRODUCERS, key=str), ids=lambda key: f"{key[0].value}-{key[1]}")
    async def test_every_delivered_item(self, capability: Capability) -> None:
        items = await PRODUCERS[capability]()
        assert items, "a source that delivers nothing proves nothing about its items"
        for item in items:
            assert violations_of(item) == [], item.get("id") if isinstance(item, Mapping) else item

    def test_no_adapter_or_capability_is_left_without_a_fixture(self) -> None:
        assert capabilities_without_fixtures(ADAPTER_SPECS, PRODUCERS) == set()

    def test_there_is_no_producer_for_something_the_table_does_not_offer(self) -> None:
        offered = {
            (kind, capability)
            for kind, spec in ADAPTER_SPECS.items()
            for capability in ITEM_CAPABILITIES
            if getattr(spec, capability) is not None
        }
        assert set(PRODUCERS) == offered


class TestTheGuardFails:
    def test_for_an_adapter_whose_fixtures_are_missing(self) -> None:
        without_dem = {key: producer for key, producer in PRODUCERS.items() if key[0] is not AdapterKind.COP_DEM_BUCKET}
        assert capabilities_without_fixtures(ADAPTER_SPECS, without_dem) == {
            (AdapterKind.COP_DEM_BUCKET, "materialize")
        }

    def test_for_a_capability_an_adapter_gains(self) -> None:
        async def never(*args: object, **kwargs: object) -> None:
            raise AssertionError("not called")

        dem = ADAPTER_SPECS[AdapterKind.COP_DEM_BUCKET]
        filters = ADAPTER_SPECS[AdapterKind.EOPF_STAC_V1].filters
        searchable: AdapterSpec = replace(dem, search=never, fetch=never, filters=filters)
        grown = {**ADAPTER_SPECS, AdapterKind.COP_DEM_BUCKET: searchable}
        assert capabilities_without_fixtures(grown, PRODUCERS) == {
            (AdapterKind.COP_DEM_BUCKET, "search"),
            (AdapterKind.COP_DEM_BUCKET, "fetch"),
        }


def _with_href(href: object) -> Callable[[dict[str, Any]], None]:
    def mutate(item: dict[str, Any]) -> None:
        next(iter(item["assets"].values()))["href"] = href

    return mutate


def _drop(*path: str) -> Callable[[dict[str, Any]], None]:
    def mutate(item: dict[str, Any]) -> None:
        target = item
        for key in path[:-1]:
            target = target[key]
        del target[path[-1]]

    return mutate


def _set(key: str, value: object) -> Callable[[dict[str, Any]], None]:
    def mutate(item: dict[str, Any]) -> None:
        item[key] = value

    return mutate


class TestTheContractCatchesABrokenItem:
    """Each case breaks one rule of a known-good item; the check must name it."""

    @pytest.mark.parametrize(
        "mutation",
        [
            pytest.param(_with_href("s3://bucket/key.tif"), id="s3-href"),
            pytest.param(_with_href("http://example.invalid/a.tif"), id="plain-http-href"),
            pytest.param(_with_href("/relative/a.tif"), id="relative-href"),
            pytest.param(_with_href("https:///no-host.tif"), id="https-without-host"),
            pytest.param(_with_href(None), id="href-is-null"),
            pytest.param(_drop("assets", "red", "href"), id="href-missing"),
            pytest.param(_set("stac_version", "1.1.0"), id="stac-1.1"),
            pytest.param(_drop("stac_version"), id="no-stac-version"),
            pytest.param(_set("assets", ["not", "an", "object"]), id="assets-not-an-object"),
            pytest.param(_drop("id"), id="no-id"),
            pytest.param(_drop("properties"), id="no-properties"),
        ],
    )
    def test_names_the_rule_that_broke(self, mutation: Callable[[dict[str, Any]], None]) -> None:
        item = copy.deepcopy(load("item", fixtures=EARTH_SEARCH_FIXTURES))
        assert violations_of(item) == []
        mutation(item)
        assert violations_of(item) != []

    def test_a_stac_1_1_band_list_on_an_asset_is_caught(self) -> None:
        item = copy.deepcopy(load("item", fixtures=EARTH_SEARCH_FIXTURES))
        item["assets"]["red"]["bands"] = [{"name": "B04"}]
        assert any("'bands'" in problem for problem in violations_of(item))

    @pytest.mark.parametrize("not_an_item", [None, "item", ["item"], 3])
    def test_something_that_is_not_an_object_is_caught(self, not_an_item: object) -> None:
        assert violations_of(not_an_item) == ["the item is not a JSON object"]

    async def test_an_s3_href_the_source_delivers_reaches_the_check_through_the_dispatcher(self) -> None:
        """The whole path, not the check alone: a source whose answer carries an
        ``s3://`` href is not translated by the adapter today, so the contract
        test sees it and fails."""
        payload = copy.deepcopy(load("item", fixtures=EARTH_SEARCH_FIXTURES))
        payload["assets"]["red"]["href"] = "s3://bucket/key/B04.tif"
        gateway = _source_gateway(SENTINEL_2_L2A, httpx.Response(200, json=payload))
        async with gateway:
            item = await get_item(SENTINEL_2_L2A, payload["id"], adapters=ADAPTER_SPECS, gateway=gateway)
        assert any("'red'" in problem for problem in violations_of(item))
