"""What a mosaic tile asks of the source, and of the server in front of it (M4-17b, plan M4-17 §4.3, §5, §11 Auflage 3).

A tile of a cold overpass needs the metadata of the items it reads, and the six tiles of a map view
ask for it at once. `ItemFetches` keeps that to one fetch per item and four at a time; these tests
check it on its own, then through the real app and the real gateway, and last that the largest request
(a selection of 2000 ids of 60 characters, and a tile URL with three steps) gets through uvicorn as the
compose file starts it.
"""

from __future__ import annotations

import asyncio
import json
import socket
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
import pytest
import uvicorn
from fastapi import FastAPI

from earthx.adapters import ADAPTER_SPECS
from earthx.api import mosaic_tiles
from earthx.api.dependencies import policy_from_registry
from earthx.api.item_source import OrderRefused, build_item_batch_source, build_item_source
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
    _serve,
    _tile_path,
    _tilejson_path,
)

pytestmark = pytest.mark.anyio

DELAY = 0.03


@pytest.fixture
def scenes(tmp_path: Path) -> Scenes:
    return Scenes(tmp_path)


class Counter:
    """An item source that answers after a delay and counts what runs at the same time."""

    def __init__(
        self, items: dict[str, dict[str, Any]], *, fail: set[str] = frozenset(), gate: asyncio.Event | None = None
    ) -> None:
        self.items = items
        self.fail = fail
        self.gate = gate
        self.calls: list[str] = []
        self.running = 0
        self.most = 0

    async def __call__(self, dataset: str, item_id: str) -> dict[str, Any]:
        self.calls.append(item_id)
        self.running += 1
        self.most = max(self.most, self.running)
        try:
            if self.gate is not None:
                await self.gate.wait()
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
            await mosaic_tiles.fetch_items(mosaic_tiles.ItemFetches(), source, DATASET, ["I00", "I01", "I02"])

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


class TestFetchingByIds:
    """The creation of a selection fetches in pages of a hundred ids and maps a failure as one item's fetch does."""

    @staticmethod
    def _source(known: set[str], asked: list[list[str]], extra: tuple[dict[str, Any], ...] = ()) -> Any:
        async def batch(dataset: str, item_ids: Any) -> list[dict[str, Any]]:
            asked.append(list(item_ids))
            return [{"id": item_id} for item_id in item_ids if item_id in known] + list(extra)

        return batch

    async def test_250_ids_are_three_pages_in_order(self) -> None:
        names = [f"I{n:03d}" for n in range(250)]
        asked: list[list[str]] = []
        found = await mosaic_tiles.fetch_selection_items(self._source(set(names), asked), DATASET, names)
        assert [len(page) for page in asked] == [100, 100, 50] and sum(asked, []) == names
        assert sorted(found) == names

    async def test_an_id_the_source_does_not_return_is_a_404_that_names_the_first_in_id_order(self) -> None:
        asked: list[list[str]] = []
        with pytest.raises(OrderRefused) as refused:
            await mosaic_tiles.fetch_selection_items(self._source({"A"}, asked), DATASET, ["A", "C", "B"])
        assert refused.value.status_code == 404 and "'B'" in refused.value.detail

    async def test_an_item_nobody_asked_for_is_left_out(self) -> None:
        source = self._source({"A", "B"}, [], extra=({"id": "STRAY"}, "not an item"))  # type: ignore[arg-type]
        assert sorted(await mosaic_tiles.fetch_selection_items(source, DATASET, ["A", "B"])) == ["A", "B"]

    async def test_a_source_that_fails_maps_as_it_does_for_one_item(self) -> None:
        from earthx.gateway import UpstreamError, UpstreamTimeout

        for failure, status in ((UpstreamError(500, "boom"), 502), (UpstreamTimeout("late"), 504), (UpstreamError(404, "gone"), 404)):

            async def failing(dataset: str, item_ids: Any, failure: Exception = failure) -> list[dict[str, Any]]:
                raise failure

            with pytest.raises(OrderRefused) as refused:
                await mosaic_tiles.fetch_selection_items(failing, DATASET, ["A", "B"])
            assert refused.value.status_code == status
            assert "boom" not in refused.value.detail  # the source's own text is not passed on

    async def test_a_database_that_fails_is_a_503_with_no_text_of_its_own(self) -> None:
        import psycopg

        async def failing(dataset: str, item_ids: Any) -> list[dict[str, Any]]:
            raise psycopg.OperationalError("connection to server at db.internal.example failed")

        with pytest.raises(OrderRefused) as refused:
            await mosaic_tiles.fetch_selection_items(failing, DATASET, ["A", "B"])
        assert refused.value.status_code == 503 and "internal.example" not in refused.value.detail


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
    # `httpx.ASGITransport` runs no lifespan, so what the lifespan would hang on the app is hung here.
    app.state.earthx_cache_pool = POOL
    app.state.earthx_item_batches = scenes.batch_source
    app.state.earthx_mosaic_selections = scenes.selections
    return app


