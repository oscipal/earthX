"""DS-03c (Otto, 05.11.2026, on #293): a scene or a pass is skipped as little as possible, and no response ends without progress.

A reading has its own time (8 s per scene, at most 30 s), is tried once more if it failed, and only then counts as skipped.
The time is checked in the thread that reads, the retry in the measurer, and the first scene of a response is waited for to
the end. The readings are replaced by functions that fail, wait or answer as the test says.
"""

from __future__ import annotations

import time
from typing import Any

import pytest
from rasterio.errors import RasterioIOError

from earthx.access.aoi_clouds import READ_DEADLINE, AoiClouds, ReadDeadlineExceeded
from earthx.access.outlines import AoiOutlines
from earthx.api import aoi_cloud_filter as module
from earthx.api import pass_filter
from earthx.api.aoi_cloud_filter import (
    ATTEMPTS,
    PASS_SECONDS_MAX,
    SCENE_SECONDS,
    SceneMeasure,
    read_seconds,
    run_filter,
)
from earthx.api.pass_filter import PassMeasurer
from earthx.catalog.search_filters import RangeCondition
from earthx.gateway import ReadSlots
from tests.catalog.entries import SENTINEL_2_L2A
from tests.earthx.api.test_aoi_cloud_filter import (
    POLICY,
    SQUARE,
    Clock,
    Measures,
    Source,
    measurer,
    public,
    request_for,
    scene,
)

pytestmark = pytest.mark.anyio

GOOD = AoiClouds(cloud_pixels=40, data_pixels=160, aoi_pixels=200, resolution=80.0)


class TestTheTimeAReadingHas:
    @pytest.mark.parametrize(("scenes", "seconds"), [(0, 8.0), (1, 8.0), (2, 16.0), (3, 24.0), (4, 30.0), (12, 30.0)])
    def test_eight_seconds_a_scene_and_at_most_thirty(self, scenes: int, seconds: float) -> None:
        assert read_seconds(scenes) == seconds

    def test_the_numbers_are_otto_s(self) -> None:
        assert (SCENE_SECONDS, PASS_SECONDS_MAX, ATTEMPTS) == (8.0, 30.0, 2)

    async def test_a_scene_is_read_inside_its_eight_seconds(self, monkeypatch: pytest.MonkeyPatch) -> None:
        seen: list[float] = []

        def read(path: Any, aoi: Any, classes: Any) -> AoiClouds:
            seen.append(READ_DEADLINE.get() - time.monotonic())
            return GOOD

        monkeypatch.setattr(module, "measure_aoi_clouds", read)
        await measurer()(scene())
        assert 6.0 < seen[0] <= 8.0

    async def test_the_time_of_a_pass_follows_the_number_of_its_scenes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        seen: list[float] = []

        def read(paths: Any, aoi: Any, classes: Any, **reading: Any) -> AoiClouds:
            seen.append(READ_DEADLINE.get() - time.monotonic())
            return GOOD

        monkeypatch.setattr(pass_filter, "measure_aoi_pass", read)
        for count in (2, 3, 5):
            await pass_measurer().measure_pass(passes(count))
        assert [round(value) for value in seen] == [16, 24, 30]


def passes(count: int) -> list[dict[str, Any]]:
    return [scene(number) for number in range(1, count + 1)]


def pass_measurer(cache: Any = None) -> PassMeasurer:
    return PassMeasurer(
        SENTINEL_2_L2A,
        SQUARE,
        policy=POLICY,
        resolver=public,
        gdal_options={},
        slots=ReadSlots(POLICY),
        cache=cache,
        aoi_outlines=AoiOutlines(SQUARE),
    )


