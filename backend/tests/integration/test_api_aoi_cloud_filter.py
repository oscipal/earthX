"""T-C, DS-03a2: the filter ``earthx:aoi_cloud_cover`` on ``POST /stac/search``, against real pgstac and a real
statistics cache, with the source mocked and the reading of a raster replaced (plan §6.5, §6.13).

The source is a stub of Earth Search that serves scenes in pages with a ``scl`` asset each; the cloud share of
scene ``n`` is a function of ``n`` that the replaced reader returns. One test reads real synthetic COGs.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
import psycopg
import pytest
from rasterio.errors import RasterioIOError

from earthx.access.aoi_clouds import AoiClouds
from earthx.api import aoi_cloud_filter
from earthx.api.main import build_app
from earthx.catalog.datasets import REGISTRY, SENTINEL_2_L2A
from earthx.catalog.load import main as load_catalog
from earthx.catalog.pgstac import load_collection, use_pgstac_search_path
from earthx.catalog.registry import CoverageProvider, DatasetRegistry, ItemHolding
from earthx.gateway import Gateway, Policy, ReadSlots
from earthx.readers.cog import AssetPath

pytestmark = pytest.mark.anyio

HOST = "earth-search.aws.element84.com"
ASSET_HOST = SENTINEL_2_L2A.source.asset_hosts[0]
S2 = SENTINEL_2_L2A.dataset_id
NATIVE = replace(
    SENTINEL_2_L2A,
    dataset_id="earthx-test-aoi-native",
    source=replace(
        SENTINEL_2_L2A.source, item_holding=ItemHolding.MATERIALIZED, source_collection_id="earthx-test-aoi-native"
    ),
    coverage=replace(SENTINEL_2_L2A.coverage, provider=CoverageProvider.LOCAL_SQL),
    search_filters=(),
)
POLICY = Policy(allowed_hosts=frozenset({HOST, ASSET_HOST}))

app = build_app(DatasetRegistry((*REGISTRY, NATIVE)))

PERIOD = "2024-05-01T00:00:00Z/2024-06-01T00:00:00Z"
# Digits no other number of a request or an answer has, to find the AOI wherever it leaks to.
SQUARE = {
    "type": "Polygon",
    "coordinates": [[[10.123456, 47.654321], [10.223456, 47.654321], [10.223456, 47.754321], [10.123456, 47.754321], [10.123456, 47.654321]]],
}
BBOX = [10.0, 47.5, 10.5, 48.0]
LEAKS = ("10.123456", "47.654321", "10.223456", "47.754321")


def share_by_number(number: int) -> float:
    """Every fourth scene has 5 % clouds in the AOI, the others 60 %."""
    return 5.0 if number % 4 == 0 else 60.0


class World:
    """The source stub, the replaced reader and what each was asked."""

    def __init__(self, total: int = 40, share: Callable[[int], float | None] = share_by_number) -> None:
        self.total = total
        self.share = share
        self.bodies: list[dict[str, Any]] = []
        self.urls: list[str] = []
        self.reads: list[tuple[int, dict[str, Any]]] = []
        self.unreadable: set[int] = set()
        self.read_seconds = 0.0
        self.error: httpx.Response | None = None
        self._lock = threading.Lock()
        self.running = self.peak = 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.urls.append(str(request.url))
        body = json.loads(request.content)
        self.bodies.append(body)
        if self.error is not None:
            return self.error
        start = int(body.get("next", 0))
        end = min(start + body["limit"], self.total)
        links = [{"rel": "next", "method": "POST", "body": {"next": str(end)}}] if end < self.total else []
        return httpx.Response(
            200,
            json={"type": "FeatureCollection", "features": [self.feature(n) for n in range(start, end)], "links": links},
        )

    def feature(self, number: int) -> dict[str, Any]:
        stamp = datetime(2024, 5, 31, tzinfo=timezone.utc) - timedelta(minutes=number)
        return {
            "type": "Feature",
            "stac_version": "1.0.0",
            "id": f"S2_{number:04d}",
            "collection": S2,
            "geometry": {"type": "Point", "coordinates": [10.0, 47.0]},
            "bbox": [10.0, 47.0, 10.0, 47.0],
            "properties": {"datetime": stamp.isoformat().replace("+00:00", "Z"), "eo:cloud_cover": 50.0},
            "assets": {"scl": {"href": f"https://{ASSET_HOST}/scenes/{number}/SCL.tif"}},
            "links": [],
        }

    def reader(self, path: Any, aoi: dict[str, Any], classes: frozenset[int]) -> AoiClouds:
        number = int(path.item_id.removeprefix("S2_"))
        with self._lock:
            self.reads.append((number, aoi))
            self.running += 1
            self.peak = max(self.peak, self.running)
        try:
            time.sleep(self.read_seconds)
            if number in self.unreadable:
                raise RasterioIOError("could not read")
            percent = self.share(number)
            if percent is None:
                return AoiClouds(0, 0, 100, 80.0)
            return AoiClouds(cloud_pixels=round(percent * 10), data_pixels=1000, aoi_pixels=1000, resolution=80.0)
        finally:
            with self._lock:
                self.running -= 1

    def numbers_read(self) -> list[int]:
        return [number for number, _ in self.reads]


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch) -> World:
    stub = World()
    monkeypatch.setattr(aoi_cloud_filter, "measure_aoi_clouds", stub.reader)
    return stub


@pytest.fixture
def collections_loaded(require_postgres_env: None) -> Iterator[None]:
    assert load_catalog() == 0
    with psycopg.connect(autocommit=True) as conn:
        load_collection(conn, NATIVE)
        # Rows outlive one test (the cache pool commits); an earlier run's page or measure must not answer this one.
        conn.execute("DELETE FROM public.earthx_search_cache")
        conn.execute("DELETE FROM public.earthx_stats_cache")
    yield
    with psycopg.connect(autocommit=True) as conn:
        use_pgstac_search_path(conn)
        conn.execute("SELECT pgstac.delete_collection(%s)", (NATIVE.dataset_id,))


def _public(host: str, port: int) -> tuple[str, ...]:
    return ("93.184.216.34",)


@asynccontextmanager
async def _client(stub: World) -> AsyncIterator[httpx.AsyncClient]:
    async def sleep(seconds: float) -> None:
        return None

    async with app.router.lifespan_context(app):
        app.state.earthx_gateway = Gateway(
            POLICY, transport=httpx.MockTransport(stub.handler), resolve=_public, sleep=sleep
        )
        app.state.earthx_resolver = _public
        app.state.earthx_read_slots = ReadSlots(POLICY)
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                yield client
        finally:
            await aoi_cloud_filter.settle()  # the measures a response left running end before the pool closes


def body(**changes: Any) -> dict[str, Any]:
    """A search with the filter at 20 % within the AOI; ``changes`` replace or (with ``None``) remove a key."""
    base: dict[str, Any] = {
        "collections": [S2],
        "datetime": PERIOD,
        "intersects": SQUARE,
        "limit": 100,
        "query_by_collection": {S2: {"earthx:aoi_cloud_cover": {"lte": 20}}},
    }
    base.update(changes)
    return {key: value for key, value in base.items() if value is not None}


async def post(client: httpx.AsyncClient, request: dict[str, Any]) -> httpx.Response:
    return await client.post("/stac/search", json=request)


def next_token(response: httpx.Response) -> str | None:
    link = next((link for link in response.json()["links"] if link["rel"] == "next"), None)
    return None if link is None else link["body"]["token"].removeprefix("next:")


def ids(response: httpx.Response) -> list[int]:
    return [int(feature["id"].removeprefix("S2_")) for feature in response.json()["features"]]


class TestOneCollection:
    async def test_it_keeps_the_scenes_within_the_range_each_with_its_share(
        self, collections_loaded: None, world: World
    ) -> None:
        async with _client(world) as client:
            response = await post(client, body())
        assert response.status_code == 200
        answer = response.json()
        assert ids(response) == list(range(0, 40, 4))
        properties = answer["features"][0]["properties"]
        assert properties["earthx:aoi_cloud_cover"] == 5.0
        assert properties["earthx:aoi_measure"] == {
            "data_percent": 100.0, "cloud_pixels": 50, "data_pixels": 1000, "resolution": 80.0
        }
        assert answer["earthx:aoi_filter"] == {"checked": 40, "found": 10, "unreadable": 0, "limit_reached": False}
        assert "earthx:aoi_filter_by_collection" not in answer
        assert next_token(response) is None

    async def test_the_source_never_hears_of_the_filter_or_the_aoi_but_gets_the_other_filters(
        self, collections_loaded: None, world: World
    ) -> None:
        query = {S2: {"earthx:aoi_cloud_cover": {"lte": 20}, "eo:cloud_cover": {"lte": 90}, "platform": {"in": ["sentinel-2a"]}}}
        async with _client(world) as client:
            response = await post(client, body(query_by_collection=query))
        assert response.status_code == 200
        (sent, *_) = world.bodies
        assert sent["query"] == {"eo:cloud_cover": {"lte": 90.0}, "platform": {"in": ["sentinel-2a"]}}
        assert sent["limit"] == 100 and sent["intersects"] == SQUARE
        for source_body in world.bodies:
            assert "earthx" not in json.dumps(source_body)

    async def test_a_filter_on_the_aoi_alone_leaves_the_source_unfiltered(
        self, collections_loaded: None, world: World
    ) -> None:
        async with _client(world) as client:
            await post(client, body())
        assert "query" not in world.bodies[0]

    async def test_the_shared_query_spelling_works_too(self, collections_loaded: None, world: World) -> None:
        async with _client(world) as client:
            response = await post(
                client, body(query_by_collection=None, query={"earthx:aoi_cloud_cover": {"lte": 20}})
            )
        assert response.status_code == 200 and ids(response) == list(range(0, 40, 4))

    async def test_both_scene_and_aoi_filter_may_stand_together(self, collections_loaded: None, world: World) -> None:
        query = {S2: {"eo:cloud_cover": {"lte": 30}, "earthx:aoi_cloud_cover": {"gte": 50}}}
        async with _client(world) as client:
            response = await post(client, body(query_by_collection=query))
        assert response.status_code == 200
        assert world.bodies[0]["query"] == {"eo:cloud_cover": {"lte": 30.0}}
        assert ids(response) == [n for n in range(40) if n % 4]

    async def test_a_bbox_is_measured_as_a_polygon(self, collections_loaded: None, world: World) -> None:
        async with _client(world) as client:
            response = await post(client, body(intersects=None, bbox=BBOX))
        assert response.status_code == 200
        assert world.bodies[0]["bbox"] == BBOX and "intersects" not in world.bodies[0]
        assert world.reads[0][1]["type"] == "Polygon"

    async def test_a_long_aoi_goes_to_the_source_as_its_bbox_and_is_measured_as_itself(
        self, collections_loaded: None, world: World
    ) -> None:
        async with _client(world) as client:
            response = await post(client, body(intersects=None, bbox=BBOX, **{"earthx:aoi": SQUARE}))
        assert response.status_code == 200
        assert world.bodies[0]["bbox"] == BBOX
        assert "intersects" not in world.bodies[0] and "earthx:aoi" not in world.bodies[0]
        assert all(aoi == SQUARE for _, aoi in world.reads)

    async def test_a_scene_without_a_valid_pixel_falls_out(self, collections_loaded: None, world: World) -> None:
        world.share = lambda n: None if n == 0 else share_by_number(n)
        async with _client(world) as client:
            response = await post(client, body())
        assert ids(response) == list(range(4, 40, 4))
        assert response.json()["earthx:aoi_filter"]["checked"] == 40

    async def test_a_scene_that_cannot_be_read_is_counted_and_not_returned(
        self, collections_loaded: None, world: World
    ) -> None:
        world.unreadable = {4, 5}
        async with _client(world) as client:
            response = await post(client, body())
        assert 4 not in ids(response)
        assert response.json()["earthx:aoi_filter"] == {"checked": 40, "found": 9, "unreadable": 2, "limit_reached": False}


class TestResponsesAndMarkers:
    async def test_a_response_may_carry_fewer_scenes_than_limit_and_the_marker_goes_on(
        self, collections_loaded: None, world: World
    ) -> None:
        world.total = 1000
        async with _client(world) as client:
            first = await post(client, body(limit=3))
            second = await post(client, body(limit=3, token=next_token(first)))
        assert ids(first) == [0, 4, 8] and ids(second) == [12, 16, 20]
        assert second.json()["earthx:aoi_filter"] == {"checked": 21, "found": 6, "unreadable": 0, "limit_reached": False}

    async def test_no_gap_and_no_double_over_many_responses(self, collections_loaded: None, world: World) -> None:
        world.total = 250
        kept: list[int] = []
        async with _client(world) as client:
            token = None
            for _ in range(40):
                response = await post(client, body(limit=7, token=token))
                assert response.status_code == 200
                kept += ids(response)
                token = next_token(response)
                if token is None:
                    break
        assert kept == list(range(0, 250, 4))
        assert sorted(set(world.numbers_read())) == list(range(250))

    async def test_a_hundred_checked_scenes_end_a_response_even_with_nothing_found(
        self, collections_loaded: None, world: World
    ) -> None:
        world.total, world.share = 1000, lambda n: 90.0
        async with _client(world) as client:
            response = await post(client, body())
        assert ids(response) == []
        assert response.json()["earthx:aoi_filter"] == {"checked": 100, "found": 0, "unreadable": 0, "limit_reached": False}
        assert next_token(response) is not None
        assert response.json()["open_collections"] == [S2]

    async def test_five_hundred_checked_scenes_end_the_search_and_no_marker_is_left(
        self, collections_loaded: None, world: World
    ) -> None:
        world.total, world.share = 2000, lambda n: 90.0
        async with _client(world) as client:
            token, counts = None, []
            for _ in range(8):
                response = await post(client, body(token=token))
                counts.append(response.json()["earthx:aoi_filter"]["checked"])
                token = next_token(response)
                if token is None:
                    break
        assert counts == [100, 200, 300, 400, 500]
        assert response.json()["earthx:aoi_filter"]["limit_reached"] is True
        assert response.json()["open_collections"] == []
        assert len(world.reads) == 500

    async def test_the_clock_ends_a_response_before_its_hundred_scenes(
        self, collections_loaded: None, world: World, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(aoi_cloud_filter, "RESPONSE_SECONDS", 0.3)
        world.total, world.share, world.read_seconds = 1000, lambda n: 90.0, 0.1
        async with _client(world) as client:
            response = await post(client, body())
        checked = response.json()["earthx:aoi_filter"]["checked"]
        assert 0 < checked < 100 and next_token(response) is not None

    async def test_the_marker_is_ours_and_holds_no_aoi(self, collections_loaded: None, world: World) -> None:
        world.total = 1000
        async with _client(world) as client:
            response = await post(client, body(limit=3))
        token = next_token(response)
        assert token is not None
        import base64

        text = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4)).decode()
        assert not any(leak in text for leak in LEAKS) and "coordinates" not in text

    async def test_a_marker_of_another_filter_or_area_is_refused_before_anything_is_read(
        self, collections_loaded: None, world: World
    ) -> None:
        world.total = 1000
        other_area = {
            "type": "Polygon",
            "coordinates": [[[10.3, 47.6], [10.4, 47.6], [10.4, 47.7], [10.3, 47.7], [10.3, 47.6]]],
        }
        async with _client(world) as client:
            token = next_token(await post(client, body(limit=3)))
            await aoi_cloud_filter.settle()
            reads, asked = len(world.reads), len(world.bodies)
            narrower = await post(
                client, body(token=token, query_by_collection={S2: {"earthx:aoi_cloud_cover": {"lte": 10}}})
            )
            elsewhere = await post(client, body(token=token, intersects=other_area))
            without = await post(client, body(token=token, query_by_collection=None))
        assert [r.status_code for r in (narrower, elsewhere, without)] == [400, 400, 400]
        assert len(world.reads) == reads and len(world.bodies) == asked
        assert not any(leak in text for text in (narrower.text, elsewhere.text) for leak in LEAKS)

    async def test_a_marker_of_a_search_without_the_filter_is_refused_by_one_with_it(
        self, collections_loaded: None, world: World
    ) -> None:
        world.total = 1000
        async with _client(world) as client:
            plain = await post(client, body(query_by_collection=None, limit=3))
            token = next_token(plain)
            response = await post(client, body(token=token))
        assert token is not None and response.status_code == 400

    async def test_a_marker_of_a_search_with_the_filter_is_refused_by_one_without(
        self, collections_loaded: None, world: World
    ) -> None:
        world.total = 1000
        async with _client(world) as client:
            token = next_token(await post(client, body(limit=3)))
            response = await post(client, body(query_by_collection=None, token=token))
        assert response.status_code == 400


class TestSeveralCollections:
    async def test_only_the_source_with_the_filter_is_measured_and_its_counts_have_their_own_key(
        self, collections_loaded: None, world: World
    ) -> None:
        async with _client(world) as client:
            response = await post(client, body(collections=[S2, NATIVE.dataset_id], limit=100))
        assert response.status_code == 200
        answer = response.json()
        assert answer["earthx:aoi_filter_by_collection"] == {
            S2: {"checked": 40, "found": 10, "unreadable": 0, "limit_reached": False}
        }
        assert "earthx:aoi_filter" not in answer
        assert set(world.numbers_read()) <= set(range(40))
        assert len(world.bodies) >= 1 and all(b["collections"] == [S2] for b in world.bodies)

    async def test_the_mixed_marker_goes_on_where_the_filtered_source_stopped(
        self, collections_loaded: None, world: World
    ) -> None:
        world.total = 1000
        async with _client(world) as client:
            first = await post(client, body(collections=[S2, NATIVE.dataset_id], limit=4))
            second = await post(client, body(collections=[S2, NATIVE.dataset_id], limit=4, token=next_token(first)))
        found = [n for response in (first, second) for n in ids(response)]
        assert found and found == sorted(set(found))
        assert S2 in second.json()["earthx:aoi_filter_by_collection"]
        first_checked = first.json()["earthx:aoi_filter_by_collection"][S2]["checked"]
        assert second.json()["earthx:aoi_filter_by_collection"][S2]["checked"] > first_checked

    async def test_the_filter_for_a_collection_without_it_is_a_400(self, collections_loaded: None, world: World) -> None:
        query = {NATIVE.dataset_id: {"earthx:aoi_cloud_cover": {"lte": 20}}}
        async with _client(world) as client:
            response = await post(client, body(collections=[S2, NATIVE.dataset_id], query_by_collection=query))
        assert response.status_code == 400 and world.bodies == []

    async def test_a_shared_query_names_the_collection_that_does_not_offer_it(
        self, collections_loaded: None, world: World
    ) -> None:
        async with _client(world) as client:
            response = await post(
                client,
                body(collections=[S2, NATIVE.dataset_id], query_by_collection=None, query={"earthx:aoi_cloud_cover": {"lte": 20}}),
            )
        assert response.status_code == 200
        assert response.json()["ignored_filters_by_collection"] == {NATIVE.dataset_id: ["earthx:aoi_cloud_cover"]}


class TestARequestACallerHasToChange:
    @pytest.mark.parametrize(
        ("changes", "message"),
        [
            ({"datetime": None}, "date range with a start and an end"),
            ({"datetime": "2024-05-01T00:00:00Z/.."}, "date range with a start and an end"),
            ({"datetime": "../2024-06-01T00:00:00Z"}, "date range with a start and an end"),
            ({"datetime": "2024-05-01T00:00:00Z"}, "date range with a start and an end"),
            ({"intersects": None}, "needs an area"),
            ({"intersects": {"type": "Point", "coordinates": [10.123456, 47.654321]}}, "needs an area"),
            ({"intersects": {"type": "LineString", "coordinates": [[10.123456, 47.654321], [10.2, 47.7]]}}, "needs an area"),
            ({"query_by_collection": {S2: {"earthx:aoi_cloud_cover": {"lte": 120.5}}}}, "outside the range"),
            ({"query_by_collection": {S2: {"earthx:aoi_cloud_cover": {"gte": 30, "lte": 10}}}}, "ends below"),
            ({"query_by_collection": {S2: {"earthx:aoi_cloud_cover": {"in": [1]}}}}, "operators gte and lte"),
            ({"query_by_collection": {S2: {"earthx:aoi_cloud_cover": {}}}}, "object of operators"),
            ({"intersects": None, "bbox": BBOX, "earthx:aoi": {"type": "Point", "coordinates": [10.2, 47.6]}}, "needs an area"),
            ({"intersects": None, "bbox": [20.0, 47.5, 20.5, 48.0], "earthx:aoi": SQUARE}, "outside the bbox"),
            ({"earthx:aoi": SQUARE}, "not with intersects"),
            ({"intersects": None, "earthx:aoi": SQUARE}, "goes with the bbox"),
            ({"query_by_collection": {S2: {"eo:cloud_cover": {"lte": 20}}}, "earthx:aoi": SQUARE}, "goes with the cloud share"),
            ({"query_by_collection": {S2: {"earthx:other": {"lte": 20}}}}, "computed by the platform"),
        ],
    )
    async def test_is_400_before_any_source_is_asked_and_names_no_value(
        self, collections_loaded: None, world: World, changes: dict[str, Any], message: str
    ) -> None:
        async with _client(world) as client:
            response = await post(client, body(**changes))
        assert response.status_code == 400
        assert message in response.json()["detail"]
        assert world.bodies == [] and world.reads == []
        assert "120.5" not in response.text and not any(leak in response.text for leak in LEAKS)

    async def test_a_body_over_a_megabyte(self, collections_loaded: None, world: World) -> None:
        async with _client(world) as client:
            response = await post(client, body(ids=None, **{"padding": "x" * 1_048_576}))
        assert response.status_code == 400 and "bytes" in response.json()["detail"]
        assert world.bodies == []

    async def test_a_search_of_more_than_twenty_thousand_positions_in_the_aoi(
        self, collections_loaded: None, world: World
    ) -> None:
        ring = [[10.0 + i * 1e-6, 47.5] for i in range(20_001)]
        huge = {"type": "Polygon", "coordinates": [[*ring, [10.0, 47.5]]]}
        async with _client(world) as client:
            response = await post(client, body(intersects=None, bbox=BBOX, **{"earthx:aoi": huge}))
        assert response.status_code == 400 and world.bodies == []

    @pytest.mark.parametrize("key", ["query", "query_by_collection", "earthx:aoi"])
    async def test_a_get_search_refuses_it(self, collections_loaded: None, world: World, key: str) -> None:
        async with _client(world) as client:
            response = await client.get("/stac/search", params={"collections": S2, key: "{}"})
        assert response.status_code == 400 and "POST" in response.json()["detail"]
        assert world.bodies == []

    async def test_the_coverage_map_refuses_it(self, collections_loaded: None, world: World) -> None:
        async with _client(world) as client:
            response = await client.get(
                f"/coverage/{S2}", params={"zoom": 4, "query": json.dumps({"earthx:aoi_cloud_cover": {"lte": 20}})}
            )
        assert response.status_code == 400 and "coverage map" in response.json()["detail"]
        assert world.bodies == []


class TestNoAoiInLogOrUrl:
    async def test_not_in_any_log_line_nor_in_a_url_of_the_source(
        self, collections_loaded: None, world: World, caplog: pytest.LogCaptureFixture
    ) -> None:
        world.unreadable = {1}
        with caplog.at_level(logging.DEBUG):
            async with _client(world) as client:
                response = await post(client, body(limit=5))
                await post(client, body(limit=5, token=next_token(response)))
        assert caplog.records
        everything = " ".join(str(record.__dict__) for record in caplog.records)
        for secret in (*LEAKS, "S2_00", "SCL.tif", ASSET_HOST, "coordinates"):
            assert secret not in everything
        assert not any(leak in url for url in world.urls for leak in LEAKS)
        assert any(record.getMessage() == "aoi cloud filter" for record in caplog.records)

    async def test_a_cache_that_raises_with_the_key_in_its_text_leaks_nothing(
        self, collections_loaded: None, world: World, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from earthx.catalog.stats_cache import PooledStatsCache

        async def get(self: Any, key: str) -> Any:
            raise RuntimeError(f"cache_key = {key}")

        async def put(self: Any, key: str, value: Any, **kwargs: Any) -> None:
            raise RuntimeError(f"cache_key = {key}")

        monkeypatch.setattr(PooledStatsCache, "get", get)
        monkeypatch.setattr(PooledStatsCache, "set", put)
        with caplog.at_level(logging.DEBUG):
            async with _client(world) as client:
                response = await post(client, body(limit=2))
        assert response.status_code == 200 and ids(response) == [0, 4]
        text = " ".join(str(record.__dict__) for record in caplog.records)
        assert "cache_key" not in text
        assert any(record.__dict__.get("error_type") == "RuntimeError" for record in caplog.records)

    async def test_a_sources_error_text_reaches_neither_the_answer_nor_the_log(
        self, collections_loaded: None, world: World, caplog: pytest.LogCaptureFixture
    ) -> None:
        world.error = httpx.Response(500, json={"description": "query_shard_exception: for input string 10.123456"})
        with caplog.at_level(logging.DEBUG):
            async with _client(world) as client:
                response = await post(client, body())
        assert response.status_code == 500 or response.status_code == 502
        assert "query_shard_exception" not in response.text
        assert all("query_shard_exception" not in str(record.__dict__) for record in caplog.records)


class TestTheCache:
    async def test_a_repeated_search_reads_no_raster_and_gives_the_same_answer(
        self, collections_loaded: None, world: World
    ) -> None:
        async with _client(world) as client:
            first = await post(client, body())
            reads = len(world.reads)
            second = await post(client, body())
        assert reads == 40 and len(world.reads) == 40
        assert ids(first) == ids(second)
        assert first.json()["features"][0]["properties"] == second.json()["features"][0]["properties"]

    async def test_scenes_measured_ahead_of_where_a_response_stopped_are_kept_for_the_next(
        self, collections_loaded: None, world: World
    ) -> None:
        world.total = 1000
        async with _client(world) as client:
            first = await post(client, body(limit=1))
            await aoi_cloud_filter.settle()
            ahead = len(world.reads)
            second = await post(client, body(limit=1, token=next_token(first)))
        assert ids(first) == [0] and ids(second) == [4]
        assert ahead > 1, "scenes behind the first hit were being measured when the response ended"
        assert sorted(world.numbers_read()) == sorted(set(world.numbers_read())), "no scene was read twice"

    async def test_another_area_measures_again(self, collections_loaded: None, world: World) -> None:
        other = {
            "type": "Polygon",
            "coordinates": [[[10.3, 47.6], [10.4, 47.6], [10.4, 47.7], [10.3, 47.7], [10.3, 47.6]]],
        }
        async with _client(world) as client:
            await post(client, body())
            await post(client, body(intersects=other))
        assert len(world.reads) == 80

    async def test_an_entry_lives_seven_days_and_holds_only_the_numbers(
        self, collections_loaded: None, world: World
    ) -> None:
        async with _client(world) as client:
            await post(client, body(limit=1))
        with psycopg.connect(autocommit=True) as conn:
            rows = conn.execute(
                "SELECT payload, expires_at - now() FROM public.earthx_stats_cache WHERE dataset_id = %s", (S2,)
            ).fetchall()
        assert rows
        for payload, remaining in rows:
            assert set(payload) == {"data_percent", "cloud_pixels", "data_pixels", "resolution"}
            assert timedelta(days=6, hours=23) < remaining <= timedelta(days=7)

    async def test_the_pages_of_the_source_come_from_the_search_cache_but_the_filtered_answer_is_not_stored(
        self, collections_loaded: None, world: World
    ) -> None:
        world.total = 1000
        async with _client(world) as client:
            await post(client, body(limit=3))
            sources_first = len(world.bodies)
            await post(client, body(limit=3))
        assert len(world.bodies) == sources_first, "the page of the source was cached"
        with psycopg.connect(autocommit=True) as conn:
            (stored,) = conn.execute("SELECT count(*) FROM public.earthx_search_cache").fetchone()
        assert stored == 1, "one entry: the source's page, no filtered answer"


class TestTheLoadOnTheSource:
    async def test_two_searches_at_once_never_read_more_than_six_at_a_time(
        self, collections_loaded: None, world: World
    ) -> None:
        world.total, world.read_seconds = 60, 0.03
        other = {
            "type": "Polygon",
            "coordinates": [[[10.3, 47.6], [10.4, 47.6], [10.4, 47.7], [10.3, 47.7], [10.3, 47.6]]],
        }
        async with _client(world) as client:
            first, second = await asyncio.gather(
                post(client, body()), post(client, body(intersects=other))
            )
        assert first.status_code == second.status_code == 200
        assert 1 < world.peak <= POLICY.max_connections_per_host


class TestRealRasters:
    async def test_the_share_of_a_synthetic_cog_in_the_aoi(
        self, collections_loaded: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The whole way, down to the counting of pixels, on a classification the test writes itself."""
        import numpy
        import rasterio
        from pyproj import Transformer
        from rasterio.enums import Resampling
        from rasterio.transform import from_origin

        size, pixel, origin_x, origin_y = 1024, 20.0, 500_000.0, 5_500_000.0
        data = numpy.full((size, size), 4, dtype="uint8")  # vegetation
        data[:, :512] = 9  # clouds in the west half
        path = tmp_path / "scl.tif"
        with rasterio.open(
            path, "w", driver="GTiff", dtype="uint8", count=1, height=size, width=size, crs="EPSG:32632",
            transform=from_origin(origin_x, origin_y, pixel, pixel), nodata=0, tiled=True, blockxsize=256, blockysize=256,
        ) as destination:
            destination.write(data, 1)
        with rasterio.open(path, "r+") as destination:
            destination.build_overviews([2, 4, 8, 16], Resampling.mode)
        # Columns 200..800, rows 200..800 as the AOI: 312 of 600 columns are cloud, 52.0 %.
        corners = [(origin_x + c * pixel, origin_y - r * pixel) for c, r in ((200, 200), (800, 200), (800, 800), (200, 800), (200, 200))]
        to_lonlat = Transformer.from_crs("EPSG:32632", "EPSG:4326", always_xy=True)
        aoi = {"type": "Polygon", "coordinates": [[list(to_lonlat.transform(x, y)) for x, y in corners]]}

        from earthx.access import resolve

        def local(ref: Any, policy: Any, resolver: Any, **kwargs: Any) -> AssetPath:
            return AssetPath(str(path), dataset_id=ref.dataset_id, item_id=ref.item_id, asset=ref.asset)

        monkeypatch.setattr(aoi_cloud_filter, "open_asset_ref", local)
        stub = World(total=3)
        async with _client(stub) as client:
            near = await post(client, body(intersects=aoi, query_by_collection={S2: {"earthx:aoi_cloud_cover": {"gte": 50, "lte": 55}}}))
            far = await post(client, body(intersects=aoi, query_by_collection={S2: {"earthx:aoi_cloud_cover": {"lte": 40}}}))
        assert resolve  # the module the replaced function stands for
        assert ids(near) == [0, 1, 2] and ids(far) == []
        measure = near.json()["features"][0]["properties"]["earthx:aoi_measure"]
        assert near.json()["features"][0]["properties"]["earthx:aoi_cloud_cover"] == 52.0
        assert measure["data_percent"] == 100.0 and measure["resolution"] == 80.0
