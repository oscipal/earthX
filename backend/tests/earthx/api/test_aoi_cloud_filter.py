"""DS-03a2 (plan §6.5, §6.9, §6.13): the filter "Within AOI", its pieces without a database or a source.

The loop runs on a source and a measure made of plain functions, with a clock the test moves; the measurer on a
cache of a dict and a reader that returns counts. The real counting of a raster is DS-03a1's tests'.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import threading
import time
from collections.abc import Mapping
from typing import Any

import pytest

from earthx.access.aoi_clouds import AoiClouds
from earthx.adapters import InvalidQuery, ItemPage
from earthx.api import aoi_cloud_filter as module
from earthx.api.aoi_cloud_filter import (
    CONCURRENT_READS,
    PAGE_SIZE,
    RESPONSE_SCENES,
    SEARCH_SCENES,
    AoiFilterRequest,
    AoiMeasurer,
    Cursor,
    SceneMeasure,
    decode_cursor,
    encode_cursor,
    hide_gdal_addresses,
    read_aoi_request,
    run_filter,
)
from earthx.catalog.datasets import SENTINEL_2_L2A
from earthx.catalog.search_filters import InvalidFilter, RangeCondition
from earthx.gateway import Policy, ReadSlots

pytestmark = pytest.mark.anyio

PERIOD = "2024-05-01T00:00:00Z/2024-06-01T00:00:00Z"
SQUARE = {"type": "Polygon", "coordinates": [[[10.0, 47.0], [10.2, 47.0], [10.2, 47.2], [10.0, 47.2], [10.0, 47.0]]]}
TWO_SQUARES = {
    "type": "MultiPolygon",
    "coordinates": [
        [[[10.0, 47.0], [10.1, 47.0], [10.1, 47.1], [10.0, 47.1], [10.0, 47.0]]],
        [[[10.5, 47.5], [10.6, 47.5], [10.6, 47.6], [10.5, 47.6], [10.5, 47.5]]],
    ],
}
BBOX = (9.0, 46.0, 11.0, 48.0)


def request_for(condition: RangeCondition | None = None, aoi: Mapping[str, Any] = SQUARE) -> AoiFilterRequest:
    return read_aoi_request(
        "s2",
        condition or RangeCondition(None, 20.0),
        datetime_value=PERIOD,
        bbox=None,
        intersects=aoi,
        earthx_aoi=None,
    )


class TestReadingTheRequest:
    def test_an_intersects_polygon_is_the_area(self) -> None:
        assert request_for().aoi == SQUARE

    def test_a_multipolygon_is_the_area(self) -> None:
        assert request_for(aoi=TWO_SQUARES).aoi["type"] == "MultiPolygon"

    def test_a_bbox_is_the_area_as_a_polygon(self) -> None:
        read = read_aoi_request(
            "s2", RangeCondition(None, 5.0), datetime_value=PERIOD, bbox=BBOX, intersects=None, earthx_aoi=None
        )
        assert read.aoi["type"] == "Polygon"
        assert {tuple(position) for position in read.aoi["coordinates"][0]} == {
            (9.0, 46.0), (11.0, 46.0), (11.0, 48.0), (9.0, 48.0)
        }

    def test_a_bbox_across_the_antimeridian_is_two_parts(self) -> None:
        read = read_aoi_request(
            "s2", RangeCondition(None, 5.0), datetime_value=PERIOD, bbox=(179.0, 10.0, -179.0, 11.0),
            intersects=None, earthx_aoi=None,
        )
        assert read.aoi["type"] == "MultiPolygon"

    def test_earthx_aoi_inside_the_bbox_is_what_is_measured(self) -> None:
        read = read_aoi_request(
            "s2", RangeCondition(None, 5.0), datetime_value=PERIOD, bbox=BBOX, intersects=None, earthx_aoi=SQUARE
        )
        assert read.aoi == SQUARE

    def test_earthx_aoi_with_twenty_thousand_positions(self) -> None:
        """A closed ring of exactly the cap: the first corner, 19 998 on a convex arc, the last corner, the first again."""
        arc = [[10.0 + 0.2 * (i + 1) / 19_999, 47.0 + 0.2 * ((i + 1) / 19_999) ** 2] for i in range(19_997)]
        polygon = {"type": "Polygon", "coordinates": [[[10.0, 47.0], *arc, [10.2, 47.2], [10.0, 47.0]]]}
        assert sum(len(ring) for ring in polygon["coordinates"]) == 20_000
        read = read_aoi_request(
            "s2", RangeCondition(None, 5.0), datetime_value=PERIOD, bbox=BBOX, intersects=None, earthx_aoi=polygon
        )
        assert read.aoi["type"] == "Polygon"

    @pytest.mark.parametrize(
        ("changes", "message"),
        [
            ({"datetime_value": None}, "date range with a start and an end"),
            ({"datetime_value": "2024-05-01T00:00:00Z/.."}, "date range with a start and an end"),
            ({"datetime_value": "../2024-05-01T00:00:00Z"}, "date range with a start and an end"),
            ({"datetime_value": "2024-05-01T00:00:00Z"}, "date range with a start and an end"),
            ({"intersects": None}, "needs an area"),
            ({"intersects": {"type": "Point", "coordinates": [10.0, 47.0]}}, "needs an area"),
            ({"intersects": {"type": "LineString", "coordinates": [[10.0, 47.0], [10.1, 47.1]]}}, "needs an area"),
            ({"intersects": {"type": "GeometryCollection", "geometries": []}}, "needs an area"),
            ({"intersects": {"type": "Polygon", "coordinates": "x"}}, "needs an area"),
            ({"intersects": {"type": "Polygon", "coordinates": [[[0, 0], [1, 1], [1, 0], [0, 1], [0, 0]]]}}, "valid polygon"),
            ({"intersects": {"type": "Polygon", "coordinates": [[[10, 47], [10, 47], [10, 47], [10, 47]]]}}, "valid polygon"),
            ({"intersects": {"type": "Polygon", "coordinates": [[[190, 47], [191, 47], [191, 48], [190, 47]]]}}, "valid polygon"),
            ({"intersects": {"type": "Polygon", "coordinates": [[["a", 47], [10, 47], [10, 48], ["a", 47]]]}}, "valid polygon"),
            ({"earthx_aoi": SQUARE}, "not with intersects"),
        ],
    )
    def test_a_request_that_cannot_be_measured(self, changes: dict[str, Any], message: str) -> None:
        arguments: dict[str, Any] = {"datetime_value": PERIOD, "bbox": None, "intersects": SQUARE, "earthx_aoi": None}
        with pytest.raises(InvalidFilter, match=message) as caught:
            read_aoi_request("s2", RangeCondition(None, 5.0), **{**arguments, **changes})
        for value in ("10.0", "47.0", "190"):
            assert value not in str(caught.value)

    @pytest.mark.parametrize(
        ("bbox", "earthx_aoi", "message"),
        [
            (None, SQUARE, "goes with the bbox"),
            ((20.0, 46.0, 21.0, 48.0), SQUARE, "lies outside the bbox"),
            ((10.05, 47.05, 10.1, 47.1), SQUARE, "lies outside the bbox"),
            (BBOX, {"type": "Point", "coordinates": [10.0, 47.0]}, "needs an area"),
            ((9.0, 46.0, 11.0), None, "four numbers"),
            ((9.0, 48.0, 11.0, 46.0), None, "upside down"),
            ((9.0, 46.0, 9.0, 48.0), None, "no area"),
        ],
    )
    def test_earthx_aoi_and_the_bbox(self, bbox: Any, earthx_aoi: Any, message: str) -> None:
        with pytest.raises(InvalidFilter, match=message):
            read_aoi_request(
                "s2", RangeCondition(None, 5.0), datetime_value=PERIOD, bbox=bbox, intersects=None, earthx_aoi=earthx_aoi
            )

    def test_more_than_twenty_thousand_positions(self) -> None:
        ring = [[10.0 + i * 1e-6, 47.0] for i in range(20_001)]
        with pytest.raises(InvalidFilter, match="more than 20000 positions"):
            read_aoi_request(
                "s2", RangeCondition(None, 5.0), datetime_value=PERIOD, bbox=BBOX, intersects=None,
                earthx_aoi={"type": "Polygon", "coordinates": [[*ring, [10.0, 47.0]]]},
            )

    def test_the_key_binds_collection_range_and_area_and_holds_no_coordinate(self) -> None:
        base = request_for()
        assert request_for().key == base.key
        assert request_for(RangeCondition(None, 21.0)).key != base.key
        assert request_for(aoi=TWO_SQUARES).key != base.key
        other = read_aoi_request(
            "other", RangeCondition(None, 20.0), datetime_value=PERIOD, bbox=None, intersects=SQUARE, earthx_aoi=None
        )
        assert other.key != base.key
        assert "10.2" not in base.key and "47" not in base.key


class TestThePageMarker:
    KEY = "k" * 64

    def test_it_reads_back_what_it_carries(self) -> None:
        cursor = Cursor(page="marker", offset=17, checked=120, found=9, unreadable=2)
        assert decode_cursor(encode_cursor(self.KEY, cursor), self.KEY) == cursor

    def test_a_first_page_has_no_marker_of_the_source(self) -> None:
        cursor = Cursor(page=None, offset=3, checked=3, found=1, unreadable=0)
        assert decode_cursor(encode_cursor(self.KEY, cursor), self.KEY) == cursor

    def test_it_holds_no_coordinate_and_not_the_key_of_the_cache(self) -> None:
        request = request_for()
        token = encode_cursor(request.key, Cursor("m", 1, 1, 1, 0))
        text = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4)).decode()
        assert "47" not in text and "coordinates" not in text

    def test_another_search_is_refused(self) -> None:
        token = encode_cursor(self.KEY, Cursor())
        with pytest.raises(InvalidQuery, match="different search"):
            decode_cursor(token, "o" * 64)

    @pytest.mark.parametrize(
        "token",
        [
            "!!!",
            base64.urlsafe_b64encode(b"[]").decode(),
            base64.urlsafe_b64encode(json.dumps({"k": "mixed", "v": 1}).encode()).decode(),
            base64.urlsafe_b64encode(json.dumps({"k": "aoi", "v": 9}).encode()).decode(),
        ],
    )
    def test_what_is_not_a_marker_of_this_filter(self, token: str) -> None:
        with pytest.raises(InvalidQuery):
            decode_cursor(token, self.KEY)

    @pytest.mark.parametrize(
        "changes",
        [
            {"i": -1},
            {"i": PAGE_SIZE},
            {"i": "3"},
            {"c": SEARCH_SCENES},
            {"c": True},
            {"f": 5, "c": 3},
            {"u": 3, "c": 3, "f": 1},
            {"p": 7},
        ],
    )
    def test_a_marker_that_names_a_place_the_search_does_not_reach(self, changes: dict[str, Any]) -> None:
        payload = {"v": 1, "k": "aoi", "h": self.KEY, "p": None, "i": 0, "c": 1, "f": 0, "u": 0, **changes}
        token = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
        with pytest.raises(InvalidQuery):
            decode_cursor(token, self.KEY)


class TestSceneMeasure:
    def test_the_share_is_of_the_valid_pixels_in_one_decimal(self) -> None:
        assert SceneMeasure(1, 3, 100.0, 20.0).cloud_percent == 33.3

    def test_no_valid_pixel_is_no_value(self) -> None:
        assert SceneMeasure(0, 0, 0.0, 20.0).cloud_percent is None

    def test_the_counts_of_a_reading(self) -> None:
        measure = SceneMeasure.of(AoiClouds(cloud_pixels=25, data_pixels=50, aoi_pixels=100, resolution=80.0))
        assert measure.as_measure() == {"data_percent": 50.0, "cloud_pixels": 25, "data_pixels": 50, "resolution": 80.0}
        assert not measure.cached

    def test_a_stored_entry_reads_back_as_cached(self) -> None:
        stored = SceneMeasure.stored({"data_percent": 50.0, "cloud_pixels": 25, "data_pixels": 50, "resolution": 80.0})
        assert stored == SceneMeasure(25, 50, 50.0, 80.0, cached=True)

    @pytest.mark.parametrize(
        "value",
        [
            None,
            [],
            {},
            {"data_percent": 50.0, "cloud_pixels": 51, "data_pixels": 50, "resolution": 80.0},
            {"data_percent": 50.0, "cloud_pixels": -1, "data_pixels": 50, "resolution": 80.0},
            {"data_percent": 50.0, "cloud_pixels": "5", "data_pixels": 50, "resolution": 80.0},
            {"data_percent": float("nan"), "cloud_pixels": 5, "data_pixels": 50, "resolution": 80.0},
            {"data_percent": 50.0, "cloud_pixels": 5, "data_pixels": 50, "resolution": None},
        ],
    )
    def test_an_entry_that_is_none_counts_as_a_miss(self, value: Any) -> None:
        assert SceneMeasure.stored(value) is None


# -- the loop ---------------------------------------------------------------------------------------------------


class Source:
    """A source of ``total`` scenes in pages: scene ``n`` has the share ``shares(n)``; remembers what it was asked."""

    def __init__(self, total: int) -> None:
        self.total = total
        self.asked: list[str | None] = []

    def item(self, number: int) -> dict[str, Any]:
        return {"id": f"S2_{number:04d}", "properties": {"datetime": f"2024-05-{1 + number % 28:02d}T10:00:00Z"}}

    async def fetch(self, marker: str | None) -> ItemPage:
        self.asked.append(marker)
        start = 0 if marker is None else int(marker)
        end = min(start + PAGE_SIZE, self.total)
        return ItemPage(
            items=tuple(self.item(number) for number in range(start, end)),
            matched=None,
            next_page_token=str(end) if end < self.total else None,
            from_cache=False,
        )


def number_of(item: Mapping[str, Any]) -> int:
    return int(item["id"].removeprefix("S2_"))


class Measures:
    """``measure(item)`` from a function of the scene's number; counts the scenes it was asked to measure."""

    def __init__(self, percent_of, *, cached=lambda number: False, clock: "Clock | None" = None, cost: float = 0.0):
        self.percent_of = percent_of
        self.cached = cached
        self.clock = clock
        self.cost = cost
        self.measured: list[int] = []

    async def __call__(self, item: Mapping[str, Any]) -> SceneMeasure | None:
        number = number_of(item)
        self.measured.append(number)
        if self.clock is not None:
            self.clock.now += self.cost
        percent = self.percent_of(number)
        if percent is None:
            return None
        return SceneMeasure(round(percent * 10), 1000, 100.0, 80.0, cached=self.cached(number))


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


