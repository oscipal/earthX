"""DS-02: the search filters of a registry entry, their checks, the collection field and the conditions on them."""

from __future__ import annotations

import math
from dataclasses import replace

import pytest

from earthx.catalog.collection import to_stac_collection
from earthx.catalog.datasets import COP_DEM_GLO_30, SENTINEL_2_L2A
from earthx.catalog.registry import (
    ConfigError,
    CoverageProvider,
    DatasetConfig,
    FilterKind,
    FilterValue,
    ItemHolding,
    SearchFilter,
)
from earthx.catalog.search_filters import (
    InvalidFilter,
    RangeCondition,
    ValuesCondition,
    conditions_key,
    range_condition,
    values_condition,
)

CLOUD = SearchFilter(
    property="eo:cloud_cover",
    kind=FilterKind.RANGE,
    title="Cloud cover",
    description="Share of the scene covered by clouds.",
    unit="%",
    minimum=0.0,
    maximum=100.0,
    integer=False,
    values=(),
)
ORBIT = replace(CLOUD, property="sat:relative_orbit", title="Relative orbit", unit=None, minimum=1, maximum=175, integer=True)
PLATFORM = SearchFilter(
    property="platform",
    kind=FilterKind.VALUES,
    title="Satellite",
    description="The satellite that took the scene.",
    unit=None,
    minimum=None,
    maximum=None,
    integer=False,
    values=(FilterValue("sentinel-2a", "Sentinel-2A"), FilterValue("sentinel-2b", "Sentinel-2B")),
)


def _with(*filters: SearchFilter) -> DatasetConfig:
    return replace(SENTINEL_2_L2A, search_filters=filters)


class TestTheEntries:
    def test_sentinel_2_offers_cloud_cover_no_data_and_satellite(self) -> None:
        offered = [(entry.property, entry.kind) for entry in SENTINEL_2_L2A.search_filters]
        assert offered == [
            ("eo:cloud_cover", FilterKind.RANGE),
            ("s2:nodata_pixel_percentage", FilterKind.RANGE),
            ("platform", FilterKind.VALUES),
        ]
        assert [value.value for value in SENTINEL_2_L2A.search_filter("platform").values] == [
            "sentinel-2a",
            "sentinel-2b",
            "sentinel-2c",
        ]

    def test_no_orbit_filter_for_sentinel_2_because_its_items_carry_none(self) -> None:
        """DS-02 plan §6.2a: measured, the items have no `sat:` property; a filter on one would match nothing."""
        assert not [entry for entry in SENTINEL_2_L2A.search_filters if entry.property.startswith("sat:")]

    def test_the_dem_offers_none(self) -> None:
        assert COP_DEM_GLO_30.search_filters == ()
        assert COP_DEM_GLO_30.search_filter("eo:cloud_cover") is None


class TestTheEntryIsRefused:
    @pytest.mark.parametrize(
        ("broken", "message"),
        [
            (replace(CLOUD, property="Cloud"), "not a property"),
            (replace(CLOUD, property="eo:cloud:cover"), "not a property"),
            (replace(CLOUD, property="datetime"), "not a property"),
            (replace(CLOUD, property="earthx:aoi_cloud_cover"), "kept for filters the platform computes"),
            (replace(CLOUD, title=" "), "title and a description"),
            (replace(CLOUD, description=""), "title and a description"),
            (replace(CLOUD, unit=" %"), "unit"),
            (replace(CLOUD, unit="x" * 33), "unit"),
            (replace(CLOUD, minimum=None), "finite minimum and maximum"),
            (replace(CLOUD, maximum=math.inf), "finite minimum and maximum"),
            (replace(CLOUD, minimum=True), "finite minimum and maximum"),
            (replace(CLOUD, values=PLATFORM.values), "finite minimum and maximum"),
            (replace(CLOUD, minimum=100.0, maximum=100.0), "minimum below its maximum"),
            (replace(ORBIT, maximum=175.5), "whole-number bounds"),
            (replace(PLATFORM, minimum=0.0), "no bounds"),
            (replace(PLATFORM, integer=True), "no bounds"),
            (replace(PLATFORM, values=PLATFORM.values[:1]), "at least two values"),
            (replace(PLATFORM, values=(PLATFORM.values[0], PLATFORM.values[0])), "at least two values"),
            (replace(PLATFORM, values=(PLATFORM.values[0], FilterValue("sentinel-2b", " "))), "a text and a label"),
        ],
    )
    def test_a_malformed_filter(self, broken: SearchFilter, message: str) -> None:
        with pytest.raises(ConfigError, match=message):
            _with(broken)

    def test_a_property_twice(self) -> None:
        with pytest.raises(ConfigError, match="names a property twice"):
            _with(CLOUD, replace(CLOUD, title="Clouds"))

    def test_not_a_tuple(self) -> None:
        with pytest.raises(ConfigError, match="tuple of SearchFilter"):
            replace(SENTINEL_2_L2A, search_filters=[CLOUD])
        with pytest.raises(ConfigError, match="tuple of SearchFilter"):
            replace(SENTINEL_2_L2A, search_filters=CLOUD)

    def test_filters_on_items_our_own_pgstac_holds(self) -> None:
        """pgstac applies no such filter yet (plan §6.5), so a materialized entry offers none."""
        with pytest.raises(ConfigError, match="need federated items"):
            replace(COP_DEM_GLO_30, search_filters=(CLOUD,))
        with pytest.raises(ConfigError, match="need federated items"):
            replace(
                SENTINEL_2_L2A,
                source=replace(SENTINEL_2_L2A.source, item_holding=ItemHolding.MATERIALIZED),
                coverage=replace(SENTINEL_2_L2A.coverage, provider=CoverageProvider.LOCAL_SQL),
            )

    def test_a_well_formed_set_is_taken(self) -> None:
        assert _with(CLOUD, ORBIT, PLATFORM).search_filter("platform") == PLATFORM


