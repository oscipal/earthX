"""Tiles that wait for a place do not hold the thread pool of the app (M5-30b plan §8.11, Otto 13.11.2026).

``MAX_CONCURRENT_TILES`` is two: of fifty tiles that a big selection asks for at once, two are read and forty-eight
wait. Waiting inside the synchronous tile function held one of the roughly 40 threads of the pool every synchronous route
of the app shares for each of them, so a cheap route such as ``/health`` waited behind the tiles. The measurement here
drives the real app over ASGI with synthetic scenes whose reading takes 0.15 s (a sleep, which gives the GIL back) and
asks ``/health`` while the fifty tiles wait.

The test does not name the gate: it holds for any way of waiting that keeps the pool free, and it is the one that ran,
unchanged, on the state before the gate to give the numbers of the plan.
"""

from __future__ import annotations

import asyncio
import functools
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import anyio.to_thread
import httpx
import pytest
from fastapi import FastAPI

from earthx.access import mosaic_tiles as reading
from earthx.access.overview_tiles import PYRAMID_GATE, PYRAMID_PLACES
from earthx.api import mosaic_tiles, overview_tiles, tiler
from earthx.api.tiler import build_app
from earthx.objectstore.client import S3
from tests.earthx.api.test_tiler_mosaic import Scenes, _serve
from tests.earthx.api.test_tiler_overview import REGISTRY, WITH_POOL, Catalogue, _path, _seam
from tests.earthx.api.test_tiler_pyramid import REGISTRY as PYRAMID_REGISTRY
from tests.earthx.api.test_tiler_pyramid import RELIEF_ID, pyramids, rows  # noqa: F401 - fixtures
from tests.earthx.api.test_tiler_pyramid import path as pyramid_path
from tests.earthx.objectstore.conftest import store, store_env  # noqa: F401 - fixtures
from tests.earthx.readers import mini_zarr

READ_S = 0.15
WAITING = 50


class Rig:
    """The app over synthetic scenes whose reading takes ``read_s`` seconds, and a count of the tiles read at once."""

    def __init__(self, scenes: Scenes, app: FastAPI) -> None:
        self.scenes = scenes
        self.app = app
        self.read_s = READ_S
        self.reading = 0
        self.started = 0
        self.most_reading = 0
        self.lock = threading.Lock()

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://tiler")