async def respond(source: Source, measures: Measures, *, limit: int = 10, token: str | None = None, condition=None, **extra):
    try:
        return await run_filter(
            request_for(condition or RangeCondition(None, 20.0)),
            fetch_page=source.fetch,
            measure=measures,
            limit=limit,
            token=token,
            **extra,
        )
    finally:
        await module.settle()  # scenes measured ahead end with the response, not after the test


def every_fourth(number: int) -> float:
    """A scene in four lies in the range of 20 % or less."""
    return 5.0 if number % 4 == 0 else 60.0


def numbers(outcome) -> list[int]:
    return [number_of(item) for item in outcome.items]


_STANDARD_ATTRIBUTES = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {"message", "taskName"}


class TestTheLoop:
    async def test_it_keeps_the_scenes_in_the_range_each_with_its_share(self) -> None:
        outcome = await respond(Source(40), Measures(every_fourth), limit=100)
        assert numbers(outcome) == list(range(0, 40, 4))
        first = outcome.items[0]["properties"]
        assert first["earthx:aoi_cloud_cover"] == 5.0
        assert first["earthx:aoi_measure"] == {"data_percent": 100.0, "cloud_pixels": 50, "data_pixels": 1000, "resolution": 80.0}
        assert first["datetime"].startswith("2024-05"), "the properties of the source stay"
        assert outcome.summary() == {"checked": 40, "found": 10, "unreadable": 0, "limit_reached": False}
        assert outcome.next_token is None

    async def test_it_does_not_change_the_item_of_the_source(self) -> None:
        source = Source(4)
        page = await source.fetch(None)
        await respond(source, Measures(lambda n: 1.0), limit=10)
        assert "earthx:aoi_cloud_cover" not in page.items[0]["properties"]

    async def test_both_ends_of_the_range_count_as_shown(self) -> None:
        outcome = await respond(
            Source(3), Measures({0: 9.9, 1: 10.0, 2: 20.0}.get), condition=RangeCondition(10.0, 20.0), limit=10
        )
        assert numbers(outcome) == [1, 2]

    async def test_it_stops_at_limit_and_goes_on_behind_the_last_scene_it_checked(self) -> None:
        source = Source(60)
        outcome = await respond(source, Measures(every_fourth), limit=3)
        assert numbers(outcome) == [0, 4, 8]
        assert outcome.summary() == {"checked": 9, "found": 3, "unreadable": 0, "limit_reached": False}
        assert decode_cursor(outcome.next_token, request_for().key) == Cursor(None, 9, 9, 3, 0)

    async def test_the_next_response_misses_none_and_repeats_none(self) -> None:
        source = Source(300)
        measures = Measures(every_fourth)
        kept: list[int] = []
        token = None
        responses = 0
        while True:
            outcome = await respond(source, measures, limit=7, token=token)
            kept += numbers(outcome)
            responses += 1
            token = outcome.next_token
            if token is None:
                break
        assert kept == list(range(0, 300, 4))
        assert measures.measured.count(0) == 1 and sorted(set(measures.measured)) == list(range(300))
        assert responses > 3

    async def test_the_counts_run_on_over_the_responses(self) -> None:
        source, measures = Source(300), Measures(every_fourth)
        first = await respond(source, measures, limit=5)
        second = await respond(source, measures, limit=5, token=first.next_token)
        assert first.summary()["found"] == 5 and second.summary()["found"] == 10
        assert second.summary()["checked"] == 37  # scenes 0..36: the tenth hit is scene 36
        assert numbers(second) == [20, 24, 28, 32, 36]

    async def test_a_marker_in_the_middle_of_a_page_fetches_that_page_again_and_goes_on_inside_it(self) -> None:
        source, measures = Source(300), Measures(lambda n: 90.0)
        first = await respond(source, measures, limit=100)
        assert decode_cursor(first.next_token, request_for().key) == Cursor("100", 0, 100, 0, 0)  # page end: next page
        source.asked.clear()
        measures.measured.clear()
        second = await respond(source, Measures(every_fourth), limit=3, token=encode_cursor(request_for().key, Cursor("100", 37, 137, 0, 0)))
        assert source.asked == ["100"]
        assert numbers(second) == [140, 144, 148]

    async def test_a_hundred_scenes_end_a_response(self) -> None:
        source = Source(1000)
        outcome = await respond(source, Measures(lambda n: 90.0), limit=100)
        assert outcome.items == []
        assert outcome.summary() == {"checked": RESPONSE_SCENES, "found": 0, "unreadable": 0, "limit_reached": False}
        assert decode_cursor(outcome.next_token, request_for().key).checked == RESPONSE_SCENES

    async def test_eight_seconds_of_the_clock_end_a_response(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(module, "CONCURRENT_READS", 1)  # one at a time: each scene costs its 3 s in turn
        clock = Clock()
        measures = Measures(lambda n: 90.0, clock=clock, cost=3.0)
        outcome = await respond(Source(1000), measures, limit=100, clock=clock)
        assert outcome.summary()["checked"] == 3  # 3 s each: the fourth would start at 9 s
        assert outcome.next_token is not None
        assert decode_cursor(outcome.next_token, request_for().key).offset == 3

    async def test_five_hundred_scenes_end_the_search_with_no_marker(self) -> None:
        source, measures = Source(2000), Measures(lambda n: 90.0)
        token, checked = None, []
        for _ in range(6):
            outcome = await respond(source, measures, limit=100, token=token)
            token = outcome.next_token
            checked.append(outcome.summary()["checked"])
            if token is None:
                break
        assert checked == [100, 200, 300, 400, 500]
        assert outcome.summary()["limit_reached"] is True
        assert token is None
        assert len(measures.measured) == SEARCH_SCENES

    async def test_a_source_that_ends_at_five_hundred_has_reached_no_limit(self) -> None:
        source, measures = Source(500), Measures(lambda n: 90.0)
        token = None
        while True:
            outcome = await respond(source, measures, limit=100, token=token)
            token = outcome.next_token
            if token is None:
                break
        assert outcome.summary() == {"checked": 500, "found": 0, "unreadable": 0, "limit_reached": False}

    async def test_the_end_of_the_source_gives_no_marker(self) -> None:
        outcome = await respond(Source(5), Measures(lambda n: 1.0), limit=100)
        assert outcome.next_token is None and len(outcome.items) == 5

    async def test_an_empty_source(self) -> None:
        outcome = await respond(Source(0), Measures(lambda n: 1.0))
        assert outcome.items == [] and outcome.next_token is None
        assert outcome.summary() == {"checked": 0, "found": 0, "unreadable": 0, "limit_reached": False}

    async def test_a_scene_that_cannot_be_read_is_counted_and_not_returned(self) -> None:
        outcome = await respond(Source(10), Measures(lambda n: None if n in (2, 5) else 1.0), limit=100)
        assert numbers(outcome) == [0, 1, 3, 4, 6, 7, 8, 9]
        assert outcome.summary() == {"checked": 10, "found": 8, "unreadable": 2, "limit_reached": False}

    async def test_a_scene_without_a_valid_pixel_in_the_aoi_falls_out_unseen(self) -> None:
        class NoData(Measures):
            async def __call__(self, item):
                return SceneMeasure(0, 0, 0.0, 80.0) if number_of(item) == 1 else await super().__call__(item)

        outcome = await respond(Source(3), NoData(lambda n: 1.0), limit=100)
        assert numbers(outcome) == [0, 2]
        assert outcome.summary() == {"checked": 3, "found": 2, "unreadable": 0, "limit_reached": False}

    async def test_a_marker_of_another_search_is_refused_before_anything_is_asked(self) -> None:
        source = Source(10)
        token = encode_cursor("o" * 64, Cursor())
        with pytest.raises(InvalidQuery):
            await respond(source, Measures(lambda n: 1.0), token=token)
        assert source.asked == []

    async def test_a_failing_source_page_fails_the_response(self) -> None:
        async def fetch(marker: str | None) -> ItemPage:
            raise RuntimeError("source down")

        with pytest.raises(RuntimeError):
            await run_filter(request_for(), fetch_page=fetch, measure=Measures(lambda n: 1.0), limit=1, token=None)

    async def test_several_scenes_are_measured_at_once_and_no_more_than_the_window(self) -> None:
        running = peak = 0

        async def measure(item: Mapping[str, Any]) -> SceneMeasure:
            nonlocal running, peak
            running += 1
            peak = max(peak, running)
            await asyncio.sleep(0.01)
            running -= 1
            return SceneMeasure(900, 1000, 100.0, 80.0)

        outcome = await run_filter(
            request_for(), fetch_page=Source(40).fetch, measure=measure, limit=100, token=None
        )
        await module.settle()
        assert outcome.summary()["checked"] == 40
        assert 1 < peak <= CONCURRENT_READS

    async def test_scenes_measured_beyond_the_limit_are_dropped_not_counted(self) -> None:
        measures = Measures(lambda n: 1.0)
        outcome = await respond(Source(50), measures, limit=2)
        assert numbers(outcome) == [0, 1]
        assert outcome.summary()["checked"] == 2
        assert decode_cursor(outcome.next_token, request_for().key).offset == 2

    async def test_one_log_line_per_response_without_the_area_or_a_name_of_a_scene(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.DEBUG):
            await respond(Source(12), Measures(every_fourth, cached=lambda n: n < 4), limit=100)
        lines = [record for record in caplog.records if record.getMessage() == "aoi cloud filter"]
        assert len(lines) == 1
        line = lines[0].__dict__
        assert (line["dataset"], line["checked"], line["found"], line["from_cache"], line["unreadable"]) == (
            "s2", 12, 3, 4, 0
        )
        assert line["limit_reached"] is False and line["levels"] == {"80.0": 12} and line["seconds"] >= 0
        extras = {key: value for key, value in line.items() if key not in _STANDARD_ATTRIBUTES}
        assert set(extras) == {"dataset", "checked", "found", "from_cache", "unreadable", "limit_reached", "levels", "seconds"}
        assert "S2_00" not in str(caplog.records) and "47.0" not in str(caplog.records)


# -- measuring a scene --------------------------------------------------------------------------------------------

HOST = SENTINEL_2_L2A.source.asset_hosts[0]
POLICY = Policy(allowed_hosts=frozenset({HOST}))


def public(host: str, port: int) -> tuple[str, ...]:
    return ("93.184.216.34",)


def scene(number: int = 1, *, href: str | None = None, assets: bool = True) -> dict[str, Any]:
    return {
        "id": f"S2_{number:04d}",
        "properties": {},
        "assets": {"scl": {"href": href or f"https://{HOST}/sentinel-s2-l2a-cogs/{number}/SCL.tif"}} if assets else {},
    }


class DictCache:
    def __init__(self) -> None:
        self.rows: dict[str, dict[str, Any]] = {}
        self.ttls: list[float] = []

    async def get(self, key: str) -> dict[str, Any] | None:
        return self.rows.get(key)

    async def set(self, key: str, value: dict[str, Any], *, dataset_id: str, ttl_s: float = 0) -> None:
        self.rows[key] = value
        self.ttls.append(ttl_s)


class BrokenCache:
    async def get(self, key: str) -> Any:
        raise RuntimeError(f"SELECT payload WHERE cache_key = '{key}'")

    async def set(self, key: str, value: Any, *, dataset_id: str, ttl_s: float = 0) -> None:
        raise RuntimeError(f"INSERT {key}")


def measurer(cache: Any = None, **overrides: Any) -> AoiMeasurer:
    resolver = overrides.pop("resolver", public)
    return AoiMeasurer(
        SENTINEL_2_L2A,
        SQUARE,
        policy=POLICY,
        resolver=resolver,
        gdal_options={"GDAL_HTTP_MULTIRANGE": "YES"},
        slots=overrides.pop("slots", ReadSlots(POLICY)),
        cache=cache,
    )


@pytest.fixture
def reads(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, frozenset[int]]]:
    """Replaces the reading of a raster; what it was asked is kept, the counts are 40 of 160 pixels."""
    seen: list[tuple[str, frozenset[int]]] = []

    def fake(path: Any, aoi: Any, classes: frozenset[int]) -> AoiClouds:
        seen.append((path.item_id, classes))
        return AoiClouds(cloud_pixels=40, data_pixels=160, aoi_pixels=200, resolution=80.0)

    monkeypatch.setattr(module, "measure_aoi_clouds", fake)
    return seen