class TestTheCollection:
    def test_publishes_the_filters_in_the_words_of_queryables(self) -> None:
        published = to_stac_collection(_with(CLOUD, ORBIT, PLATFORM))["earthx:search_filters"]
        assert published == [
            {
                "property": "eo:cloud_cover",
                "kind": "range",
                "title": "Cloud cover",
                "description": "Share of the scene covered by clouds.",
                "unit": "%",
                "type": "number",
                "minimum": 0.0,
                "maximum": 100.0,
            },
            {
                "property": "sat:relative_orbit",
                "kind": "range",
                "title": "Relative orbit",
                "description": "Share of the scene covered by clouds.",
                "unit": None,
                "type": "integer",
                "minimum": 1,
                "maximum": 175,
            },
            {
                "property": "platform",
                "kind": "values",
                "title": "Satellite",
                "description": "The satellite that took the scene.",
                "unit": None,
                "type": "string",
                "oneOf": [
                    {"const": "sentinel-2a", "title": "Sentinel-2A"},
                    {"const": "sentinel-2b", "title": "Sentinel-2B"},
                ],
            },
        ]

    def test_an_entry_without_filters_publishes_an_empty_list(self) -> None:
        assert to_stac_collection(COP_DEM_GLO_30)["earthx:search_filters"] == []


class TestARange:
    def test_both_bounds(self) -> None:
        assert range_condition(CLOUD, 0, 20) == RangeCondition(minimum=0.0, maximum=20.0)

    def test_one_open_bound(self) -> None:
        assert range_condition(CLOUD, None, 20.5) == RangeCondition(minimum=None, maximum=20.5)
        assert range_condition(CLOUD, 80, None) == RangeCondition(minimum=80.0, maximum=None)

    def test_the_edges_of_the_filter_are_inside(self) -> None:
        assert range_condition(CLOUD, 0, 100) == RangeCondition(minimum=0.0, maximum=100.0)

    def test_a_single_whole_number(self) -> None:
        assert range_condition(ORBIT, 22, 22) == RangeCondition(minimum=22.0, maximum=22.0)

    @pytest.mark.parametrize(
        ("minimum", "maximum", "message"),
        [
            (None, None, "no bound"),
            ("10", None, "not a number"),
            (True, None, "not a number"),
            (None, math.nan, "not a number"),
            (None, math.inf, "not a number"),
            (-0.5, None, "outside the range"),
            (None, 100.5, "outside the range"),
            (30, 20, "ends below its start"),
        ],
    )
    def test_refused(self, minimum: object, maximum: object, message: str) -> None:
        with pytest.raises(InvalidFilter, match=message):
            range_condition(CLOUD, minimum, maximum)

    def test_a_fraction_on_a_whole_number_filter(self) -> None:
        with pytest.raises(InvalidFilter, match="not a whole number"):
            range_condition(ORBIT, 22.5, None)

    def test_a_range_on_a_values_filter(self) -> None:
        with pytest.raises(InvalidFilter, match="takes a list of values"):
            range_condition(PLATFORM, 0, 1)

    def test_no_message_names_the_value(self) -> None:
        with pytest.raises(InvalidFilter) as caught:
            range_condition(CLOUD, None, 123.456)
        assert "123" not in str(caught.value)


class TestValues:
    def test_sorted_and_kept(self) -> None:
        condition = values_condition(PLATFORM, ["sentinel-2b", "sentinel-2a"])
        assert condition == ValuesCondition(values=("sentinel-2a", "sentinel-2b"))

    @pytest.mark.parametrize(
        ("values", "message"),
        [
            ([], "non-empty list"),
            ("sentinel-2a", "non-empty list"),
            (["sentinel-9z"], "not one it offers"),
            ([1], "not one it offers"),
            (["sentinel-2a", "sentinel-2a"], "listed twice"),
        ],
    )
    def test_refused(self, values: object, message: str) -> None:
        with pytest.raises(InvalidFilter, match=message) as caught:
            values_condition(PLATFORM, values)
        assert "sentinel-9z" not in str(caught.value)

    def test_values_on_a_range_filter(self) -> None:
        with pytest.raises(InvalidFilter, match="takes a range"):
            values_condition(CLOUD, ["a"])


def test_the_key_of_the_same_question_is_one_spelling() -> None:
    first = {"platform": ValuesCondition(("sentinel-2a",)), "eo:cloud_cover": RangeCondition(None, 20.0)}
    second = {"eo:cloud_cover": RangeCondition(None, 20.0), "platform": ValuesCondition(("sentinel-2a",))}
    assert conditions_key(first) == conditions_key(second)
    assert conditions_key(first) == {"eo:cloud_cover": ["range", None, 20.0], "platform": ["values", ["sentinel-2a"]]}
