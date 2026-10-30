"""DS-02 plan §6.4: ``query`` and ``query_by_collection`` of a search body, read into conditions per collection."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest

from earthx.api.search_filters import AOI_CLOUD_COVER, SearchConditions, read_search_conditions
from earthx.catalog.datasets import SENTINEL_2_L2A
from earthx.catalog.registry import SearchFilter
from earthx.catalog.search_filters import InvalidFilter, RangeCondition, ValuesCondition

S2 = "s2"
CLOUD_ONLY = "cloud-only"
NONE = "none"
FILTERS: dict[str, tuple[SearchFilter, ...]] = {
    S2: SENTINEL_2_L2A.search_filters,
    CLOUD_ONLY: (SENTINEL_2_L2A.search_filter("eo:cloud_cover"),),
    NONE: (),
}


def _read(body: dict[str, Any], collections: tuple[str, ...] = (S2, CLOUD_ONLY, NONE)) -> SearchConditions:
    return read_search_conditions(body, collections, FILTERS.__getitem__)


class TestQuery:
    def test_goes_to_every_collection_that_offers_the_property(self) -> None:
        read = _read({"query": {"eo:cloud_cover": {"lte": 20}, "platform": {"in": ["sentinel-2c"]}}})
        assert read.by_collection == {
            S2: {"eo:cloud_cover": RangeCondition(None, 20.0), "platform": ValuesCondition(("sentinel-2c",))},
            CLOUD_ONLY: {"eo:cloud_cover": RangeCondition(None, 20.0)},
        }

    def test_names_what_a_collection_does_not_offer(self) -> None:
        read = _read({"query": {"eo:cloud_cover": {"lte": 20}, "platform": {"in": ["sentinel-2c"]}}})
        assert read.dropped == {CLOUD_ONLY: ("platform",), NONE: ("eo:cloud_cover", "platform")}

    def test_a_property_no_searched_collection_offers(self) -> None:
        with pytest.raises(InvalidFilter, match="platform is no filter of a searched collection"):
            _read({"query": {"platform": {"in": ["sentinel-2a"]}}}, (CLOUD_ONLY, NONE))

    def test_an_empty_query_filters_nothing(self) -> None:
        assert _read({"query": {}}) == SearchConditions()


class TestQueryByCollection:
    def test_each_collection_gets_its_own_values(self) -> None:
        read = _read(
            {
                "query_by_collection": {
                    S2: {"platform": {"in": ["sentinel-2a"]}},
                    CLOUD_ONLY: {"eo:cloud_cover": {"gte": 50}},
                }
            }
        )
        assert read.by_collection == {
            S2: {"platform": ValuesCondition(("sentinel-2a",))},
            CLOUD_ONLY: {"eo:cloud_cover": RangeCondition(50.0, None)},
        }
        assert read.dropped == {}

    def test_a_property_its_collection_does_not_offer(self) -> None:
        with pytest.raises(InvalidFilter, match="platform is no filter of the collection it is given for"):
            _read({"query_by_collection": {CLOUD_ONLY: {"platform": {"in": ["sentinel-2a"]}}}})

    def test_a_collection_the_search_does_not_name(self) -> None:
        with pytest.raises(InvalidFilter, match="names a collection the search does not") as caught:
            _read({"query_by_collection": {"elsewhere-77": {"eo:cloud_cover": {"lte": 1}}}})
        assert "elsewhere-77" not in str(caught.value)

    def test_together_with_query(self) -> None:
        with pytest.raises(InvalidFilter, match="not both"):
            _read({"query": {}, "query_by_collection": {}})


@pytest.mark.parametrize(
    ("query", "message"),
    [
        ([], "query is a JSON object"),
        ({"eo:cloud_cover": 20}, "an object of operators"),
        ({"eo:cloud_cover": {}}, "an object of operators"),
        ({"eo:cloud_cover": {"lt": 20}}, "takes the operators gte and lte"),
        ({"eo:cloud_cover": {"in": [1]}}, "takes the operators gte and lte"),
        ({"platform": {"eq": "sentinel-2a"}}, "takes the operator in"),
        ({"platform": {"in": ["sentinel-2a"], "lte": 1}}, "takes the operator in"),
        ({"eo:cloud_cover": {"lte": "abc"}}, "not a number"),
        ({"eo:cloud_cover": {"gte": 30, "lte": 20}}, "ends below its start"),
        ({"platform": {"in": ["sentinel-9z"]}}, "not one it offers"),
        ({"earthx:something_else": {"lte": 5}}, "computed by the platform, not offered yet"),
        ({"Not A Property; DROP": {"lte": 5}}, "a property is no filter"),
    ],
)
def test_a_query_a_caller_has_to_change(query: Any, message: str) -> None:
    with pytest.raises(InvalidFilter, match=message) as caught:
        _read({"query": query})
    for value in ("abc", "sentinel-9z", "DROP"):
        assert value not in str(caught.value)


def test_a_body_without_filters() -> None:
    assert _read({"collections": [S2]}) == SearchConditions()


class TestCloudShareInTheAoi:
    """DS-03 plan §6.5: ``earthx:aoi_cloud_cover`` takes the range of the filter whose registry entry says ``within_aoi``."""

    def test_in_query_it_is_kept_apart_for_each_collection_that_offers_it(self) -> None:
        read = _read({"query": {AOI_CLOUD_COVER: {"lte": 20}, "platform": {"in": ["sentinel-2c"]}}}, (S2, NONE))
        assert read.aoi_cloud_cover == {S2: RangeCondition(None, 20.0)}
        assert read.by_collection == {S2: {"platform": ValuesCondition(("sentinel-2c",))}}, "the source never gets it"
        assert read.dropped == {NONE: (AOI_CLOUD_COVER, "platform")}

    def test_in_query_by_collection_it_is_the_collections_own(self) -> None:
        read = _read({"query_by_collection": {S2: {AOI_CLOUD_COVER: {"gte": 10, "lte": 30}}}})
        assert read.aoi_cloud_cover == {S2: RangeCondition(10.0, 30.0)}
        assert read.by_collection == {} and read.dropped == {}

    def test_it_may_stand_beside_the_scene_filter(self) -> None:
        read = _read({"query_by_collection": {S2: {"eo:cloud_cover": {"lte": 50}, AOI_CLOUD_COVER: {"lte": 10}}}})
        assert read.by_collection == {S2: {"eo:cloud_cover": RangeCondition(None, 50.0)}}
        assert read.aoi_cloud_cover == {S2: RangeCondition(None, 10.0)}

    def test_it_takes_the_bounds_of_the_filter_it_follows(self) -> None:
        for bad in ({"lte": 100.5}, {"gte": -1}, {"gte": 30, "lte": 10}, {"lt": 5}, {"in": [1]}, {}):
            with pytest.raises(InvalidFilter):
                _read({"query_by_collection": {S2: {AOI_CLOUD_COVER: bad}}})

    def test_a_collection_without_within_aoi_does_not_offer_it(self) -> None:
        with pytest.raises(InvalidFilter, match=f"{AOI_CLOUD_COVER} is no filter of the collection it is given for"):
            _read({"query_by_collection": {NONE: {AOI_CLOUD_COVER: {"lte": 20}}}})
        with pytest.raises(InvalidFilter, match=f"{AOI_CLOUD_COVER} is no filter of a searched collection"):
            _read({"query": {AOI_CLOUD_COVER: {"lte": 20}}}, (NONE,))

    def test_a_cloud_cover_filter_without_within_aoi_does_not_offer_it_either(self) -> None:
        plain = {"plain": (replace(SENTINEL_2_L2A.search_filter("eo:cloud_cover"), within_aoi=False),)}
        with pytest.raises(InvalidFilter):
            read_search_conditions({"query_by_collection": {"plain": {AOI_CLOUD_COVER: {"lte": 20}}}}, ["plain"], plain.__getitem__)

    def test_every_other_earthx_property_stays_refused(self) -> None:
        with pytest.raises(InvalidFilter, match="computed by the platform, not offered yet"):
            _read({"query": {"earthx:something_else": {"lte": 20}}})

    def test_it_is_no_property_of_the_registry_entries(self) -> None:
        assert all(AOI_CLOUD_COVER != entry.property for entries in FILTERS.values() for entry in entries)