async def _selected(http: httpx.AsyncClient, names: list[str]) -> str:
    response = await http.post(f"/collections/{DATASET}/mosaic", json={"items": names, "assets": [ASSET]})
    assert response.status_code in (200, 201), response.text
    return response.json()["id"]


def _all_asked(app: FastAPI, monkeypatch: pytest.MonkeyPatch, times: int) -> asyncio.Event:
    """Set once the app's `ItemFetches.get` was called ``times`` times.

    A source held by it answers only when every request waits on the fetches. Without it, "at once"
    is a matter of timing: a request that reaches the fetches more than `DELAY` after the first
    finds the fetch ended and fetches again, since these apps have no item cache behind it (NM4-23).
    """
    asked = asyncio.Event()
    fetches = app.state.earthx_item_fetches
    real_get = fetches.get
    calls = 0

    async def counted(*args: Any) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        if calls == times:
            asked.set()
        return await real_get(*args)

    monkeypatch.setattr(fetches, "get", counted)
    return asked


class TestSixTilesAtOnce:
    """The map asks for about six tiles of a view at the same moment."""

    async def test_they_fetch_each_item_once_and_never_more_than_four_at_a_time(
        self, scenes: Scenes, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        names = _scenes_over_the_tile(scenes, 10)
        app = _bare(scenes, monkeypatch)
        source = Counter({name: scenes.items[name] for name in names}, gate=_all_asked(app, monkeypatch, 6 * len(names)))
        app.state.earthx_item_source = source
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as http:
            chosen = await _selected(http, names)
            tiles = asyncio.gather(*(http.get(_tile_path(chosen)) for _ in range(6)))
            responses = await asyncio.wait_for(tiles, timeout=60)
        assert [response.status_code for response in responses] == [200] * 6
        assert sorted(source.calls) == sorted(names)
        assert source.most == mosaic_tiles.MAX_ITEM_FETCHES
        assert app.state.earthx_item_fetches._running == {}

    async def test_the_tilejson_fetches_nothing_and_the_tiles_share_the_fetches(
        self, scenes: Scenes, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        names = _scenes_over_the_tile(scenes, 6)
        app = _bare(scenes, monkeypatch)
        source = Counter({name: scenes.items[name] for name in names}, gate=_all_asked(app, monkeypatch, 3 * len(names)))
        app.state.earthx_item_source = source
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as http:
            chosen = await _selected(http, names)
            requests = asyncio.gather(
                http.get(_tilejson_path(chosen)), *(http.get(_tile_path(chosen)) for _ in range(3))
            )
            responses = await asyncio.wait_for(requests, timeout=60)
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
            chosen = await _selected(http, names)
            responses = await asyncio.gather(*(http.get(_tile_path(chosen)) for _ in range(4)))
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
                chosen = [await _selected(http, lot) for lot in lots]
                responses = await asyncio.gather(*(http.get(_tile_path(selection)) for selection in chosen))
        assert [response.status_code for response in responses] == [200] * 6, [r.text for r in responses]
        assert sorted(asked) == sorted(names)
        assert 1 < most <= mosaic_tiles.MAX_ITEM_FETCHES <= policy.max_connections_per_host


    async def test_a_selection_of_250_scenes_is_three_searches_through_the_gateway_and_no_item_request(
        self, scenes: Scenes, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        names = _scenes_over_the_tile(scenes, 250)
        app = _bare(scenes, monkeypatch)
        policy = policy_from_registry(REGISTRY)
        searches: list[list[str]] = []
        paths: list[str] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            paths.append(f"{request.method} {request.url.path.rsplit('/', 1)[-1]}")
            body = json.loads(request.content)
            searches.append(body["ids"])
            return httpx.Response(
                200, json={"type": "FeatureCollection", "features": [scenes.items[item_id] for item_id in body["ids"]]}
            )

        async with Gateway(
            policy, transport=httpx.MockTransport(handler), resolve=lambda host, port: ("93.184.216.34",)
        ) as gateway:
            app.state.earthx_item_batches = build_item_batch_source(REGISTRY, ADAPTER_SPECS, gateway, None)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as http:
                chosen = await _selected(http, names)
        assert chosen in scenes.selections.rows
        assert paths == ["POST search"] * 3
        assert [len(ids) for ids in searches] == [100, 100, 50]
        assert sorted(sum(searches, [])) == sorted(names)


@pytest.fixture
def server(scenes: Scenes, monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[str, list[str]]]:
    """The tiler under uvicorn with its defaults, as `docker-compose.yml` starts it, on a free local port.

    Yields its address and 2000 item ids of 60 characters: one scene over the tile and 1999 away from it, so that
    all are in the selection and only the one is read.
    """
    scenes.add("BASE", ZONE_32, SEAM_X - 5000.0, 10_000.0, 10)
    long_ids = [f"S2C_{n:04d}_".ljust(60, "x") for n in range(mosaic_tiles.MAX_SELECTION_ITEMS - 1)]
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


#: A chain of three steps on the one asset of the scenes, as the panel would send it (NM4-04 §7.7).
CHAIN = "&".join(
    f"op={op}&op_version=1&params={quote(json.dumps(params, separators=(',', ':'), sort_keys=True))}"
    for op, params in (
        ("normalize", {"in_min": 0, "in_max": 255, "out_min": 0, "out_max": 1, "clip": True}),
        ("band_math", {"expression": "visual * 2 - 1"}),
        ("normalize", {"in_min": -1, "in_max": 1, "out_min": 0, "out_max": 255, "clip": True}),
    )
)


def _http(address: str, request: str, body: bytes = b"") -> tuple[str, bytes]:
    """The status line and the body of what the server answers a request sent by hand over a socket.

    By hand because the guard of the test suite allows no name lookup, not even of 127.0.0.1.
    """
    host, port = address.removeprefix("http://").split(":")
    headers = f"Host: {host}\r\nConnection: close\r\n"
    if body:
        headers += f"Content-Type: application/json\r\nContent-Length: {len(body)}\r\n"
    with socket.socket() as connection:
        connection.settimeout(30)
        connection.connect((host, int(port)))
        connection.sendall(f"{request} HTTP/1.1\r\n{headers}\r\n".encode() + body)
        received = b""
        while chunk := connection.recv(65536):
            received += chunk
    head, _, content = received.partition(b"\r\n\r\n")
    return head.split(b"\r\n", 1)[0].decode(), content


class TestTheLargestRequests:
    @pytest.mark.parametrize("steps", ["", CHAIN], ids=["scenes", "scenes and three steps"])
    def test_a_selection_of_2000_ids_of_60_characters_and_its_tile_get_through_the_server_the_compose_file_starts(
        self, server: tuple[str, list[str]], steps: str
    ) -> None:
        address, ids = server
        assert len(ids) == mosaic_tiles.MAX_SELECTION_ITEMS
        body = json.dumps({"items": ids, "assets": [ASSET]}, separators=(",", ":")).encode()
        assert 120_000 < len(body) < mosaic_tiles.MAX_SELECTION_BODY_BYTES  # 2000 ids of 60 characters, a little under the limit
        status, content = _http(address, f"POST /collections/{DATASET}/mosaic", body)
        assert status == "HTTP/1.1 201 Created", (status, content[-300:])
        target = _tile_path(json.loads(content)["id"]) + (f"?{steps}" if steps else "")
        assert len(target) <= mosaic_tiles.MAX_MOSAIC_REQUEST_BYTES
        status, content = _http(address, f"GET {target}")
        assert status == "HTTP/1.1 200 OK", (status, content[-300:])
