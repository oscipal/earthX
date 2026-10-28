"""DS-02: conditions on a dataset's search filters, from ``SearchParams`` to the request Earth Search gets."""

from __future__ import annotations

from dataclasses import replace

import httpx
import pytest

from earthx.adapters import (
    ADAPTER_SPECS,
    AdapterSpecMismatch,
    InvalidQuery,
    SearchParams,
    UnsupportedFilter,
    check_adapter_specs,
    search_items,
)
from earthx.adapters.earth_search import query_extension
from earthx.adapters.earth_search import search_items as earth_search_items
from earthx.adapters.federated_search import search_fingerprint
from earthx.adapters.spec import AdapterSpecs, spec_table
from earthx.catalog.datasets import SENTINEL_2_L2A
from earthx.catalog.registry import AdapterKind, DatasetRegistry
from earthx.catalog.search_filters import RangeCondition, ValuesCondition

from .conftest import answering, body_of, load

pytestmark = pytest.mark.anyio

CONDITIONS = {
    "eo:cloud_cover": RangeCondition(minimum=None, maximum=20.0),
    "s2:nodata_pixel_percentage": RangeCondition(minimum=0.0, maximum=5.0),
    "platform": ValuesCondition(values=("sentinel-2a", "sentinel-2c")),
}


def _without_query() -> AdapterSpecs:
    spec = ADAPTER_SPECS[AdapterKind.EARTH_SEARCH_V1]
    stub = replace(spec, filters=replace(spec.filters, query=False))
    return spec_table(stub, *(other for kind, other in ADAPTER_SPECS.items() if kind is not stub.kind))


class TestTheRequest:
    async def test_carries_the_conditions_as_the_query_extension(self) -> None:
        gateway, seen = answering(httpx.Response(200, json=load("search_empty")))
        async with gateway:
            await earth_search_items(SENTINEL_2_L2A, SearchParams(conditions=CONDITIONS), gateway=gateway)
        assert body_of(seen[0])["query"] == {
            "eo:cloud_cover": {"lte": 20.0},
            "s2:nodata_pixel_percentage": {"gte": 0.0, "lte": 5.0},
            "platform": {"in": ["sentinel-2a", "sentinel-2c"]},
        }

    async def test_carries_no_query_without_conditions(self) -> None:
        gateway, seen = answering(httpx.Response(200, json=load("search_empty")))
        async with gateway:
            await earth_search_items(SENTINEL_2_L2A, SearchParams(), gateway=gateway)
        assert "query" not in body_of(seen[0])

    def test_a_lower_bound_alone(self) -> None:
        assert query_extension({"eo:cloud_cover": RangeCondition(minimum=50.0, maximum=None)}) == {
            "eo:cloud_cover": {"gte": 50.0}
        }


class TestTheFingerprint:
    def test_conditions_make_it_another_search(self) -> None:
        assert search_fingerprint("ds", SearchParams()) != search_fingerprint("ds", SearchParams(conditions=CONDITIONS))

    def test_different_conditions_are_different_searches(self) -> None:
        other = {**CONDITIONS, "eo:cloud_cover": RangeCondition(minimum=None, maximum=30.0)}
        assert search_fingerprint("ds", SearchParams(conditions=CONDITIONS)) != search_fingerprint(
            "ds", SearchParams(conditions=other)
        )

    def test_the_order_of_the_conditions_does_not_matter(self) -> None:
        reversed_order = dict(reversed(list(CONDITIONS.items())))
        assert search_fingerprint("ds", SearchParams(conditions=CONDITIONS)) == search_fingerprint(
            "ds", SearchParams(conditions=reversed_order)
        )


class TestRefused:
    def test_empty_conditions(self) -> None:
        with pytest.raises(InvalidQuery, match="omit it"):
            SearchParams(conditions={})

    def test_something_that_is_no_condition(self) -> None:
        with pytest.raises(InvalidQuery, match="no search filter condition"):
            SearchParams(conditions={"eo:cloud_cover": {"lte": 20}})

    async def test_by_a_source_that_applies_no_query(self) -> None:
        gateway, seen = answering(httpx.Response(200, json=load("search_empty")))
        async with gateway:
            with pytest.raises(UnsupportedFilter, match="search filters"):
                await search_items(
                    SENTINEL_2_L2A, SearchParams(conditions=CONDITIONS), adapters=_without_query(), gateway=gateway
                )
        assert seen == []

    def test_an_app_whose_entry_has_filters_its_source_cannot_apply(self) -> None:
        with pytest.raises(AdapterSpecMismatch, match="applies no query"):
            check_adapter_specs(DatasetRegistry((SENTINEL_2_L2A,)), _without_query())

    def test_an_entry_without_filters_needs_no_query(self) -> None:
        check_adapter_specs(DatasetRegistry((replace(SENTINEL_2_L2A, search_filters=()),)), _without_query())
