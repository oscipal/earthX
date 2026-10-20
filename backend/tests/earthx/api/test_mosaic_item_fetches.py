"""What a mosaic tile asks of the source, and of the server in front of it (M4-17b, plan M4-17 §4.3, §5, §11 Auflage 3).

A tile of a cold overpass needs the metadata of every item in its URL, and the six tiles of a map view
ask for it at once. `ItemFetches` keeps that to one fetch per item and four at a time; these tests
check it on its own, then through the real app and the real gateway, and last that the longest URL
(64 ids of 60 characters) gets through uvicorn as the compose file starts it.
"""

from __future__ import annotations

import asyncio
import socket
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import uvicorn
from fastapi import FastAPI

from earthx.adapters import ADAPTER_SPECS
from earthx.api import mosaic_tiles
from earthx.api.dependencies import policy_from_registry
from earthx.api.item_source import OrderRefused, build_item_source
from earthx.gateway import Gateway
from earthx.gateway.policy import Policy
from tests.earthx.access.test_mosaic_tiles import SEAM_X
from tests.earthx.api.test_tiler_mosaic import (
    ASSET,
    DATASET,
    POOL,
    REGISTRY,
    ZONE_32,
    Scenes,
    _app,
    _query,
    _serve,
    _tile_path,
)

pytestmark = pytest.mark.anyio

DELAY = 0.03


@pytest.fixture
def scenes(tmp_path: Path) -> Scenes:
    return Scenes(tmp_path)


class Counter:
    """An item source that answers after a delay and counts what runs at the same time."""

    def __init__(self, items: dict[str, dict[str, Any]], *, fail: set[str] = frozenset()) -> None:
        self.items = items
        self.fail = fail
        self.calls: list[str] = []
        self.running = 0
        self.most = 0

    async def __call__(self, dataset: str, item_id: str) -> dict[str, Any]:
        self.calls.append(item_id)
        self.running += 1
        self.most = max(self.most, self.running)
        try:
            await asyncio.sleep(DELAY)
        finally:
            self.running -= 1
        if item_id in self.fail:
            raise ConnectionResetError(item_id)  # not one of the source failures `fetch_item_or_refuse` maps
        return self.items[item_id]


def _items(count: int) -> dict[str, dict[str, Any]]:
    return {f"I{n:02d}": {"id": f"I{n:02d}"} for n in range(count)}


class TestItemFetches:
    async def test_the_same_item_asked_by_many_is_fetched_once(self) -> None:
        source = Counter(_items(3))
        fetches = mosaic_tiles.ItemFetches()
        results = await asyncio.gather(*(fetches.get(source, "d", "I01") for _ in range(8)))
        assert source.calls == ["I01"]
        assert all(result == {"id": "I01"} for result in results)

    async def test_no_more_than_the_limit_run_at_the_same_time_however_many_ask(self) -> None:
        source = Counter(_items(30))
        fetches = mosaic_tiles.ItemFetches()
        await asyncio.gather(*(fetches.get(source, "d", f"I{n:02d}") for n in range(30) for _ in range(2)))
        assert sorted(source.calls) == sorted(_items(30))
        assert source.most == mosaic_tiles.MAX_ITEM_FETCHES == 4

    async def test_an_item_of_another_dataset_is_another_fetch(self) -> None:
        source = Counter(_items(1))
        fetches = mosaic_tiles.ItemFetches()
        await asyncio.gather(fetches.get(source, "one", "I00"), fetches.get(source, "two", "I00"))
        assert source.calls == ["I00", "I00"]

    async def test_nothing_is_kept_after_the_fetches_end_so_the_next_ask_fetches_again(self) -> None:
        source = Counter(_items(1))
        fetches = mosaic_tiles.ItemFetches()
        await fetches.get(source, "d", "I00")
        await asyncio.sleep(0)
        assert fetches._running == {}
        await fetches.get(source, "d", "I00")
        assert source.calls == ["I00", "I00"]

    async def test_a_failure_is_given_to_everyone_who_waited_and_is_not_kept(self) -> None:
        source = Counter(_items(1), fail={"I00"})
        fetches = mosaic_tiles.ItemFetches()
        results = await asyncio.gather(*(fetches.get(source, "d", "I00") for _ in range(3)), return_exceptions=True)
        assert [type(result) for result in results] == [ConnectionResetError] * 3
        assert source.calls == ["I00"]
        await asyncio.sleep(0)
        assert fetches._running == {}

    async def test_a_request_that_gives_up_does_not_cancel_the_fetch_the_others_wait_for(self) -> None:
        source = Counter(_items(1))
        fetches = mosaic_tiles.ItemFetches()
        impatient = asyncio.ensure_future(fetches.get(source, "d", "I00"))
        patient = asyncio.ensure_future(fetches.get(source, "d", "I00"))
        await asyncio.sleep(DELAY / 3)
        impatient.cancel()
        assert await patient == {"id": "I00"}
        assert source.calls == ["I00"]

    async def test_a_source_that_refuses_is_an_order_refused_with_the_status_of_the_source(self) -> None:
        async def missing(dataset: str, item_id: str) -> dict[str, Any]:
            from earthx.gateway import UpstreamError

            raise UpstreamError(404, "not found")

        with pytest.raises(OrderRefused) as refused:
            await mosaic_tiles.fetch_items(mosaic_tiles.ItemFetches(), missing, DATASET, ["A", "B"])
        assert refused.value.status_code == 404 and "'A'" in refused.value.detail

    async def test_the_first_failure_in_id_order_is_the_one_reported(self) -> None:
        source = Counter(_items(3), fail={"I00", "I02"})
        with pytest.raises(ConnectionResetError, match="I00"):
            await mosaic_tiles.fetch_items(mosaic_tiles.ItemFetches(), source, DATASET, ["I02", "I01", "I00"][::-1])

    async def test_what_belongs_to_another_event_loop_is_left_behind(self) -> None:
        """A process has one loop; a test client that runs one per request must not wait on a dead one's fetch."""
        fetches = mosaic_tiles.ItemFetches()
        source = Counter(_items(1))
        other = asyncio.new_event_loop()
        try:
            fetches._loop = other
            fetches._running[("d", "I00")] = other.create_future()  # type: ignore[assignment]
            assert await asyncio.wait_for(fetches.get(source, "d", "I00"), timeout=5) == {"id": "I00"}
        finally:
            other.close()