class TestOneRetry:
    """A failure another try may mend is repeated once; only then the scene or pass is skipped."""

    def failing(self, monkeypatch: pytest.MonkeyPatch, errors: list[BaseException | None]) -> list[int]:
        calls: list[int] = []

        def read(path: Any, aoi: Any, classes: Any) -> AoiClouds:
            calls.append(len(calls))
            error = errors[min(len(calls) - 1, len(errors) - 1)]
            if error is not None:
                raise error
            return GOOD

        monkeypatch.setattr(module, "measure_aoi_clouds", read)
        return calls

    @pytest.mark.parametrize("error", [RasterioIOError("stall"), OSError("reset"), ReadDeadlineExceeded()])
    async def test_a_failure_that_may_pass_is_tried_again_and_then_counts(
        self, monkeypatch: pytest.MonkeyPatch, error: BaseException
    ) -> None:
        calls = self.failing(monkeypatch, [error, None])
        got = measurer()
        assert (await got(scene())).cloud_pixels == 40
        assert len(calls) == 2 and got.retries == 1

    @pytest.mark.parametrize("error", [RasterioIOError("stall"), OSError("reset"), ReadDeadlineExceeded()])
    async def test_two_failures_skip_it_and_no_third_try_is_made(self, monkeypatch: pytest.MonkeyPatch, error: BaseException) -> None:
        calls = self.failing(monkeypatch, [error])
        assert await measurer()(scene()) is None
        assert len(calls) == 2

    async def test_a_failure_the_same_again_is_not_tried_twice(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls = self.failing(monkeypatch, [ValueError("the AOI does not fit")])
        assert await measurer()(scene()) is None
        assert len(calls) == 1

    async def test_a_scene_the_gateway_refuses_is_not_tried_at_all(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls = self.failing(monkeypatch, [None])
        assert await measurer()(scene(href="https://elsewhere.example.org/SCL.tif")) is None
        assert calls == []

    async def test_the_retry_gets_its_own_time(self, monkeypatch: pytest.MonkeyPatch) -> None:
        starts: list[float] = []

        def read(path: Any, aoi: Any, classes: Any) -> AoiClouds:
            starts.append(READ_DEADLINE.get() - time.monotonic())
            if len(starts) == 1:
                time.sleep(0.3)
                raise ReadDeadlineExceeded
            return GOOD

        monkeypatch.setattr(module, "measure_aoi_clouds", read)
        await measurer()(scene())
        assert starts[1] > starts[0] - 0.05 and starts[1] > 7.0

    async def test_a_pass_is_tried_again_once_too(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[int] = []

        def read(paths: Any, aoi: Any, classes: Any, **reading: Any) -> AoiClouds:
            calls.append(1)
            if len(calls) == 1:
                raise RasterioIOError("stall")
            return GOOD

        monkeypatch.setattr(pass_filter, "measure_aoi_pass", read)
        result = await pass_measurer().measure_pass(passes(2))
        assert result is not None and len(calls) == 2

    async def test_a_pass_that_fails_twice_is_none_and_one_that_cannot_fit_is_not_repeated(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[int] = []

        def stall(paths: Any, aoi: Any, classes: Any, **reading: Any) -> AoiClouds:
            calls.append(1)
            raise RasterioIOError("stall")

        monkeypatch.setattr(pass_filter, "measure_aoi_pass", stall)
        assert await pass_measurer().measure_pass(passes(2)) is None and len(calls) == 2
        calls.clear()

        def refused(paths: Any, aoi: Any, classes: Any, **reading: Any) -> AoiClouds:
            calls.append(1)
            raise ValueError("no")

        monkeypatch.setattr(pass_filter, "measure_aoi_pass", refused)
        assert await pass_measurer().measure_pass(passes(2)) is None and len(calls) == 1


class SlowMeasures:
    """``measure(item)`` that really takes ``seconds``, as a cold source does; counts what it measured."""

    def __init__(self, seconds: float, percent: float = 5.0) -> None:
        self.seconds = seconds
        self.percent = percent
        self.measured: list[str] = []

    async def __call__(self, item: Any) -> SceneMeasure:
        import asyncio

        self.measured.append(item["id"])
        await asyncio.sleep(self.seconds)
        return SceneMeasure(round(self.percent * 10), 1000, 100.0, 80.0)


@pytest.fixture
def short_response(monkeypatch: pytest.MonkeyPatch) -> None:
    """A response of 50 ms: any scene that takes longer is "past the clock"."""
    monkeypatch.setattr(module, "RESPONSE_SECONDS", 0.05)
    monkeypatch.setattr(pass_filter, "RESPONSE_SECONDS", 0.05)


class TestNoResponseWithoutProgress:
    """The first scene of a response is waited for to the end, whatever the clock of the response says."""

    async def respond(self, measures: Any, token: str | None = None, limit: int = 100):
        try:
            return await run_filter(
                request_for(RangeCondition(None, 20.0)), fetch_page=Source(30).fetch, measure=measures, limit=limit, token=token
            )
        finally:
            await module.settle()

    async def test_a_cold_scene_that_takes_longer_than_the_response_is_still_taken(self, short_response: None) -> None:
        measures = SlowMeasures(0.3)
        outcome = await self.respond(measures)
        assert outcome.checked >= 1 and outcome.found >= 1, "the scene was not given up on at 50 ms"
        assert outcome.next_token is not None and outcome.checked < 30, "and the response ended after it"

    async def test_the_search_goes_on_behind_it_to_the_end(self, short_response: None) -> None:
        kept = 0
        token = None
        for _ in range(60):
            outcome = await self.respond(SlowMeasures(0.06), token)
            kept = outcome.found
            token = outcome.next_token
            if token is None:
                break
        assert kept == 30 and token is None, "every response moved on, so the search came to its end"

    async def test_a_scene_that_is_skipped_counts_and_the_search_goes_on(self) -> None:
        clock = Clock()
        outcome = await run_filter(
            request_for(RangeCondition(None, 20.0)), fetch_page=Source(30).fetch,
            measure=Measures(lambda n: None if n == 0 else 5.0, clock=clock, cost=0.0), limit=100, token=None, clock=clock,
        )
        await module.settle()
        assert outcome.unreadable == 1 and outcome.found == 29


def test_the_filtered_source_has_the_time_of_its_first_reading() -> None:
    from earthx.api.aoi_cloud_filter import FILTERED_SOURCE_SECONDS

    assert FILTERED_SOURCE_SECONDS >= ATTEMPTS * PASS_SECONDS_MAX