class TestMeasuringAScene:
    async def test_it_reads_the_classification_with_the_classes_of_the_registry(self, reads: list) -> None:
        result = await measurer()(scene())
        assert result == SceneMeasure(40, 160, 80.0, 80.0, cached=False)
        assert reads == [("S2_0001", frozenset({8, 9, 10}))]

    async def test_the_second_time_it_comes_from_the_cache_for_seven_days(self, reads: list) -> None:
        cache = DictCache()
        first = await measurer(cache)(scene())
        second = await measurer(cache)(scene())
        assert not first.cached and second.cached and second.cloud_pixels == 40
        assert len(reads) == 1
        assert cache.ttls == [7 * 24 * 3600]
        (stored,) = cache.rows.values()
        assert stored == {"data_percent": 80.0, "cloud_pixels": 40, "data_pixels": 160, "resolution": 80.0}

    async def test_the_cache_key_is_the_scene_and_the_area(self, reads: list) -> None:
        cache = DictCache()
        await measurer(cache)(scene(1))
        await measurer(cache)(scene(2))
        assert len(cache.rows) == 2 and len(reads) == 2
        for key in cache.rows:
            assert len(key) == 64 and set(key) <= set("0123456789abcdef")

    async def test_an_entry_that_is_none_is_measured_again(self, reads: list) -> None:
        cache = DictCache()
        await measurer(cache)(scene())
        (key,) = cache.rows
        cache.rows[key] = {"cloud_pixels": 999, "data_pixels": 1}
        result = await measurer(cache)(scene())
        assert not result.cached and len(reads) == 2

    async def test_a_cache_that_fails_only_makes_it_slower_and_its_words_stay_out_of_the_log(
        self, reads: list, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.DEBUG):
            result = await measurer(BrokenCache())(scene())
        assert result.cloud_pixels == 40
        warnings = [record for record in caplog.records if record.levelno == logging.WARNING]
        assert [record.__dict__["error_type"] for record in warnings] == ["RuntimeError", "RuntimeError"]
        everything = " ".join(str(record.__dict__) for record in caplog.records)
        assert "SELECT" not in everything and "INSERT" not in everything and "cache_key" not in everything

    @pytest.mark.parametrize(
        "item",
        [
            scene(assets=False),
            scene(href="https://elsewhere.example.org/SCL.tif"),
            scene(href="http://" + HOST + "/SCL.tif"),
            {"properties": {}, "assets": {}},
        ],
    )
    async def test_a_scene_it_may_not_or_cannot_read_is_none(self, reads: list, item: dict[str, Any]) -> None:
        assert await measurer()(item) is None
        assert reads == []

    async def test_an_address_that_resolves_to_a_private_one_is_not_read(self, reads: list) -> None:
        result = await measurer(resolver=lambda host, port: ("10.0.0.5",))(scene())
        assert result is None and reads == []

    @pytest.mark.parametrize("error", [ValueError("position 10.0 47.0"), OSError("https://x"), RuntimeError])
    async def test_a_failing_read_is_none_unless_it_is_a_bug(
        self, monkeypatch: pytest.MonkeyPatch, error: Any
    ) -> None:
        from rasterio.errors import RasterioIOError

        def fail(path: Any, aoi: Any, classes: Any) -> AoiClouds:
            raise error

        monkeypatch.setattr(module, "measure_aoi_clouds", fail)
        if error is RuntimeError:
            with pytest.raises(RuntimeError):
                await measurer()(scene())
        else:
            assert await measurer()(scene()) is None
        monkeypatch.setattr(module, "measure_aoi_clouds", lambda *a: (_ for _ in ()).throw(RasterioIOError("x")))
        assert await measurer()(scene()) is None

    async def test_it_needs_a_dataset_with_a_classification(self) -> None:
        from tests.catalog.synthetic_zarr import SYNTHETIC_ZARR

        with pytest.raises(ValueError, match="classification"):
            AoiMeasurer(
                SYNTHETIC_ZARR, SQUARE, policy=POLICY, resolver=public, gdal_options={},
                slots=ReadSlots(POLICY), cache=None,
            )

    async def test_never_more_readers_at_once_than_the_policy_allows_even_for_two_searches(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        lock = threading.Lock()
        running = peak = 0

        def slow(path: Any, aoi: Any, classes: Any) -> AoiClouds:
            nonlocal running, peak
            with lock:
                running += 1
                peak = max(peak, running)
            time.sleep(0.03)
            with lock:
                running -= 1
            return AoiClouds(1, 2, 3, 80.0)

        monkeypatch.setattr(module, "measure_aoi_clouds", slow)
        slots = ReadSlots(POLICY)  # one per process, shared by the searches
        first, second = measurer(slots=slots), measurer(slots=slots)
        scenes = [scene(number) for number in range(1, 25)]
        await asyncio.gather(*(m(item) for m in (first, second) for item in scenes))
        assert 1 < peak <= POLICY.max_connections_per_host


class TestNoAddressInTheLogOfAFailedRead:
    async def test_gdals_line_with_the_address_is_dropped(self, caplog: pytest.LogCaptureFixture) -> None:
        import rasterio
        from rasterio.errors import RasterioIOError

        hide_gdal_addresses()
        hide_gdal_addresses()
        with caplog.at_level(logging.DEBUG):
            with pytest.raises(RasterioIOError), rasterio.Env():
                rasterio.open("/vsicurl/https://127.0.0.1:9/secret-scene/SCL.tif")
        everything = " ".join(record.getMessage() for record in caplog.records)
        assert "secret-scene" not in everything and "vsicurl" not in everything
