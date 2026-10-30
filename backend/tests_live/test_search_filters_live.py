"""T-D, DS-02: do the search filters of the registry still match their source? (Otto 28.10.2026, D)

The registry is the truth about which filters a dataset offers, because the source's own queryables are
incomplete (plan §6.2, §6.6). What only the source can answer is checked here, through the adapter and the
gateway, for every entry with filters:

* every item of a sample carries every filtered property — a filter on a property the items lack matches
  nothing without a word (plan §6.2a);
* the source counts exactly the scenes the sample says a filter keeps (DS-02c): a filter that matches more, fewer or
  nothing is one the source no longer applies as the registry says (adr/0021 §8);
* a values filter knows every value the sample holds, and every value of the last 30 days: a new satellite or
  processing baseline needs a line in the registry;
* the coverage map follows the filter: the aggregation counts exactly the scenes the search matches (DS-02b);
* where the queryables name a property with a type, the type fits the kind of filter.

Small on purpose (adr/0005 §3.6, K5): one sample in a closed window in the past, two or three searches and one
aggregation per filter, one search of the last 30 days per values filter and one request for the queryables.
"""

from __future__ import annotations

import statistics
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import pytest

from earthx.adapters import ADAPTER_SPECS, SearchParams, coverage, search_items
from earthx.catalog.coverage import CoverageQuery
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


def _probes(search_filter: SearchFilter, found: list[Any]) -> list[Condition]:
    """Conditions whose result the sample itself tells: both halves of a range split at its median, and for a choice
    the value the sample holds most often and, where there is one, a value it does not hold at all."""
    if search_filter.kind is FilterKind.RANGE:
        median = statistics.median(found)
        return [RangeCondition(minimum=None, maximum=median), RangeCondition(minimum=median, maximum=None)]
    held = max(set(found), key=found.count)
    absent = [entry.value for entry in search_filter.values if entry.value not in found]
    return [ValuesCondition(values=(held,)), *([ValuesCondition(values=(absent[0],))] if absent else [])]


def _keeps(condition: Condition, value: Any) -> bool:
    if isinstance(condition, ValuesCondition):
        return value in condition.values
    return (condition.minimum is None or value >= condition.minimum) and (condition.maximum is None or value <= condition.maximum)


async def _matched(config: DatasetConfig, gateway: Gateway, conditions: dict[str, Condition] | None) -> int:
    params = SearchParams(bbox=BBOX, start=WINDOW[0], end=WINDOW[1], limit=1, conditions=conditions)
    page = await search_items(config, params, adapters=ADAPTER_SPECS, gateway=gateway)
    assert isinstance(page.matched, int), f"{config.dataset_id}: the source no longer counts its matches"
    return page.matched


async def _counted(config: DatasetConfig, gateway: Gateway, conditions: dict[str, Condition]) -> int | None:
    query = CoverageQuery(
        dataset_id=config.dataset_id, level=4, bbox=BBOX, start=WINDOW[0], end=WINDOW[1], conditions=conditions
    )
    return (await coverage(query, config, adapters=ADAPTER_SPECS, gateway=gateway)).total_count


async def _recent_values_are_known(config: DatasetConfig, gateway: Gateway, search_filter: SearchFilter) -> None:
    """The last 30 days hold no value of a choice that the registry does not offer: a new satellite or processing
    baseline shows here first (the closed window above cannot)."""
    until = datetime.now(timezone.utc)
    params = SearchParams(bbox=BBOX, start=until - timedelta(days=30), end=until, limit=SAMPLE)
    recent = await search_items(config, params, adapters=ADAPTER_SPECS, gateway=gateway)
    offered = {entry.value for entry in search_filter.values}
    held = {item.get("properties", {}).get(search_filter.property) for item in recent.items}
    assert held <= offered, f"{config.dataset_id}: the source holds a new value of {search_filter.property}: add it to the registry"


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
        assert total == len(sample.items), f"{config.dataset_id}: the sample window holds more than {SAMPLE} scenes"
        for search_filter in config.search_filters:
            name = search_filter.property
            found = [item.get("properties", {}).get(name) for item in sample.items]
            assert all(value is not None for value in found), f"{config.dataset_id}: an item lacks {name}"
            if search_filter.kind is FilterKind.VALUES:
                offered = {entry.value for entry in search_filter.values}
                assert set(found) <= offered, f"{config.dataset_id}: the source holds a value of {name} not offered"
                await _recent_values_are_known(config, gateway, search_filter)
            narrowed_somewhere = False
            for number, condition in enumerate(_probes(search_filter, found)):
                expected = sum(_keeps(condition, value) for value in found)
                matched = await _matched(config, gateway, {name: condition})
                assert matched == expected, f"{config.dataset_id}: {name} keeps {matched} scenes, the sample says {expected}"
                narrowed_somewhere |= matched < total
                if number == 0:
                    assert await _counted(config, gateway, {name: condition}) == matched, (
                        f"{config.dataset_id}: the coverage count does not follow {name}"
                    )
            if len(set(found)) > 1:
                assert narrowed_somewhere, f"{config.dataset_id}: {name} does not narrow the sample"

        url = f"{config.source.endpoint.rstrip('/')}/collections/{config.source.source_collection_id}/queryables"
        queryables = (await gateway.get(url)).json().get("properties", {})
        for search_filter in config.search_filters:
            kind = queryables.get(search_filter.property, {}).get("type")
            if kind is not None:
                assert kind in TYPES[search_filter.kind], (
                    f"{config.dataset_id}: the queryables give {search_filter.property} another type"
                )
