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
import threading
import time
from contextlib import asynccontextmanager
from typing import Any

import anyio.to_thread
import httpx
import pytest
from fastapi import FastAPI

from earthx.access import mosaic_tiles as reading
from earthx.api import mosaic_tiles
from earthx.api.tiler import build_app
from tests.earthx.api.test_tiler_mosaic import Scenes, _serve
from tests.earthx.api.test_tiler_overview import REGISTRY, WITH_POOL, Catalogue, _path, _seam
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


async def _end(tasks: list[asyncio.Task[httpx.Response]], client: httpx.AsyncClient) -> None:
    """The clients give up: the tiles that wait leave, the ones being read end in a moment."""
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    await client.aclose()
    await asyncio.sleep(0.4)


def test_a_cheap_synchronous_route_stays_responsive_while_fifty_tiles_wait(rig: Rig, capsys: pytest.CaptureFixture[str]) -> None:
    async def scenario() -> tuple[float, int]:
        tasks, client = await _storm(rig, WAITING)
        borrowed = anyio.to_thread.current_default_thread_limiter().borrowed_tokens
        started = time.monotonic()
        health = await client.get("/health")
        answered = time.monotonic() - started
        assert health.status_code == 200
        await _end(tasks, client)
        return answered, borrowed

    answered, borrowed = asyncio.run(scenario())
    with capsys.disabled():
        print(f"\n[tile waiting] {WAITING} tiles waiting: /health answered in {answered * 1000:.0f} ms, pool threads borrowed: {borrowed}")
    assert rig.most_reading <= reading.MAX_CONCURRENT_TILES, "never more than two tiles are read at once"
    assert borrowed <= reading.MAX_CONCURRENT_TILES + 2, f"{borrowed} threads of the pool are held by tiles"
    assert answered < 1.0, f"/health waited {answered:.2f} s behind the tiles"


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


def test_a_client_that_hangs_up_while_its_tile_waits_takes_no_place_and_reads_nothing(rig: Rig) -> None:
    rig.read_s = 0.8

    async def scenario() -> tuple[int, float, int]:
        tasks, client = await _storm(rig, 2, settle=0.3)  # both places are taken, for about a second
        opened_before = len(rig.scenes.opened)
        status, took = await _call(rig.app, _path(extension="npy"), hang_up_after=0.1)
        opened_by_it = len(rig.scenes.opened) - opened_before
        responses = await asyncio.gather(*tasks)
        assert [r.status_code for r in responses] == [200, 200]
        await client.aclose()
        return status, took, opened_by_it

    status, took, opened_by_it = asyncio.run(scenario())
    assert status == 499
    assert took < 0.1 + reading.TileGate.POLL_S + 0.3, f"it left after {took:.2f} s, when it was noticed"
    assert opened_by_it == 0, "nothing was read for a client that was no longer there"
    assert rig.most_reading <= reading.MAX_CONCURRENT_TILES


def test_a_tile_that_waited_is_read_with_its_whole_time_budget(rig: Rig, monkeypatch: pytest.MonkeyPatch) -> None:
    """The wait is not the budget's (adr/0032 §6.2): with a budget shorter than the wait every tile is still answered ``200``."""
    monkeypatch.setattr(mosaic_tiles, "TILE_TIME_BUDGET_S", 2 * READ_S + 0.2)

    async def scenario() -> list[int]:
        client = rig.client()
        responses = await asyncio.gather(*(client.get(_path(extension="npy")) for _ in range(6)))
        await client.aclose()
        return [r.status_code for r in responses]

    assert asyncio.run(scenario()) == [200] * 6


def test_a_tile_of_a_pyramid_does_not_wait_behind_the_tiles_of_a_mosaic(rig: Rig) -> None:
    """The pyramid tile of a dataset takes no place: asked while the places are taken, it answers at once.

    The answer here is a refusal (the process has no store), which is the point: how long it takes to say so.
    """
    rig.read_s = 0.8

    async def scenario() -> float:
        tasks, client = await _storm(rig, 6, settle=0.3)
        started = time.monotonic()
        status, _ = await _call(rig.app, "/collections/synthetic-terrain/overview/tiles/WebMercatorQuad/3/0/0.npy")
        waited = time.monotonic() - started
        assert status in (400, 404, 503)
        await _end(tasks, client)
        return waited

    assert asyncio.run(scenario()) < 0.3