@pytest.fixture
def rig(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> Rig:
    scenes = Scenes(tmp_path)
    catalogue = Catalogue(scenes)
    monkeypatch.setattr(mosaic_tiles, "search_items_in_bbox_async", catalogue.search)
    _serve(scenes, monkeypatch)
    _seam(scenes)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> Any:  # pragma: no cover - ASGITransport does not run it; the state is set below
        yield

    app = build_app(REGISTRY, lifespan=lifespan)
    app.state.earthx_resolver = mini_zarr.from_memory
    app.state.earthx_item_source = None
    app.state.earthx_cache_pool = WITH_POOL
    made = Rig(scenes, app)
    open_asset, read_tile = reading.open_asset, reading.mosaic_reader

    def slow_scene(scene: Any, **options: Any) -> Any:
        time.sleep(made.read_s)  # a sleep gives the GIL back, as the network wait of a real read does
        return open_asset(scene, **options)

    def counted_tile(*args: Any, **kwargs: Any) -> Any:
        with made.lock:
            made.reading += 1
            made.started += 1
            made.most_reading = max(made.most_reading, made.reading)
        try:
            return read_tile(*args, **kwargs)
        finally:
            with made.lock:
                made.reading -= 1

    monkeypatch.setattr(reading, "open_asset", slow_scene)
    monkeypatch.setattr(reading, "mosaic_reader", counted_tile)
    return made


def _asgi(path: str) -> dict[str, Any]:
    return {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "GET", "path": path,
        "raw_path": path.encode(), "query_string": b"", "root_path": "", "scheme": "http",
        "headers": [(b"host", b"tiler")], "client": ("127.0.0.1", 50000), "server": ("tiler", 80),
    }  # fmt: skip


async def _call(app: FastAPI, path: str, *, hang_up_after: float | None = None) -> tuple[int, float]:
    """The status of one request over raw ASGI, and how long it took; the client leaves after ``hang_up_after`` s."""
    started = time.monotonic()
    state = {"sent": False}
    gone = asyncio.Event()
    messages: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        if not state["sent"]:
            state["sent"] = True
            return {"type": "http.request", "body": b"", "more_body": False}
        await gone.wait()
        return {"type": "http.disconnect"}

    async def send(message: dict[str, Any]) -> None:
        messages.append(message)

    if hang_up_after is not None:
        asyncio.get_running_loop().call_later(hang_up_after, gone.set)
    await app(_asgi(path), receive, send)
    return next(m["status"] for m in messages if m["type"] == "http.response.start"), time.monotonic() - started


async def _storm(rig: Rig, count: int, *, settle: float = 1.0) -> tuple[list[asyncio.Task[httpx.Response]], httpx.AsyncClient]:
    """``count`` tiles asked for at once; returns once they have all had time to reach the place they wait at."""
    client = rig.client()
    tasks = [asyncio.ensure_future(client.get(_path(extension="npy"))) for _ in range(count)]
    await asyncio.sleep(settle)
    return tasks, client


async def _all_at_the_gate(rig: Rig, gate: reading.TileGate, count: int) -> None:
    """Until each of ``count`` tiles waits at ``gate`` or has been read, so that a loaded machine does not count threads
    still on their way to it; at most 10 s, after which the threads are counted all the same (without a gate the tiles
    never get there)."""
    deadline = time.monotonic() + 10.0
    while gate.waiting + rig.started < count and time.monotonic() < deadline:
        await asyncio.sleep(0.02)


async def _places_taken(rig: Rig, count: int) -> None:
    """Until ``count`` tiles are being read, that is until every place is held; fails after 20 s instead of guessing."""
    deadline = time.monotonic() + 20.0
    while rig.started < count and time.monotonic() < deadline:
        await asyncio.sleep(0.01)
    assert rig.started >= count, "the storm did not take every place"


async def _end(tasks: list[asyncio.Task[httpx.Response]], client: httpx.AsyncClient) -> None:
    """The clients give up: the tiles that wait leave, the ones being read end in a moment."""
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    await client.aclose()
    await asyncio.sleep(0.4)


def test_a_cheap_synchronous_route_stays_responsive_while_fifty_tiles_wait(rig: Rig, capsys: pytest.CaptureFixture[str]) -> None:
    """The threads held are the check; the latency is a wide bound, so that a loaded CI machine does not make it flake.

    Before the gate 40 of the 40 threads were held and `/health` waited about as long as ten tiles of reading (0.4 s a
    scene here: seconds); with the gate two threads are held and it answers in a few hundred milliseconds at the most.
    """
    rig.read_s = 0.4

    async def scenario() -> tuple[float, float, int]:
        client = rig.client()
        started = time.monotonic()
        assert (await client.get("/health")).status_code == 200
        idle = time.monotonic() - started  # the same route with nothing waiting: what this machine answers in just now
        tasks, _ = await _storm(rig, WAITING, settle=0.0)
        await _all_at_the_gate(rig, reading.TILE_GATE, WAITING)
        borrowed = anyio.to_thread.current_default_thread_limiter().borrowed_tokens
        started = time.monotonic()
        health = await client.get("/health")
        answered = time.monotonic() - started
        assert health.status_code == 200
        await _end(tasks, client)
        return idle, answered, borrowed

    idle, answered, borrowed = asyncio.run(scenario())
    with capsys.disabled():
        print(f"\n[tile waiting] {WAITING} tiles waiting: /health answered in {answered * 1000:.0f} ms (idle {idle * 1000:.0f} ms), pool threads borrowed: {borrowed}")
    assert rig.most_reading <= reading.MAX_CONCURRENT_TILES, "never more than two tiles are read at once"
    assert borrowed <= reading.MAX_CONCURRENT_TILES + 2, f"{borrowed} threads of the pool are held by tiles"
    assert answered < idle + 1.5, f"/health waited {answered:.2f} s behind the tiles (idle: {idle:.2f} s)"


def test_the_tiles_themselves_are_read_two_at_a_time_and_all_are_answered(rig: Rig) -> None:
    async def scenario() -> float:
        client = rig.client()
        started = time.monotonic()
        responses = await asyncio.gather(*(client.get(_path(extension="npy")) for _ in range(8)))
        assert [r.status_code for r in responses] == [200] * 8
        await client.aclose()
        return time.monotonic() - started

    elapsed = asyncio.run(scenario())
    assert rig.most_reading == reading.MAX_CONCURRENT_TILES
    # Eight tiles of two scenes each, two tiles at a time: four rounds of about two reads one after the other.
    assert elapsed >= 4 * READ_S


def test_a_client_that_hangs_up_while_its_tile_waits_takes_no_place_and_reads_nothing(
    rig: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig.read_s = 2.0  # the places are held for 4 s: far longer than anything the client does below
    monkeypatch.setattr(reading.TileGate, "POLL_S", 0.01)

    async def scenario() -> tuple[int, float, int]:
        tasks, client = await _storm(rig, 2, settle=0.0)
        await _places_taken(rig, 2)  # both places are taken, whatever the speed of the machine
        opened_before = len(rig.scenes.opened)
        status, took = await _call(rig.app, _path(extension="npy"), hang_up_after=0.1)
        opened_by_it = len(rig.scenes.opened) - opened_before
        responses = await asyncio.gather(*tasks)
        assert [r.status_code for r in responses] == [200, 200]
        await client.aclose()
        return status, took, opened_by_it

    status, took, opened_by_it = asyncio.run(scenario())
    assert status == 499
    assert took < 2.0, f"it left after {took:.2f} s: not when it was noticed, but when a place came"
    assert opened_by_it == 0, "nothing was read for a client that was no longer there"
    assert rig.most_reading <= reading.MAX_CONCURRENT_TILES


def test_a_tile_that_waited_is_read_with_its_whole_time_budget(rig: Rig, monkeypatch: pytest.MonkeyPatch) -> None:
    """The wait is not the budget's (adr/0032 §6.2): with a budget shorter than the wait every tile is still answered ``200``.

    The budget runs on a clock of the thread of its tile that only the reading of a scene advances (by ``READ_S``), so
    how fast this machine is decides nothing: a tile has used 2 * READ_S of its budget of 2 * READ_S + 0.2 whatever
    the wall clock says, and the tiles that wait for a place spend none of it.
    """
    spent = threading.local()

    def clock() -> float:
        return getattr(spent, "seconds", 0.0)

    open_asset = reading.open_asset

    def timed_scene(scene: Any, **options: Any) -> Any:
        spent.seconds = clock() + READ_S
        return open_asset(scene, **options)

    monkeypatch.setattr(reading, "open_asset", timed_scene)
    monkeypatch.setattr(mosaic_tiles, "TILE_TIME_BUDGET_S", 2 * READ_S + 0.2)
    monkeypatch.setattr(tiler, "ReadBudget", functools.partial(reading.ReadBudget, clock=clock))

    async def scenario() -> list[int]:
        client = rig.client()
        responses = await asyncio.gather(*(client.get(_path(extension="npy")) for _ in range(6)))
        await client.aclose()
        return [r.status_code for r in responses]

    assert asyncio.run(scenario()) == [200] * 6
    assert rig.started == 6


def test_a_tile_of_a_pyramid_does_not_wait_behind_the_tiles_of_a_mosaic(rig: Rig) -> None:
    """The pyramid tile of a dataset takes no place: asked while the places are taken, it answers at once.

    The answer here is a refusal (the process has no store), which is the point: how long it takes to say so.
    """
    rig.read_s = 2.0  # the places are held for 4 s

    async def scenario() -> float:
        tasks, client = await _storm(rig, 6, settle=0.0)
        await _places_taken(rig, 2)
        started = time.monotonic()
        status, _ = await _call(rig.app, "/collections/synthetic-terrain/overview/tiles/WebMercatorQuad/3/0/0.npy")
        waited = time.monotonic() - started
        assert status in (400, 404, 503)
        await _end(tasks, client)
        return waited

    assert asyncio.run(scenario()) < 2.0, "it waited for the places of the mosaic"


# The pyramid tiles: one read of an object, and a rendering, each in a thread of the pool. A slow store must not fill it.


@pytest.fixture
def slow_store(rows: Any, pyramids: Any, store: Any, monkeypatch: pytest.MonkeyPatch) -> Rig:  # noqa: F811
    """The app over a pyramid whose store takes 0.4 s for an object; counts the objects being read at once."""
    rows.ready(RELIEF_ID)
    pyramids.put(RELIEF_ID, 6)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> Any:  # pragma: no cover
        yield

    app = build_app(PYRAMID_REGISTRY, lifespan=lifespan)
    app.state.earthx_cache_pool = WITH_POOL
    app.state.earthx_overviews = overview_tiles.OverviewSources(store)
    made = Rig(Scenes(Path("/nonexistent")), app)  # only the app and the counters are used
    made.read_s = 0.4
    counted = S3.get_bytes_and_metadata  # the double of the `pyramids` fixture: it still reads the real (moto) object

    def slow(client: S3, key: str) -> Any:
        with made.lock:
            made.reading += 1
            made.started += 1
            made.most_reading = max(made.most_reading, made.reading)
        try:
            time.sleep(made.read_s)
            return counted(client, key)
        finally:
            with made.lock:
                made.reading -= 1

    monkeypatch.setattr(S3, "get_bytes_and_metadata", slow)
    return made


async def _pyramid_storm(
    rig: Rig, count: int, *, settle: float = 1.0
) -> tuple[list[asyncio.Task[httpx.Response]], httpx.AsyncClient]:
    client = rig.client()
    tasks = [asyncio.ensure_future(client.get(pyramid_path(RELIEF_ID, 6))) for _ in range(count)]
    await asyncio.sleep(settle)
    return tasks, client


def test_a_cheap_route_stays_responsive_while_fifty_pyramid_tiles_wait_on_a_slow_store(
    slow_store: Rig, capsys: pytest.CaptureFixture[str]
) -> None:
    async def scenario() -> tuple[float, float, int]:
        client = slow_store.client()
        started = time.monotonic()
        assert (await client.get("/health")).status_code == 200
        idle = time.monotonic() - started
        tasks, storm_client = await _pyramid_storm(slow_store, WAITING, settle=0.0)
        await _all_at_the_gate(slow_store, PYRAMID_GATE, WAITING)
        borrowed = anyio.to_thread.current_default_thread_limiter().borrowed_tokens
        started = time.monotonic()
        assert (await client.get("/health")).status_code == 200
        answered = time.monotonic() - started
        await _end(tasks, storm_client)
        await client.aclose()
        return idle, answered, borrowed

    idle, answered, borrowed = asyncio.run(scenario())
    with capsys.disabled():
        print(f"\n[pyramid waiting] {WAITING} tiles waiting: /health answered in {answered * 1000:.0f} ms (idle {idle * 1000:.0f} ms), pool threads borrowed: {borrowed}")
    assert slow_store.most_reading <= PYRAMID_PLACES, "no more objects are read at once than the gate has places"
    assert borrowed <= PYRAMID_PLACES + 2, f"{borrowed} threads of the pool are held by pyramid tiles"
    assert answered < idle + 1.5, f"/health waited {answered:.2f} s behind the tiles (idle: {idle:.2f} s)"


def test_the_tiles_of_a_pyramid_all_come_and_the_gate_is_free_afterwards(slow_store: Rig) -> None:
    slow_store.read_s = 0.02

    async def scenario() -> list[int]:
        client = slow_store.client()
        responses = await asyncio.gather(*(client.get(pyramid_path(RELIEF_ID, 6)) for _ in range(30)))
        await client.aclose()
        return [r.status_code for r in responses]

    assert asyncio.run(scenario()) == [200] * 30
    assert 1 < slow_store.most_reading <= PYRAMID_PLACES
    async def free() -> None:
        taken = [await asyncio.wait_for(PYRAMID_GATE.enter(_never_gone), 0.3) for _ in range(PYRAMID_PLACES)]
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(PYRAMID_GATE.enter(_never_gone), 0.05)
        for place in taken:
            place.release()

    asyncio.run(free())


async def _never_gone() -> bool:
    return False


def test_a_client_that_hangs_up_while_its_pyramid_tile_waits_reads_nothing(slow_store: Rig) -> None:
    slow_store.read_s = 2.0

    async def scenario() -> tuple[int, int]:
        tasks, client = await _pyramid_storm(slow_store, PYRAMID_PLACES, settle=0.0)
        # Every place is taken, for 2 s, before the client comes; on a loaded machine the storm needs longer to start.
        deadline = time.monotonic() + 5.0
        while slow_store.started < PYRAMID_PLACES and time.monotonic() < deadline:
            await asyncio.sleep(0.02)
        assert slow_store.started == PYRAMID_PLACES, "the storm took every place first"
        reads_before = slow_store.started
        status, _ = await _call(slow_store.app, pyramid_path(RELIEF_ID, 6), hang_up_after=0.1)
        await asyncio.gather(*tasks)
        await client.aclose()
        return status, slow_store.started - reads_before

    status, reads_for_it = asyncio.run(scenario())
    assert (status, reads_for_it) == (499, 0), "nothing was read for a client that was no longer there"
    assert slow_store.most_reading <= PYRAMID_PLACES


def test_a_pyramid_tile_does_not_wait_behind_the_file_reads_of_a_mosaic(slow_store: Rig) -> None:
    """The two gates are apart: both places of the file reads taken, a pyramid tile still comes at once."""
    from earthx.access.mosaic_tiles import TILE_GATE

    slow_store.read_s = 0.01

    async def scenario() -> float:
        taken = [await TILE_GATE.enter(_never_gone) for _ in range(TILE_GATE.places)]
        client = slow_store.client()
        started = time.monotonic()
        response = await client.get(pyramid_path(RELIEF_ID, 6))
        took = time.monotonic() - started
        for place in taken:
            place.release()
        await client.aclose()
        assert response.status_code == 200
        return took

    assert asyncio.run(scenario()) < 1.0
