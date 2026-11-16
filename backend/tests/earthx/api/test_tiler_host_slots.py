"""The tiler's reads with one slot per host (M5-36 §5): every tile still comes, none waits for itself or another.

``EARTHX_SOURCE_INSTANCES=6`` shares the default cap of 6 so that this instance holds 1 per host, the hardest case
for a deadlock. The scenes are the synthetic ones of the mosaic tile with steps; their paths are local files, so
the host GDAL would ask is put back in where the readers and the route look it up. Each request runs in a thread
with a deadline, so a deadlock fails the test instead of hanging the run.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack

import anyio
import pytest
from fastapi.testclient import TestClient

from earthx.api.dependencies import policy_from_registry
from earthx.catalog.datasets import read_registry
from earthx.gateway import ReadSlots
from tests.earthx.api.test_tiler_mosaic_operator import (
    CLOUDS_THEN_NDVI,
    DATASET,
    HEIGHT,
    X0,
    Y0,
    Source,
    _app,
    _tiles,
    _url,
    files,  # noqa: F401  (a fixture)
    source,  # noqa: F401  (a fixture)
)
from tests.earthx.processing import sources

DEADLINE_S = 60


class Spy:
    """The most holders a host ever had, and on which side each slot was taken."""

    def __init__(self) -> None:
        self.most = 0
        self.sides: list[str] = []


@pytest.fixture
def spy(monkeypatch: pytest.MonkeyPatch) -> Iterator[Spy]:
    monkeypatch.setenv("EARTHX_SOURCE_INSTANCES", "6")
    host = lambda path: sources.HOST  # noqa: E731  — the host of every synthetic scene
    monkeypatch.setattr("earthx.readers.cog.asset_host", host)
    seen = Spy()
    take, slot, aslot = ReadSlots._take_or_queue, ReadSlots.slot, ReadSlots.aslot

    def counted(self, name, loop):
        waiter = take(self, name, loop)
        seen.most = max(seen.most, self._hosts[name].held)
        return waiter

    def in_thread(self, host):
        seen.sides.append("thread")
        return slot(self, host)

    def in_loop(self, host):
        seen.sides.append("loop")
        return aslot(self, host)

    monkeypatch.setattr(ReadSlots, "_take_or_queue", counted)
    monkeypatch.setattr(ReadSlots, "slot", in_thread)
    monkeypatch.setattr(ReadSlots, "aslot", in_loop)
    yield seen


@pytest.fixture
def api(source: Source, spy: Spy) -> Iterator[TestClient]:  # noqa: F811
    with ExitStack() as stack:
        yield stack.enter_context(TestClient(_app(source)))


def _within_deadline(call: Callable[[], object]) -> object:
    result: list[object] = []
    worker = threading.Thread(target=lambda: result.append(call()), daemon=True)
    worker.start()
    worker.join(DEADLINE_S)
    assert not worker.is_alive(), "the request waited for a slot it can never get"
    return result[0]


def _held(api: TestClient) -> int:
    return sum(state.held for state in api.app.state.earthx_read_slots._hosts.values())


def test_the_instance_holds_its_share_of_the_cap(api: TestClient) -> None:
    assert api.app.state.earthx_policy.connections_for(sources.HOST) == 1


def test_every_mosaic_tile_comes_with_one_slot_a_scene_at_a_time(api: TestClient, spy: Spy) -> None:
    for tile in _tiles():
        response = _within_deadline(lambda tile=tile: api.get(_url(api, tile, [], assets=("red",))))
        assert response.status_code in (200, 204), response.text
    assert spy.most == 1 and "thread" in spy.sides and _held(api) == 0


def test_a_mosaic_tile_with_steps_holds_one_slot_for_all_its_scenes(api: TestClient, spy: Spy) -> None:
    for tile in _tiles():
        response = _within_deadline(lambda tile=tile: api.get(_url(api, tile, CLOUDS_THEN_NDVI)))
        assert response.status_code in (200, 204), response.text
    # The route's thread holds the slot of the first scene; the scenes' threads read under it and take none.
    assert spy.most == 1 and spy.sides == ["thread"] * len(_tiles()) and _held(api) == 0


@pytest.mark.parametrize(
    "query",
    ["asset=red", "asset=red&asset=nir&op=band_math&op_version=1&params=%7B%22expression%22%3A%22nir-red%22%7D"],
)
def test_an_item_tile_takes_one_slot_in_the_thread_that_reads(api: TestClient, spy: Spy, query: str) -> None:
    z, x, y = _tiles()[0]
    response = _within_deadline(
        lambda: api.get(f"/collections/{DATASET}/items/A/tiles/WebMercatorQuad/{z}/{x}/{y}.tif?{query}")
    )
    assert response.status_code == 200, response.text
    assert spy.sides == ["thread"] and spy.most == 1 and _held(api) == 0


def test_tiles_and_downloads_at_once_with_one_slot_and_few_threads_all_finish(api: TestClient, spy: Spy) -> None:
    # Review of M5-36 PR 2: a slot taken in the event loop before a thread, and a thread that waits for that slot,
    # could hold each other for good. With every slot taken in the thread that reads, three threads and one slot
    # still serve them all.
    api.portal.call(lambda: setattr(anyio.to_thread.current_default_thread_limiter(), "total_tokens", 3))
    z, x, y = _tiles()[0]
    aoi = sources.aoi_around(X0 + 100, Y0 - HEIGHT * 10 + 100, X0 + 3500, Y0 - 100)
    calls = [lambda: api.get(f"/collections/{DATASET}/items/A/tiles/WebMercatorQuad/{z}/{x}/{y}.tif?asset=red")] * 6
    calls += [
        lambda: api.post(
            f"/collections/{DATASET}/download", json={"groups": [["A", "B"]], "assets": ["red"], "aoi": aoi}
        )
    ] * 4
    with ThreadPoolExecutor(max_workers=len(calls)) as pool:
        responses = [future.result(timeout=DEADLINE_S) for future in [pool.submit(call) for call in calls]]
    assert [response.status_code for response in responses] == [200] * len(calls), [r.text[:200] for r in responses]
    assert "loop" not in spy.sides and spy.most == 1 and _held(api) == 0


def test_a_bad_number_of_instances_stops_the_start(monkeypatch: pytest.MonkeyPatch, source: Source) -> None:  # noqa: F811
    monkeypatch.setenv("EARTHX_SOURCE_INSTANCES", "two")
    with pytest.raises(ValueError, match="EARTHX_SOURCE_INSTANCES") as raised:
        _app(source)
    assert "two" not in str(raised.value)


class TestTheShareOfTheRegistry:
    def test_two_instances_halve_each_cap(self) -> None:
        policy = policy_from_registry(read_registry(), instances=2)
        assert policy.connections_for("copernicus-dem-30m.s3.amazonaws.com") == 16
        assert policy.connections_for("data.geo.admin.ch") == 3
        assert policy.max_connections_per_host == 3

    def test_more_instances_than_a_cap_leave_one_each_and_say_so(self, caplog: pytest.LogCaptureFixture) -> None:
        policy = policy_from_registry(read_registry(), instances=7)
        assert policy.connections_for("data.geo.admin.ch") == 1
        assert policy.connections_for("copernicus-dem-30m.s3.amazonaws.com") == 4
        assert "data.geo.admin.ch, earth-search.aws.element84.com" in caplog.text
        assert "copernicus" not in caplog.text
