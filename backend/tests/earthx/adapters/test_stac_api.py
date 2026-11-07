"""M5-08: one module for STAC APIs, one dialect per source (adr/0011 F6, §8.2).

What Earth Search sends and answers is pinned in ``test_earth_search_golden.py`` and
``test_earth_search.py``; this covers the dialect itself and its tie to the spec table.
"""

from __future__ import annotations

from dataclasses import replace

import httpx
import pytest

from earthx.adapters import (
    ADAPTER_SPECS,
    AdapterSpecMismatch,
    SearchParams,
    UnsupportedFilter,
    UnsupportedSource,
    check_adapter_specs,
    stac_api,
)
from earthx.adapters.federated_search import FilterSupport
from earthx.adapters.spec import spec_table
from earthx.adapters.stac_api import (
    DIALECTS,
    EARTH_SEARCH,
    StacDialect,
    dialect_of,
    dialect_table,
    query_extension,
)
from earthx.catalog.registry import AdapterKind, DatasetRegistry
from earthx.catalog.search_filters import RangeCondition
from tests.catalog.entries import COP_DEM_GLO_30, SENTINEL_2_L2A

from .conftest import answering, load


class TestDialect:
    def test_conditions_without_a_query_at_the_source_are_refused(self) -> None:
        with pytest.raises(ValueError, match="conditions are written exactly when"):
            replace(EARTH_SEARCH, filters=replace(EARTH_SEARCH.filters, query=False))

    def test_a_query_at_the_source_without_a_writer_is_refused(self) -> None:
        with pytest.raises(ValueError, match="conditions are written exactly when"):
            replace(EARTH_SEARCH, write_conditions=None)

    def test_a_source_without_a_query_needs_no_writer(self) -> None:
        dialect = StacDialect(
            kind=AdapterKind.EARTH_SEARCH_V1,
            marker_field="cursor",
            filters=FilterSupport(intersects=True, ids=True, cql2=False, query=False),
            write_conditions=None,
            normalize_item=lambda item: item,
        )
        assert dialect.write_conditions is None

    def test_earth_search_writes_the_query_extension(self) -> None:
        conditions = {"eo:cloud_cover": RangeCondition(minimum=None, maximum=20.0)}
        assert EARTH_SEARCH.write_conditions is not None
        assert EARTH_SEARCH.write_conditions(conditions) == {"query": query_extension(conditions)}


class TestTheTable:
    def test_every_dialect_is_keyed_by_its_own_kind(self) -> None:
        assert all(kind is dialect.kind for kind, dialect in DIALECTS.items())

    def test_the_spec_table_declares_the_filters_of_the_dialect(self) -> None:
        """One measurement, one place: the dispatch refuses by the spec, the body is built by the dialect."""
        for kind, dialect in DIALECTS.items():
            assert ADAPTER_SPECS[kind].filters is dialect.filters

    def test_the_earth_search_entry_finds_its_dialect(self) -> None:
        assert dialect_of(SENTINEL_2_L2A) is EARTH_SEARCH

    def test_an_entry_of_a_bucket_has_no_dialect(self) -> None:
        with pytest.raises(UnsupportedSource, match="is no STAC API"):
            dialect_of(COP_DEM_GLO_30)


def _plain(**fields: object) -> StacDialect:
    """A dialect for the Earth Search kind that applies no conditions, as the FSDI's will (M5-08 plan §2)."""
    values: dict[str, object] = {
        "kind": AdapterKind.EARTH_SEARCH_V1,
        "marker_field": "cursor",
        "filters": FilterSupport(intersects=True, ids=True, cql2=False, query=False),
        "write_conditions": None,
        "normalize_item": lambda item: item,
    }
    values.update(fields)
    return StacDialect(**values)  # type: ignore[arg-type]


class CountingCache:
    def __init__(self) -> None:
        self.reads = 0

    async def get(self, key: str) -> None:
        self.reads += 1
        return None

    async def set(self, key: str, value: object, *, ttl_s: float, dataset_id: str) -> None:
        raise AssertionError("nothing may be stored")


class TestMisuse:
    @pytest.mark.parametrize("field", ["limit", "collections", "datetime", "ids"])
    def test_the_marker_cannot_take_over_a_body_field(self, field: str) -> None:
        with pytest.raises(ValueError, match="cannot take over the body field"):
            _plain(marker_field=field)

    def test_a_kind_with_two_dialects_is_refused(self) -> None:
        with pytest.raises(ValueError, match="two dialects"):
            dialect_table(EARTH_SEARCH, _plain())

    @pytest.mark.anyio
    async def test_conditions_for_a_source_without_a_query_are_refused_before_cache_and_request(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(stac_api, "DIALECTS", dialect_table(_plain()))
        gateway, seen = answering(httpx.Response(200, json=load("search_empty")))
        cache = CountingCache()
        conditions = {"eo:cloud_cover": RangeCondition(minimum=None, maximum=20.0)}
        async with gateway:
            with pytest.raises(UnsupportedFilter):
                await stac_api.search_items(
                    SENTINEL_2_L2A, SearchParams(conditions=conditions), gateway=gateway, cache=cache
                )
        assert seen == []
        assert cache.reads == 0

    @pytest.mark.anyio
    async def test_conditions_that_would_take_over_a_body_field_are_refused(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sly = _plain(
            filters=FilterSupport(intersects=True, ids=True, cql2=False, query=True),
            write_conditions=lambda conditions: {"limit": 1},
        )
        monkeypatch.setattr(stac_api, "DIALECTS", dialect_table(sly))
        gateway, seen = answering(httpx.Response(200, json=load("search_empty")))
        conditions = {"eo:cloud_cover": RangeCondition(minimum=None, maximum=20.0)}
        async with gateway:
            with pytest.raises(ValueError, match="take over a field"):
                await stac_api.search_items(SENTINEL_2_L2A, SearchParams(conditions=conditions), gateway=gateway)
        assert seen == []

    @pytest.mark.anyio
    async def test_an_item_of_an_entry_that_is_no_stac_api_is_not_fetched(self) -> None:
        gateway, seen = answering(httpx.Response(200, json=load("item")))
        async with gateway:
            with pytest.raises(UnsupportedSource, match="is no STAC API"):
                await stac_api.get_item(COP_DEM_GLO_30, "SYNTH_A", gateway=gateway)
        assert seen == []

    def test_a_spec_that_searches_as_a_stac_api_without_a_dialect_stops_the_build(self) -> None:
        dem = ADAPTER_SPECS[AdapterKind.COP_DEM_BUCKET]
        borrowed = replace(
            dem,
            search=stac_api.search_items,
            fetch=stac_api.get_item,
            filters=FilterSupport(intersects=True, ids=True, cql2=False, query=False),
        )
        table = spec_table(borrowed, *(spec for kind, spec in ADAPTER_SPECS.items() if kind is not borrowed.kind))
        with pytest.raises(AdapterSpecMismatch, match="searches as a STAC API, but has no dialect"):
            check_adapter_specs(DatasetRegistry((COP_DEM_GLO_30,)), table)