def _scenes_over_the_tile(scenes: Scenes, count: int) -> list[str]:
    """``count`` items that all read one file covering the tile."""
    scenes.add("BASE", ZONE_32, SEAM_X - 5000.0, 10_000.0, 10)
    names = ["BASE"] + [f"I{n:02d}" for n in range(1, count)]
    for name in names[1:]:
        scenes.alias(name, "BASE")
    return names


def _bare(scenes: Scenes, monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    _serve(scenes, monkeypatch)
    app = _app(scenes)
    app.state.earthx_cache_pool = POOL
    return app


class TestSixTilesAtOnce:
    """The map asks for about six tiles of a view at the same moment."""

    async def test_they_fetch_each_item_once_and_never_more_than_four_at_a_time(
        self, scenes: Scenes, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        names = _scenes_over_the_tile(scenes, 10)
        app = _bare(scenes, monkeypatch)
        source = Counter({name: scenes.items[name] for name in names})
        app.state.earthx_item_source = source
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as http:
            responses = await asyncio.gather(*(http.get(_tile_path(), params=_query(names)) for _ in range(6)))
        assert [response.status_code for response in responses] == [200] * 6
        assert sorted(source.calls) == sorted(names)
        assert source.most == mosaic_tiles.MAX_ITEM_FETCHES
        assert app.state.earthx_item_fetches._running == {}

    async def test_the_tilejson_and_the_tiles_share_the_fetches(
        self, scenes: Scenes, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        names = _scenes_over_the_tile(scenes, 6)
        app = _bare(scenes, monkeypatch)
        source = Counter({name: scenes.items[name] for name in names})
        app.state.earthx_item_source = source
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as http:
            responses = await asyncio.gather(
                http.get("/collections/%s/mosaic/WebMercatorQuad/tilejson.json" % DATASET, params=_query(names)),
                *(http.get(_tile_path(), params=_query(names)) for _ in range(3)),
            )
        assert [response.status_code for response in responses] == [200] * 4
        assert sorted(source.calls) == sorted(names)

    async def test_a_source_that_fails_is_an_answer_for_every_tile_and_nothing_stays_behind(
        self, scenes: Scenes, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from earthx.gateway import UpstreamTimeout

        names = _scenes_over_the_tile(scenes, 3)
        app = _bare(scenes, monkeypatch)

        async def slow(dataset: str, item_id: str) -> dict[str, Any]:
            await asyncio.sleep(DELAY)
            raise UpstreamTimeout("late")

        app.state.earthx_item_source = slow
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as http:
            responses = await asyncio.gather(*(http.get(_tile_path(), params=_query(names)) for _ in range(4)))
        assert [response.status_code for response in responses] == [504] * 4
        assert app.state.earthx_item_fetches._running == {}


class TestAtTheGateway:
    """Plan §11 Auflage 3: the fetches stay within what the gateway allows per host, whatever the tiles do."""

    async def test_many_tiles_over_many_items_never_have_more_connections_open_than_the_policy_allows(
        self, scenes: Scenes, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        names = _scenes_over_the_tile(scenes, 48)
        app = _bare(scenes, monkeypatch)
        policy = policy_from_registry(REGISTRY)
        assert isinstance(policy, Policy) and policy.max_connections_per_host == 6
        running = most = 0
        asked: list[str] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            nonlocal running, most
            item_id = request.url.path.rsplit("/", 1)[-1]
            asked.append(item_id)
            running += 1
            most = max(most, running)
            try:
                await asyncio.sleep(DELAY)
            finally:
                running -= 1
            return httpx.Response(200, json=scenes.items[item_id])

        async with Gateway(
            policy, transport=httpx.MockTransport(handler), resolve=lambda host, port: ("93.184.216.34",)
        ) as gateway:
            app.state.earthx_item_source = build_item_source(REGISTRY, ADAPTER_SPECS, gateway, None)
            lots = [names[n : n + 8] for n in range(0, 48, 8)]  # six tiles, each over its own eight items
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as http:
                responses = await asyncio.gather(*(http.get(_tile_path(), params=_query(lot)) for lot in lots))
        assert [response.status_code for response in responses] == [200] * 6, [r.text for r in responses]
        assert sorted(asked) == sorted(names)
        assert 1 < most <= mosaic_tiles.MAX_ITEM_FETCHES <= policy.max_connections_per_host


@pytest.fixture
def server(scenes: Scenes, monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[str, list[str]]]:
    """The tiler under uvicorn with its defaults, as `docker-compose.yml` starts it, on a free local port.

    Yields its address and 64 item ids of 60 characters: one scene over the tile and 63 away from it, so that
    all 64 are fetched and only the one is read.
    """
    scenes.add("BASE", ZONE_32, SEAM_X - 5000.0, 10_000.0, 10)
    long_ids = [f"S2C_{n:02d}_".ljust(60, "x") for n in range(63)]
    away = {"type": "Polygon", "coordinates": [[[0.0, 0.0], [0.1, 0.0], [0.1, 0.1], [0.0, 0.1], [0.0, 0.0]]]}
    for item_id in long_ids:
        scenes.alias(item_id, "BASE", bbox=[0.0, 0.0, 0.1, 0.1], geometry=away)
    _serve(scenes, monkeypatch)
    app = _app(scenes)
    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning", access_log=False)
    instance = uvicorn.Server(config)
    thread = threading.Thread(target=instance.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    while not instance.started:
        assert time.monotonic() < deadline, "the server did not start"
        time.sleep(0.02)
    port = instance.servers[0].sockets[0].getsockname()[1]
    try:
        yield f"http://127.0.0.1:{port}", ["BASE", *long_ids]
    finally:
        instance.should_exit = True
        thread.join(timeout=15)


class TestTheLongestUrl:
    def test_64_ids_of_60_characters_get_through_the_server_the_compose_file_starts(
        self, server: tuple[str, list[str]]
    ) -> None:
        """Sent by hand over a socket: the guard of the test suite allows no name lookup, not even of 127.0.0.1."""
        address, ids = server
        assert len(ids) == mosaic_tiles.MAX_MOSAIC_ITEMS
        query = "&".join([f"item={item_id}" for item_id in ids] + [f"asset={ASSET}"])
        target = f"{_tile_path()}?{query}"
        assert len(target) > 4000  # the plan counts 4.3 kB for 64 long ids (§5)
        host, port = address.removeprefix("http://").split(":")
        with socket.socket() as connection:
            connection.settimeout(30)
            connection.connect((host, int(port)))
            connection.sendall(f"GET {target} HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n\r\n".encode())
            received = b""
            while chunk := connection.recv(65536):
                received += chunk
        status = received.split(b"\r\n", 1)[0].decode()
        assert status == "HTTP/1.1 200 OK", (status, received[-300:])
