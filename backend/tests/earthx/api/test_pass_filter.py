"""DS-03c: a search judged per overpass and the coverage of the AOI, the pieces without a database or a source.

The loop runs on a source and a measure made of plain functions, with a clock the test moves. The outlines are synthetic
squares on a degree grid, so every area and every share can be worked out by hand. The reading of rasters is DS-03c's access tests'.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import Any

import pytest

from earthx.access.outlines import AoiOutlines, mosaic_weights, outline_of
from earthx.adapters import InvalidQuery, ItemPage
from earthx.api import aoi_cloud_filter as filter_module
from earthx.api.aoi_cloud_filter import (
    AoiFilterRequest,
    Cursor,
    SceneMeasure,
    decode_cursor,
    read_aoi_request,
    run_filter,
)
from earthx.api.pass_filter import (
    CLUSTER_GAP_S,
    MAX_CLUSTER,
    judge_properties,
    overpass_key,
    run_pass_filter,
    weighted_value,
)
from earthx.catalog.datasets import SENTINEL_2_L2A
from earthx.catalog.registry import AoiMeasure, FilterKind, SearchFilter
from earthx.catalog.search_filters import RangeCondition, ValuesCondition

pytestmark = pytest.mark.anyio

FILTERS = {entry.property: entry for entry in SENTINEL_2_L2A.search_filters}
KEY_OF = overpass_key(SENTINEL_2_L2A.viewer)
CLOUD = "eo:cloud_cover"
SHARES = {entry.measure: entry.classes for entry in SENTINEL_2_L2A.mask.share_classes}
#: The AOI: a degree square, 10° east, 10° north.
AOI_SQUARE = {"type": "Polygon", "coordinates": [[[10.0, 10.0], [11.0, 10.0], [11.0, 11.0], [10.0, 11.0], [10.0, 10.0]]]}
PERIOD = "2024-05-01T00:00:00Z/2024-06-01T00:00:00Z"


def box_geometry(west: float, east: float, south: float = 10.0, north: float = 11.0) -> dict[str, Any]:
    return {
        "type": "Polygon",
        "coordinates": [[[west, south], [east, south], [east, north], [west, north], [west, south]]],
    }


def scene(
    name: str,
    minutes: float,
    datatake: str,
    *,
    west: float = 10.0,
    east: float = 11.0,
    day: int = 10,
    **properties: Any,
) -> dict[str, Any]:
    """A scene of Sentinel-2: ``minutes`` after 10:00 on ``day``, in the datatake, over ``west``..``east`` degrees."""
    stamp = f"2024-05-{day:02d}T{10 + int(minutes // 60):02d}:{int(minutes % 60):02d}:{int(minutes % 1 * 60):02d}Z"
    return {
        "id": name,
        "collection": SENTINEL_2_L2A.dataset_id,
        "geometry": box_geometry(west, east),
        "properties": {"datetime": stamp, "s2:datatake_id": datatake, **properties},
    }


def pass_request(
    *conditions_by_property: tuple[str, Any],
    coverage: RangeCondition | None = None,
    measures: Mapping[AoiMeasure, RangeCondition] | None = None,
    aoi: Mapping[str, Any] | None = AOI_SQUARE,
) -> AoiFilterRequest:
    judged = dict(conditions_by_property)
    return read_aoi_request(
        SENTINEL_2_L2A.dataset_id,
        measures or {},
        datetime_value=PERIOD,
        bbox=None,
        intersects=aoi if (measures or coverage is not None) else None,
        earthx_aoi=None,
        coverage=coverage,
        evaluate_pass=True,
        scene_conditions=judged,
        filters=SENTINEL_2_L2A.search_filters,
        share_classes=SHARES,
    )


def order_by_id(items: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(items, key=lambda item: item["id"])


class Source:
    """Scenes in the order of the source (newest first), in pages of ``size``; remembers the markers it was asked for."""

    def __init__(self, items: Sequence[dict[str, Any]], size: int = 100) -> None:
        self.items = sorted(items, key=lambda item: (item["properties"]["datetime"], item["id"]), reverse=True)
        self.size = size
        self.asked: list[str | None] = []

    async def fetch(self, marker: str | None) -> ItemPage:
        self.asked.append(marker)
        start = 0 if marker is None else int(marker)
        end = min(start + self.size, len(self.items))
        return ItemPage(
            items=tuple(self.items[start:end]),
            matched=None,
            next_page_token=str(end) if end < len(self.items) else None,
            from_cache=False,
        )


async def never_measure(items: Sequence[dict[str, Any]]) -> SceneMeasure | None:
    raise AssertionError("a search that reads no pixel measured a pass")


async def judged(
    request: AoiFilterRequest,
    source: Source,
    *,
    measure=never_measure,
    limit: int = 100,
    token: str | None = None,
    order=order_by_id,
    **extra: Any,
):
    try:
        return await run_pass_filter(
            request,
            fetch_page=source.fetch,
            group_of=KEY_OF,
            order_of=order,
            measure_pass=measure,
            limit=limit,
            token=token,
            **extra,
        )
    finally:
        await filter_module.settle()


def ids(outcome) -> list[str]:
    return sorted(item["id"] for item in outcome.items)


CLOUD_AT_MOST_20 = (CLOUD, RangeCondition(None, 20.0))


class TestAPassStaysOrFallsAsAWhole:
    async def test_a_pass_whose_merged_value_meets_the_filter_keeps_all_its_scenes(self) -> None:
        """Two equal scenes with 30 % and 10 %: the pass has 20 %, so a scene at 30 % stays with it."""
        source = Source([
            scene("a", 0, "d1", west=10.0, east=11.0, **{CLOUD: 30.0}),
            scene("b", 0.5, "d1", west=11.0, east=12.0, **{CLOUD: 10.0}),
        ])
        outcome = await judged(pass_request(CLOUD_AT_MOST_20), source)
        assert ids(outcome) == ["a", "b"]

    async def test_a_pass_that_misses_it_falls_with_the_scene_that_would_pass_alone(self) -> None:
        """Gegenprobe: 10 % alone meets "up to 10", but its pass has 20 %, so both go."""
        source = Source([
            scene("a", 0, "d1", west=10.0, east=11.0, **{CLOUD: 30.0}),
            scene("b", 0.5, "d1", west=11.0, east=12.0, **{CLOUD: 10.0}),
        ])
        outcome = await judged(pass_request((CLOUD, RangeCondition(None, 10.0))), source)
        assert outcome.items == []
        assert outcome.summary()["checked"] == 2 and outcome.summary()["found"] == 0

    async def test_per_scene_keeps_only_the_scene_that_meets_it_alone(self) -> None:
        """The same two scenes, judged one by one: the other way of the switch."""
        a = scene("a", 0, "d1", west=10.0, east=11.0, **{CLOUD: 30.0})
        b = scene("b", 0.5, "d1", west=11.0, east=12.0, **{CLOUD: 10.0})
        alone = [judge_properties(pass_request(CLOUD_AT_MOST_20), [item], [outline_of(item)]) for item in (a, b)]
        assert alone == [False, True]

    async def test_the_passes_of_one_answer_are_judged_each_on_its_own(self) -> None:
        source = Source([
            scene("a1", 0, "d1", west=10.0, east=11.0, **{CLOUD: 30.0}),
            scene("a2", 0.5, "d1", west=11.0, east=12.0, **{CLOUD: 10.0}),
            scene("b1", 120, "d2", west=10.0, east=11.0, **{CLOUD: 40.0}),
            scene("b2", 120.5, "d2", west=11.0, east=12.0, **{CLOUD: 30.0}),
            scene("c", 240, "d3", **{CLOUD: 5.0}),
        ])
        outcome = await judged(pass_request(CLOUD_AT_MOST_20), source)
        assert ids(outcome) == ["a1", "a2", "c"]
        assert outcome.summary() == {"checked": 5, "found": 3, "unreadable": 0, "limit_reached": False}

    async def test_the_answer_keeps_the_order_of_the_source(self) -> None:
        source = Source([
            scene("a", 0, "d1", **{CLOUD: 1.0}),
            scene("b", 0.5, "d1", west=11.0, east=12.0, **{CLOUD: 1.0}),
            scene("c", 1, "d1", west=12.0, east=13.0, **{CLOUD: 1.0}),
        ])
        outcome = await judged(pass_request(CLOUD_AT_MOST_20), source, order=lambda items: sorted(items, key=lambda i: i["id"], reverse=True))
        assert [item["id"] for item in outcome.items] == [item["id"] for item in source.items]

    async def test_a_scene_does_not_bring_the_fields_of_a_measure_it_never_had(self) -> None:
        source = Source([scene("a", 0, "d1", **{CLOUD: 1.0})])
        outcome = await judged(pass_request(CLOUD_AT_MOST_20), source)
        assert "earthx:aoi_measure" not in outcome.items[0]["properties"]


class TestAnOverlapCountsOnce:
    def overlapping(self) -> list[dict[str, Any]]:
        """a over 10..12 degrees with 30 % and b over 11..13 with 10 %: they overlap on 11..12."""
        return [
            scene("a", 0, "d1", west=10.0, east=12.0, **{CLOUD: 30.0}),
            scene("b", 0.5, "d1", west=11.0, east=13.0, **{CLOUD: 10.0}),
        ]

    def test_the_weights_are_the_area_each_scene_adds(self) -> None:
        a, b = self.overlapping()
        first, second = mosaic_weights([outline_of(a), outline_of(b)]) or (0, 0)
        assert second / first == pytest.approx(0.5, rel=0.01)  # b adds 12..13: half of what a has

    def test_the_value_is_the_mean_of_the_area_each_scene_adds_not_of_the_scenes(self) -> None:
        a, b = self.overlapping()
        weights = mosaic_weights([outline_of(a), outline_of(b)])
        assert weighted_value([a, b], CLOUD, weights) == pytest.approx((2 * 30.0 + 1 * 10.0) / 3, rel=0.01)  # 23.3, not 20

    def test_the_other_order_of_the_mosaic_gives_the_other_value(self) -> None:
        """Gegenprobe: the scene the mosaic takes first owns the overlap."""
        a, b = self.overlapping()
        weights = mosaic_weights([outline_of(b), outline_of(a)])
        assert weighted_value([b, a], CLOUD, weights) == pytest.approx((2 * 10.0 + 1 * 30.0) / 3, rel=0.01)  # 16.7

    async def test_a_filter_at_20_keeps_the_pass_in_one_order_and_drops_it_in_the_other(self) -> None:
        source = Source(self.overlapping())
        a_first = await judged(pass_request(CLOUD_AT_MOST_20), source, order=order_by_id)
        b_first = await judged(pass_request(CLOUD_AT_MOST_20), source, order=lambda items: order_by_id(items)[::-1])
        assert ids(a_first) == [] and ids(b_first) == ["a", "b"]

    def test_a_scene_wholly_under_an_earlier_one_has_no_say(self) -> None:
        under = scene("c", 1, "d1", west=10.5, east=11.5)  # inside a, and lacks the property
        a = scene("a", 0, "d1", west=10.0, east=12.0, **{CLOUD: 30.0})
        weights = mosaic_weights([outline_of(a), outline_of(under)])
        assert weights is not None and weights[1] == pytest.approx(0.0, abs=1e-6)
        assert weighted_value([a, under], CLOUD, weights) == 30.0

    def test_a_scene_that_adds_area_and_lacks_the_value_leaves_the_pass_without_one(self) -> None:
        a = scene("a", 0, "d1", west=10.0, east=12.0, **{CLOUD: 30.0})
        bare = scene("b", 1, "d1", west=11.0, east=13.0)
        assert weighted_value([a, bare], CLOUD, mosaic_weights([outline_of(a), outline_of(bare)])) is None

    def test_one_scene_has_its_own_value_whatever_its_outline(self) -> None:
        only = {"id": "x", "properties": {CLOUD: 12.34}}  # no geometry
        assert weighted_value([only], CLOUD, None) == 12.34

    def test_a_pass_of_several_scenes_without_an_outline_has_no_value(self) -> None:
        a = {"id": "a", "properties": {CLOUD: 1.0}}
        b = {"id": "b", "properties": {CLOUD: 1.0}}
        assert weighted_value([a, b], CLOUD, mosaic_weights([outline_of(a), outline_of(b)])) is None


# Properties of the registry, one pass and one that is not, for each filter (every filter works per pass).
PASSING_AND_FAILING: dict[str, tuple[Any, Any, Any]] = {
    # property: (condition, a value that meets it, a value that does not)
    "eo:cloud_cover": (RangeCondition(None, 20.0), 10.0, 50.0),
    "s2:thin_cirrus_percentage": (RangeCondition(None, 5.0), 1.0, 30.0),
    "s2:cloud_shadow_percentage": (RangeCondition(None, 5.0), 1.0, 30.0),
    "s2:nodata_pixel_percentage": (RangeCondition(None, 5.0), 1.0, 30.0),
    "s2:snow_ice_percentage": (RangeCondition(None, 5.0), 1.0, 30.0),
    "s2:water_percentage": (RangeCondition(None, 5.0), 1.0, 30.0),
    "s2:vegetation_percentage": (RangeCondition(50.0, None), 80.0, 10.0),
    "s2:not_vegetated_percentage": (RangeCondition(50.0, None), 80.0, 10.0),
    "s2:degraded_msi_data_percentage": (RangeCondition(None, 1.0), 0.0, 9.0),
    "platform": (ValuesCondition(("sentinel-2a",)), "sentinel-2a", "sentinel-2b"),
    "view:sun_elevation": (RangeCondition(30.0, None), 50.0, 10.0),
    "view:sun_azimuth": (RangeCondition(None, 180.0), 120.0, 300.0),
    "s2:processing_baseline": (ValuesCondition(("05.11",)), "05.11", "05.00"),
}


def test_the_table_names_every_filter_of_the_registry() -> None:
    assert set(PASSING_AND_FAILING) == set(FILTERS)


@pytest.mark.parametrize("name", sorted(PASSING_AND_FAILING))
class TestEveryFilterWorksPerPass:
    def two_scenes(self, name: str, first: Any, second: Any) -> list[dict[str, Any]]:
        return [
            scene("a", 0, "d1", west=10.0, east=11.0, **{name: first}),
            scene("b", 0.5, "d1", west=11.0, east=12.0, **{name: second}),
        ]

    async def test_a_pass_that_meets_it_stays(self, name: str) -> None:
        condition, good, _ = PASSING_AND_FAILING[name]
        outcome = await judged(pass_request((name, condition)), Source(self.two_scenes(name, good, good)))
        assert ids(outcome) == ["a", "b"]

    async def test_a_pass_that_misses_it_falls(self, name: str) -> None:
        condition, _, bad = PASSING_AND_FAILING[name]
        outcome = await judged(pass_request((name, condition)), Source(self.two_scenes(name, bad, bad)))
        assert outcome.items == []

    async def test_a_scene_without_the_property_does_not_meet_it(self, name: str) -> None:
        condition, good, _ = PASSING_AND_FAILING[name]
        source = Source([scene("a", 0, "d1", **{name: good}), scene("b", 0.5, "d1", west=11.0, east=12.0)])
        outcome = await judged(pass_request((name, condition)), source)
        assert outcome.items == []

    def test_the_registry_says_which_kind_it_is(self, name: str) -> None:
        entry = FILTERS[name]
        assert entry.area_based == (entry.kind is FilterKind.RANGE and entry.unit == "%")


class TestAFilterWithoutAnArea:
    """The satellite, the sun, the baseline: a pass meets one if every scene of it does (unique, or all within)."""

    def test_the_same_value_in_all_scenes_is_the_value_of_the_pass(self) -> None:
        a = scene("a", 0, "d1", platform="sentinel-2a")
        b = scene("b", 1, "d1", west=11.0, east=12.0, platform="sentinel-2a")
        request = pass_request(("platform", ValuesCondition(("sentinel-2a",))))
        assert judge_properties(request, [a, b], [outline_of(a), outline_of(b)])

    def test_different_values_in_one_pass_all_have_to_be_among_the_choices(self) -> None:
        a = scene("a", 0, "d1", **{"s2:processing_baseline": "05.11"})
        b = scene("b", 1, "d1", west=11.0, east=12.0, **{"s2:processing_baseline": "05.12"})
        outlines = [outline_of(a), outline_of(b)]
        one = pass_request(("s2:processing_baseline", ValuesCondition(("05.11",))))
        both = pass_request(("s2:processing_baseline", ValuesCondition(("05.11", "05.12"))))
        assert not judge_properties(one, [a, b], outlines)
        assert judge_properties(both, [a, b], outlines)

    def test_a_number_that_differs_in_a_pass_must_lie_in_the_range_in_every_scene(self) -> None:
        a = scene("a", 0, "d1", **{"view:sun_elevation": 44.0})
        b = scene("b", 1, "d1", west=11.0, east=12.0, **{"view:sun_elevation": 46.0})
        outlines = [outline_of(a), outline_of(b)]
        assert judge_properties(pass_request(("view:sun_elevation", RangeCondition(40.0, 50.0))), [a, b], outlines)
        assert not judge_properties(pass_request(("view:sun_elevation", RangeCondition(45.0, 50.0))), [a, b], outlines)

    def test_it_is_not_weighted_by_area(self) -> None:
        """Gegenprobe: a big scene at 44° and a small one at 30° with "at least 40": the small one fails the pass."""
        big = scene("a", 0, "d1", west=10.0, east=14.0, **{"view:sun_elevation": 44.0})
        small = scene("b", 1, "d1", west=14.0, east=14.1, **{"view:sun_elevation": 30.0})
        request = pass_request(("view:sun_elevation", RangeCondition(40.0, None)))
        assert not judge_properties(request, [big, small], [outline_of(big), outline_of(small)])


class TestSeveralFilters:
    async def test_every_filter_has_to_be_met_by_the_pass(self) -> None:
        source = Source([
            scene("a", 0, "d1", platform="sentinel-2a", **{CLOUD: 5.0}),
            scene("b", 0.5, "d1", west=11.0, east=12.0, platform="sentinel-2a", **{CLOUD: 5.0}),
        ])
        both = pass_request(CLOUD_AT_MOST_20, ("platform", ValuesCondition(("sentinel-2a",))))
        wrong = pass_request(CLOUD_AT_MOST_20, ("platform", ValuesCondition(("sentinel-2b",))))
        assert ids(await judged(both, source)) == ["a", "b"]
        assert (await judged(wrong, source)).items == []


class TestTheCoverageOfTheAoi:
    """Synthetic outlines over the AOI of 10..11°: each share is a fraction of the degrees it covers."""

    COVER_60 = RangeCondition(60.0, None)

    def test_the_share_is_the_part_of_the_aoi_the_outline_covers(self) -> None:
        aoi = AoiOutlines(AOI_SQUARE)
        left = outline_of(scene("a", 0, "d", west=9.0, east=10.4))
        assert aoi.coverage([left]) == pytest.approx(40.0, abs=0.2)
        assert aoi.coverage([outline_of(scene("a", 0, "d", west=9.0, east=12.0))]) == 100.0

    def test_an_outline_beside_the_aoi_covers_nothing(self) -> None:
        assert AoiOutlines(AOI_SQUARE).coverage([outline_of(scene("a", 0, "d", west=20.0, east=21.0))]) == 0.0

    def test_the_outlines_together_cover_what_each_covers_once(self) -> None:
        aoi = AoiOutlines(AOI_SQUARE)
        left = outline_of(scene("a", 0, "d", west=9.0, east=10.6))
        right = outline_of(scene("b", 0, "d", west=10.4, east=12.0))
        assert aoi.coverage([left, right]) == 100.0  # 0.6 + 0.6 overlap, not 120 %

    def test_a_scene_without_an_outline_has_no_share(self) -> None:
        assert AoiOutlines(AOI_SQUARE).coverage([None]) is None
        assert AoiOutlines(AOI_SQUARE).coverage([]) is None

    @pytest.mark.parametrize(
        "geometry", [None, {}, {"type": "Point", "coordinates": [10, 10]}, {"type": "Polygon", "coordinates": []}]
    )
    def test_an_item_whose_geometry_is_no_area_has_no_outline(self, geometry: Any) -> None:
        assert outline_of({"id": "x", "geometry": geometry}) is None

    @pytest.mark.parametrize("aoi", [{"type": "Point", "coordinates": [10, 10]}, {}])
    def test_an_aoi_that_is_no_area_is_refused(self, aoi: Any) -> None:
        with pytest.raises(ValueError):
            AoiOutlines(aoi)

    async def test_per_pass_the_outlines_of_the_scenes_together_decide(self) -> None:
        """Two scenes of 45 % and 40 % that do not overlap: 85 % together, so the pass meets "at least 60"."""
        source = Source([
            scene("a", 0, "d1", west=9.0, east=10.45),
            scene("b", 0.5, "d1", west=10.6, east=12.0),
        ])
        outcome = await judged(pass_request(coverage=self.COVER_60), source)
        assert ids(outcome) == ["a", "b"]

    async def test_a_pass_that_covers_too_little_falls_together(self) -> None:
        source = Source([
            scene("a", 0, "d1", west=9.0, east=10.2),
            scene("b", 0.5, "d1", west=10.2, east=10.4),
        ])
        outcome = await judged(pass_request(coverage=self.COVER_60), source)
        assert outcome.items == []

    async def test_per_scene_each_outline_decides_alone(self) -> None:
        """Gegenprobe: the same two scenes judged one by one, neither meets "at least 60"; and one that does is kept."""
        items = [
            scene("a", 0, "d1", west=9.0, east=10.45),
            scene("b", 0.5, "d1", west=10.6, east=12.0),
            scene("c", 1, "d1", west=9.0, east=12.0),
        ]
        source = Source(items)
        request = read_aoi_request(
            "s2", {}, datetime_value=None, bbox=None, intersects=AOI_SQUARE, earthx_aoi=None, coverage=self.COVER_60
        )

        async def no_measure(item: Mapping[str, Any]) -> SceneMeasure:
            raise AssertionError("the coverage reads no pixel")

        outcome = await run_filter(request, fetch_page=source.fetch, measure=no_measure, limit=10, token=None)
        assert [item["id"] for item in outcome.items] == ["c"]
        assert outcome.summary() == {"checked": 3, "found": 1, "unreadable": 0, "limit_reached": False}

    async def test_it_needs_no_date_range(self) -> None:
        request = read_aoi_request(
            "s2", {}, datetime_value=None, bbox=None, intersects=AOI_SQUARE, earthx_aoi=None, coverage=self.COVER_60
        )
        assert request.coverage == self.COVER_60 and not request.conditions

    async def test_a_measure_inside_the_aoi_still_needs_one(self) -> None:
        from earthx.catalog.search_filters import InvalidFilter

        with pytest.raises(InvalidFilter, match="date range"):
            read_aoi_request(
                "s2", {AoiMeasure.CLOUD_SHARE: RangeCondition(None, 5.0)}, datetime_value=None, bbox=None,
                intersects=AOI_SQUARE, earthx_aoi=None, coverage=self.COVER_60,
            )

    async def test_the_coverage_needs_an_area(self) -> None:
        from earthx.catalog.search_filters import InvalidFilter

        with pytest.raises(InvalidFilter, match="area"):
            read_aoi_request(
                "s2", {}, datetime_value=None, bbox=None, intersects=None, earthx_aoi=None, coverage=self.COVER_60
            )

    async def test_the_coverage_is_judged_before_any_pixel_is_read(self) -> None:
        """A pass that fails the coverage is not measured: the reading is the expensive part."""
        source = Source([scene("a", 0, "d1", west=20.0, east=21.0, **{CLOUD: 1.0})])
        request = pass_request(coverage=self.COVER_60, measures={AoiMeasure.CLOUD_SHARE: RangeCondition(None, 50.0)})
        outcome = await judged(request, source)  # `never_measure` would raise
        assert outcome.items == []


class TestEveryMeasureInsideTheAoiWorksPerPassAndPerScene:
    """The share of each class, counted over the merged pixels of a pass (the class pixels of the measure)."""

    def counts(self, classes: dict[int, int], data: int = 1000) -> SceneMeasure:
        return SceneMeasure(
            sum(n for c, n in classes.items() if c in {8, 9, 10}), data, 100.0, 80.0, class_pixels=classes
        )

    @pytest.mark.parametrize("measure", list(AoiMeasure), ids=lambda m: m.name)
    async def test_per_pass(self, measure: AoiMeasure) -> None:
        classes = {1: 100, 3: 100, 4: 100, 5: 100, 6: 100, 8: 100, 9: 100, 10: 100, 11: 100, 0: 0}
        read = self.counts({c: n for c, n in classes.items() if n}, data=900)
        value = read.value_of(measure, SHARES)
        assert value is not None
        source = Source([scene("a", 0, "d1"), scene("b", 0.5, "d1", west=11.0, east=12.0)])

        async def measure_pass(items: Sequence[dict[str, Any]]) -> SceneMeasure:
            return read

        holds = pass_request(measures={measure: RangeCondition(value, value)})
        misses = pass_request(measures={measure: RangeCondition(value + 0.2, None) if value < 99.8 else RangeCondition(None, value - 0.2)})
        assert ids(await judged(holds, source, measure=measure_pass)) == ["a", "b"]
        assert (await judged(misses, source, measure=measure_pass)).items == []

    @pytest.mark.parametrize("measure", list(AoiMeasure), ids=lambda m: m.name)
    async def test_per_scene(self, measure: AoiMeasure) -> None:
        read = self.counts({1: 100, 3: 100, 4: 100, 5: 100, 6: 100, 8: 100, 9: 100, 10: 100, 11: 100}, data=900)
        value = read.value_of(measure, SHARES)
        assert value is not None
        source = Source([scene("a", 0, "d1")])

        async def measure_scene(item: Mapping[str, Any]) -> SceneMeasure:
            return read

        def request(low: float | None, high: float | None) -> AoiFilterRequest:
            return read_aoi_request(
                "s2", {measure: RangeCondition(low, high)}, datetime_value=PERIOD, bbox=None, intersects=AOI_SQUARE,
                earthx_aoi=None, share_classes=SHARES,
            )

        kept = await run_filter(request(value, value), fetch_page=source.fetch, measure=measure_scene, limit=5, token=None)
        dropped = await run_filter(request(value + 0.2, None) if value < 99.8 else request(None, value - 0.2), fetch_page=source.fetch, measure=measure_scene, limit=5, token=None)
        assert [item["id"] for item in kept.items] == ["a"] and dropped.items == []

    def test_a_share_is_counted_over_the_classes_of_the_registry(self) -> None:
        read = self.counts({10: 50, 8: 50, 4: 100}, data=400)
        assert read.value_of(AoiMeasure.CIRRUS_SHARE, SHARES) == 12.5  # class 10 only
        assert read.value_of(AoiMeasure.CLOUD_SHARE, SHARES) == 25.0  # 8, 9, 10
        assert read.value_of(AoiMeasure.VEGETATION_SHARE, SHARES) == 25.0
        assert read.value_of(AoiMeasure.SHADOW_SHARE, SHARES) == 0.0

    def test_no_valid_pixel_has_no_share_but_all_the_aoi_is_no_data(self) -> None:
        read = self.counts({}, data=0)
        assert read.value_of(AoiMeasure.WATER_SHARE, SHARES) is None
        assert read.value_of(AoiMeasure.NODATA_SHARE, SHARES) == 100.0

    def test_a_measure_the_dataset_gives_no_classes_has_no_value(self) -> None:
        assert self.counts({4: 10}, data=10).value_of(AoiMeasure.WATER_SHARE, {}) is None

    async def test_a_pass_that_cannot_be_read_is_counted_and_dropped(self) -> None:
        source = Source([scene("a", 0, "d1"), scene("b", 0.5, "d1", west=11.0, east=12.0)])

        async def unreadable(items: Sequence[dict[str, Any]]) -> None:
            return None

        outcome = await judged(pass_request(measures={AoiMeasure.WATER_SHARE: RangeCondition(None, 50.0)}), source, measure=unreadable)
        assert outcome.items == [] and outcome.summary()["unreadable"] == 2


class TestTheClusters:
    async def test_a_pass_across_two_pages_of_the_source_is_judged_whole(self) -> None:
        source = Source(
            [scene(f"s{n}", n, "d1", west=10.0 + n, east=11.0 + n, **{CLOUD: 10.0 if n else 30.0}) for n in range(4)],
            size=2,
        )
        outcome = await judged(pass_request((CLOUD, RangeCondition(None, 16.0))), source)
        assert len(outcome.items) == 4, "four scenes at 30, 10, 10, 10 percent make 15 %"
        assert source.asked == [None, "2"]

    async def test_scenes_of_another_pass_between_the_scenes_of_one_stay_apart(self) -> None:
        source = Source([
            scene("a1", 0, "d1", west=10.0, east=11.0, **{CLOUD: 5.0}),
            scene("x", 1, "d2", west=10.0, east=11.0, **{CLOUD: 90.0}),
            scene("a2", 2, "d1", west=11.0, east=12.0, **{CLOUD: 5.0}),
        ])
        outcome = await judged(pass_request(CLOUD_AT_MOST_20), source)
        assert ids(outcome) == ["a1", "a2"]

    async def test_scenes_further_apart_than_the_gap_are_two_clusters_and_two_passes(self) -> None:
        late = CLUSTER_GAP_S / 60 + 1
        source = Source([
            scene("a", 0, "d1", **{CLOUD: 5.0}),
            scene("b", late, "d1", west=11.0, east=12.0, **{CLOUD: 90.0}),
        ])
        outcome = await judged(pass_request(CLOUD_AT_MOST_20), source)
        assert ids(outcome) == ["a"], "the late scene is a pass of its own"

    async def test_the_response_ends_between_clusters_and_the_next_goes_on(self) -> None:
        items = [scene(f"p{p}-{k}", p * 120 + k, f"d{p}", west=10.0 + k, east=11.0 + k, **{CLOUD: 5.0}) for p in range(6) for k in range(2)]
        source = Source(items, size=5)
        kept: list[str] = []
        token = None
        responses = 0
        while True:
            outcome = await judged(pass_request(CLOUD_AT_MOST_20), source, limit=4, token=token)
            kept += [item["id"] for item in outcome.items]
            responses += 1
            token = outcome.next_token
            if token is None:
                break
        assert sorted(kept) == sorted(item["id"] for item in items), "none missed"
        assert len(kept) == len(set(kept)), "none repeated"
        assert responses > 1

    async def test_the_limit_never_cuts_a_pass(self) -> None:
        source = Source([scene(f"s{k}", k, "d1", west=10.0 + k, east=11.0 + k, **{CLOUD: 5.0}) for k in range(5)])
        outcome = await judged(pass_request(CLOUD_AT_MOST_20), source, limit=2)
        assert len(outcome.items) == 5

    async def test_a_cluster_is_cut_at_the_most_scenes_of_one(self) -> None:
        source = Source(
            [scene(f"s{k:03d}", k * 0.05, "d1", west=10.0, east=11.0, **{CLOUD: 5.0}) for k in range(MAX_CLUSTER + 20)],
            size=MAX_CLUSTER + 20,
        )
        first = await judged(pass_request(CLOUD_AT_MOST_20), source, limit=1000)
        assert first.summary()["checked"] == MAX_CLUSTER
        assert first.next_token is not None

    async def test_the_marker_belongs_to_the_search_that_made_it(self) -> None:
        source = Source([scene(f"p{p}", p * 120, f"d{p}", **{CLOUD: 5.0}) for p in range(4)])
        first = await judged(pass_request(CLOUD_AT_MOST_20), source, limit=1, binding="a")
        assert first.next_token is not None
        with pytest.raises(InvalidQuery, match="different search"):
            await judged(pass_request(CLOUD_AT_MOST_20), source, token=first.next_token, binding="b")
        other = pass_request((CLOUD, RangeCondition(None, 30.0)))
        with pytest.raises(InvalidQuery, match="different search"):
            await judged(other, source, token=first.next_token, binding="a")

    async def test_the_marker_of_the_judged_search_is_not_the_scene_search_s(self) -> None:
        source = Source([scene(f"p{p}", p * 120, f"d{p}", **{CLOUD: 5.0}) for p in range(4)])
        first = await judged(pass_request(CLOUD_AT_MOST_20), source, limit=1)
        assert decode_cursor(first.next_token, _key(pass_request(CLOUD_AT_MOST_20))) == Cursor(None, 1, 1, 1, 0)


def _key(request: AoiFilterRequest) -> str:
    import hashlib

    return hashlib.sha256((request.key + "").encode("ascii")).hexdigest()


class TestTheTime:
    async def test_a_cluster_that_is_not_judged_in_time_is_left_for_the_next_response(self) -> None:
        release = asyncio.Event()
        calls = 0

        async def slow(items: Sequence[dict[str, Any]]) -> SceneMeasure:
            nonlocal calls
            calls += 1
            await release.wait()
            return SceneMeasure(0, 100, 100.0, 80.0, class_pixels={4: 100})

        source = Source([scene("a", 0, "d1"), scene("b", 0.5, "d1", west=11.0, east=12.0)])
        request = pass_request(measures={AoiMeasure.VEGETATION_SHARE: RangeCondition(50.0, None)})
        old = filter_module.RESPONSE_SECONDS
        filter_module.RESPONSE_SECONDS = 0.05
        try:
            import earthx.api.pass_filter as pass_module

            pass_module.RESPONSE_SECONDS = 0.05
            first = await run_pass_filter(
                request, fetch_page=source.fetch, group_of=KEY_OF, order_of=order_by_id, measure_pass=slow,
                limit=10, token=None,
            )
        finally:
            filter_module.RESPONSE_SECONDS = old
            pass_module.RESPONSE_SECONDS = old
        assert first.items == [] and first.summary()["checked"] == 0
        assert first.next_token is not None, "the cluster is still to come"
        release.set()
        await filter_module.settle()
        assert calls == 1


class TestTheRequest:
    def test_a_search_per_pass_over_properties_alone_needs_neither_area_nor_dates(self) -> None:
        request = pass_request(CLOUD_AT_MOST_20, aoi=None)
        assert request.aoi is None and request.evaluate_pass and request.scene_conditions

    def test_a_dataset_that_needs_no_area_leaves_earthx_aoi_to_the_others(self) -> None:
        """In a search over several datasets another one may need the AOI beside the box (review of DS-03c)."""
        request = read_aoi_request(
            "s2", {}, datetime_value=None, bbox=(9, 9, 12, 12), intersects=None, earthx_aoi=AOI_SQUARE,
            evaluate_pass=True, scene_conditions={CLOUD: RangeCondition(None, 5.0)},
        )
        assert request.aoi is None

    def test_nothing_to_judge_is_a_value_error(self) -> None:
        with pytest.raises(ValueError):
            read_aoi_request("s2", {}, datetime_value=None, bbox=None, intersects=None, earthx_aoi=None, evaluate_pass=True)

    def test_the_key_tells_per_pass_from_per_scene_and_the_coverage_from_none(self) -> None:
        scene_request = read_aoi_request(
            "s2", {AoiMeasure.CLOUD_SHARE: RangeCondition(None, 5.0)}, datetime_value=PERIOD, bbox=None,
            intersects=AOI_SQUARE, earthx_aoi=None,
        )
        by_pass = pass_request(measures={AoiMeasure.CLOUD_SHARE: RangeCondition(None, 5.0)})
        with_coverage = read_aoi_request(
            "s2", {AoiMeasure.CLOUD_SHARE: RangeCondition(None, 5.0)}, datetime_value=PERIOD, bbox=None,
            intersects=AOI_SQUARE, earthx_aoi=None, coverage=RangeCondition(50.0, None),
        )
        assert len({scene_request.key, by_pass.key, with_coverage.key}) == 3

    def test_the_overpass_key_stands_apart_for_an_item_without_its_parts(self) -> None:
        assert KEY_OF({"id": "x", "properties": {}}) == ("item", "x")
        assert KEY_OF(scene("a", 0, "d1")) == ("2024-05-10", "d1")

    def test_the_registry_fields_the_loop_reads(self) -> None:
        assert isinstance(FILTERS[CLOUD], SearchFilter) and replace(FILTERS[CLOUD]).area_based
