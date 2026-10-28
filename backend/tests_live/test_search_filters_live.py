"""T-D, DS-02: do the search filters of the registry still match their source? (Otto 28.10.2026, D)

The registry is the truth about which filters a dataset offers, because the source's own queryables are
incomplete (plan §6.2, §6.6). What only the source can answer is checked here, through the adapter and the
gateway, for every entry with filters:

* every item of a sample carries every filtered property — a filter on a property the items lack matches
  nothing without a word (plan §6.2a);
* each filter narrows the sample, and still finds something;
* a values filter knows every value the sample holds;
* where the queryables name a property with a type, the type fits the kind of filter.

Small on purpose (adr/0005 §3.6, K5): one sample, one request per filter and one for the queryables, in a
closed window in the past.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import httpx
import pytest

from earthx.adapters import ADAPTER_SPECS, SearchParams, search_items
from earthx.catalog.datasets import REGISTRY
from earthx.catalog.registry import DatasetConfig, FilterKind, SearchFilter
from earthx.catalog.search_filters import Condition, RangeCondition, ValuesCondition
from earthx.gateway import Policy
from earthx.gateway.client import Gateway

pytestmark = [pytest.mark.anyio, pytest.mark.live_dataset("sentinel-2-c1-l2a")]

# The box and month of the plan's measurement (§6.2): 42 scenes, enough to narrow on every filter.
BBOX = (10.0, 47.0, 11.0, 48.0)
WINDOW = (datetime(2024, 6, 1, tzinfo=timezone.utc), datetime(2024, 6, 30, 23, 59, 59, tzinfo=timezone.utc))
SAMPLE = 100
# The queryables' JSON Schema types that fit each kind of filter.
TYPES = {FilterKind.RANGE: {"number", "integer"}, FilterKind.VALUES: {"string"}}

FILTERED = tuple(config for config in REGISTRY if config.search_filters)


@asynccontextmanager
async def open_gateway() -> AsyncIterator[Gateway]:
    hosts = frozenset(httpx.URL(config.source.endpoint).host for config in FILTERED)
    async with Gateway(Policy(allowed_hosts=hosts)) as gateway:
        yield gateway


@pytest.fixture
async def gateway() -> AsyncIterator[Gateway]:
    async with open_gateway() as gateway:
        yield gateway


def _narrowing(search_filter: SearchFilter) -> Condition:
    """A condition that should keep some of the sample but not all: the lower half, or the first value."""
    if search_filter.kind is FilterKind.RANGE:
        assert search_filter.minimum is not None and search_filter.maximum is not None
        return RangeCondition(minimum=None, maximum=(search_filter.minimum + search_filter.maximum) / 2)
    return ValuesCondition(values=(search_filter.values[0].value,))


async def _matched(config: DatasetConfig, gateway: Gateway, conditions: dict[str, Condition] | None) -> int:
    params = SearchParams(bbox=BBOX, start=WINDOW[0], end=WINDOW[1], limit=1, conditions=conditions)
    page = await search_items(config, params, adapters=ADAPTER_SPECS, gateway=gateway)
    assert isinstance(page.matched, int), f"{config.dataset_id}: the source no longer counts its matches"
    return page.matched


async def test_the_registry_filters_still_fit_their_source(gateway: Gateway) -> None:
    assert FILTERED, "no registry entry offers search filters"
    for config in FILTERED:
        sample = await search_items(
            config,
            SearchParams(bbox=BBOX, start=WINDOW[0], end=WINDOW[1], limit=SAMPLE),
            adapters=ADAPTER_SPECS,
            gateway=gateway,
        )
        assert sample.items, f"{config.dataset_id}: no items in the sample window"
        total = await _matched(config, gateway, None)
        for search_filter in config.search_filters:
            name = search_filter.property
            found = [item.get("properties", {}).get(name) for item in sample.items]
            assert all(value is not None for value in found), f"{config.dataset_id}: an item lacks {name}"
            if search_filter.kind is FilterKind.VALUES:
                offered = {entry.value for entry in search_filter.values}
                assert set(found) <= offered, f"{config.dataset_id}: the source holds a value of {name} not offered"
            narrowed = await _matched(config, gateway, {name: _narrowing(search_filter)})
            assert 0 < narrowed < total, f"{config.dataset_id}: {name} does not narrow the sample"

        url = f"{config.source.endpoint.rstrip('/')}/collections/{config.source.source_collection_id}/queryables"
        queryables = (await gateway.get(url)).json().get("properties", {})
        for search_filter in config.search_filters:
            kind = queryables.get(search_filter.property, {}).get("type")
            if kind is not None:
                assert kind in TYPES[search_filter.kind], (
                    f"{config.dataset_id}: the queryables give {search_filter.property} another type"
                )
