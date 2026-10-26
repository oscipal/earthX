"""The item fetches of the single-item routes are bundled like those of the mosaic tile (NM4-26 S2).

The map asks for about six tiles of a cold scene at the same moment, and each of them used to fetch the item
from the source itself (measured: five fetches for one scene, fifteen for thirteen). `_fetch_item` now goes
through the process's `ItemFetches`, the one the mosaic tile uses: one running fetch per item, and the item
cache is behind it as before. What a refusal means is still decided in `fetch_item_or_refuse`, so the status
and the text every waiter gets are those a lone request got.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI, HTTPException

from earthx.api import mosaic_tiles
from earthx.api.tiler import _fetch_item, build_app
from earthx.catalog.datasets import SENTINEL_2_L2A
from earthx.gateway import UpstreamError, UpstreamTimeout, check_url

pytestmark = pytest.mark.anyio

FIXTURE = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "earth_search" / "item_asset_hosts.json"
DATASET = SENTINEL_2_L2A.dataset_id
ITEM = "SYNTH_T00AAA_20260724T100000_L2A"
BASE = f"/collections/{DATASET}/items/{ITEM}"
DELAY = 0.03
SIX = 6


class Source:
    """An item source that answers after a delay, counts its calls and can fail."""

    def __init__(self, item: dict[str, Any], failure: Exception | None = None) -> None:
        self.item = item
        self.failure = failure
        self.calls: list[tuple[str, str]] = []

    async def __call__(self, dataset: str, item_id: str) -> dict[str, Any]:
        self.calls.append((dataset, item_id))
        await asyncio.sleep(DELAY)
        if self.failure is not None:
            raise self.failure
        return self.item


@pytest.fixture(scope="module")
def item() -> dict[str, Any]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture
def app(monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    """The real app without its lifespan, as `test_tiler.py` builds it; the reader of the asset is the one fake."""
    monkeypatch.setattr(
        "earthx.readers.cog.check_url",
        lambda url, policy, **_: check_url(url, policy, resolve=lambda host, port: ("93.184.216.34",)),
    )
    monkeypatch.setattr("earthx.access.tiles._read_statistics", lambda reader, src_path, **kwargs: {})
    app = build_app()
    app.state.earthx_cache_pool = None
    return app


def client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def statistics(http: httpx.AsyncClient, path: str = BASE) -> httpx.Response:
    return await http.get(f"{path}/statistics", params={"asset": "visual"})


class TestSixTilesOfOneColdScene:
    async def test_the_item_is_fetched_once(self, app: FastAPI, item: dict[str, Any]) -> None:
        source = Source(item)
        app.state.earthx_item_source = source
        async with client(app) as http:
            responses = await asyncio.gather(*(statistics(http) for _ in range(SIX)))
        assert [response.status_code for response in responses] == [200] * SIX
        assert source.calls == [(DATASET, ITEM)]
        assert app.state.earthx_item_fetches._running == {}

    async def test_other_scenes_are_fetched_each_once_and_not_waited_for(self, app: FastAPI, item: dict[str, Any]) -> None:
        other = {**item, "id": "SYNTH_T00BBB_20260724T100000_L2A"}
        items = {ITEM: item, other["id"]: other}

        async def source(dataset: str, item_id: str) -> dict[str, Any]:
            calls.append(item_id)
            await asyncio.sleep(DELAY)
            return items[item_id]

        calls: list[str] = []
        app.state.earthx_item_source = source
        async with client(app) as http:
            responses = await asyncio.gather(
                *(statistics(http, BASE) for _ in range(3)),
                *(statistics(http, f"/collections/{DATASET}/items/{other['id']}") for _ in range(3)),
            )
        assert [response.status_code for response in responses] == [200] * SIX
        assert sorted(calls) == sorted(items)

    async def test_the_fetches_are_the_ones_the_mosaic_tile_uses(self, app: FastAPI) -> None:
        """One instance for the process: the slots (`MAX_ITEM_FETCHES`) bound the fetches of every route together."""
        assert isinstance(app.state.earthx_item_fetches, mosaic_tiles.ItemFetches)

    @pytest.mark.parametrize(
        ("failure", "status", "detail"),
        [
            (UpstreamTimeout("late"), 504, "the source did not answer in time"),
            (UpstreamError(404, "not found"), 404, f"no item {ITEM!r} in {DATASET!r}"),
            (UpstreamError(500, "boom"), 502, "the source did not deliver the item"),
        ],
    )
    async def test_a_source_that_fails_gives_every_tile_the_same_answer(
        self, app: FastAPI, item: dict[str, Any], failure: Exception, status: int, detail: str
    ) -> None:
        source = Source(item, failure)
        app.state.earthx_item_source = source
        async with client(app) as http:
            responses = await asyncio.gather(*(statistics(http) for _ in range(SIX)))
        assert [(response.status_code, response.json()["detail"]) for response in responses] == [(status, detail)] * SIX
        assert len(source.calls) == 1
        assert app.state.earthx_item_fetches._running == {}

    async def test_an_item_that_is_not_the_one_asked_for_is_the_same_502_for_all(
        self, app: FastAPI, item: dict[str, Any]
    ) -> None:
        source = Source({**item, "id": "SOMETHING_ELSE"})
        app.state.earthx_item_source = source
        async with client(app) as http:
            responses = await asyncio.gather(*(statistics(http) for _ in range(SIX)))
        assert {response.status_code for response in responses} == {502}
        assert len({response.json()["detail"] for response in responses}) == 1
        assert len(source.calls) == 1


class TestWithoutConcurrency:
    async def test_one_request_after_the_other_each_asks_the_source(self, app: FastAPI, item: dict[str, Any]) -> None:
        """Nothing is kept beyond a running fetch: the item cache is what makes the second one cheap."""
        source = Source(item)
        app.state.earthx_item_source = source
        async with client(app) as http:
            first = await statistics(http)
            second = await statistics(http)
        assert (first.status_code, second.status_code) == (200, 200)
        assert len(source.calls) == 2

    async def test_a_refusal_of_one_request_does_not_stay_for_the_next(self, app: FastAPI, item: dict[str, Any]) -> None:
        source = Source(item, UpstreamTimeout("late"))
        app.state.earthx_item_source = source
        async with client(app) as http:
            failed = await statistics(http)
            source.failure = None
            served = await statistics(http)
        assert (failed.status_code, served.status_code) == (504, 200)


class TestTheHelperItself:
    async def test_six_calls_fetch_once_and_a_refusal_is_the_http_exception_it_always_was(
        self, app: FastAPI, item: dict[str, Any]
    ) -> None:
        source = Source(item, UpstreamError(404, "not found"))
        app.state.earthx_item_source = source
        results = await asyncio.gather(*(_fetch_item(app.state, DATASET, ITEM) for _ in range(SIX)), return_exceptions=True)
        assert all(isinstance(result, HTTPException) for result in results)
        assert {(result.status_code, result.detail) for result in results} == {  # type: ignore[union-attr]
            (404, f"no item {ITEM!r} in {DATASET!r}")
        }
        assert len(source.calls) == 1

    async def test_an_unknown_dataset_is_a_404_for_all(self, app: FastAPI, item: dict[str, Any]) -> None:
        from earthx.adapters.errors import UnknownCollection

        source = Source(item, UnknownCollection("nope"))
        app.state.earthx_item_source = source
        results = await asyncio.gather(*(_fetch_item(app.state, "nope", ITEM) for _ in range(SIX)), return_exceptions=True)
        assert {(result.status_code, result.detail) for result in results} == {(404, "no dataset 'nope'")}  # type: ignore[union-attr]
        assert len(source.calls) == 1
