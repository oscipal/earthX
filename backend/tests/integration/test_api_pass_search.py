"""T-C, DS-03c: ``earthx:evaluate`` and ``earthx:aoi_coverage`` on ``POST /stac/search``, against real pgstac and a real
statistics cache, with the source mocked and the reading of a raster replaced.

The source is a stub of Earth Search that serves scenes of a few overpasses, each with an outline and its properties. What is
asked of the source is read from the bodies it received: the filters on properties go to it per scene and never per pass,
where the platform judges them over the scenes of a pass. A materialized dataset (the elevation model's kind) is searched with
the coverage alone.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from dataclasses import replace
from typing import Any

import httpx
import psycopg
import pytest

from earthx.access.aoi_clouds import AoiClouds
from earthx.api import aoi_cloud_filter, pass_filter
from earthx.api.main import build_app
from earthx.catalog.datasets import REGISTRY, SENTINEL_2_L2A
from earthx.catalog.load import main as load_catalog
from earthx.catalog.pgstac import load_collection, upsert_items, use_pgstac_search_path
from earthx.catalog.registry import CoverageProvider, DatasetRegistry, ItemHolding, SearchCapabilities
from earthx.gateway import Gateway, Policy, ReadSlots

pytestmark = pytest.mark.anyio

HOST = "earth-search.aws.element84.com"
ASSET_HOST = SENTINEL_2_L2A.source.asset_hosts[0]
S2 = SENTINEL_2_L2A.dataset_id
POLICY = Policy(allowed_hosts=frozenset({HOST, ASSET_HOST}))
TILES = replace(
    SENTINEL_2_L2A,
    dataset_id="earthx-test-pass-tiles",
    source=replace(
        SENTINEL_2_L2A.source, item_holding=ItemHolding.MATERIALIZED, source_collection_id="earthx-test-pass-tiles"
    ),
    coverage=replace(SENTINEL_2_L2A.coverage, provider=CoverageProvider.LOCAL_SQL),
    search_filters=(),
    search_capabilities=SearchCapabilities(evaluate=False, aoi_coverage=True),
)

app = build_app(DatasetRegistry((*REGISTRY, TILES)))

PERIOD = "2024-05-01T00:00:00Z/2024-06-01T00:00:00Z"
# The AOI: one degree square. Digits no other number of a request or an answer has, to find it wherever it leaks to.
AOI = {
    "type": "Polygon",
    "coordinates": [[[10.123456, 47.654321], [11.123456, 47.654321], [11.123456, 48.654321], [10.123456, 48.654321], [10.123456, 47.654321]]],
}
LEAKS = ("10.123456", "47.654321", "11.123456", "48.654321")


def outline(west: float, east: float) -> dict[str, Any]:
    south, north = 47.4, 48.9  # taller than the AOI: only the east-west extent matters
    return {"type": "Polygon", "coordinates": [[[west, south], [east, south], [east, north], [west, north], [west, south]]]}


#: The scenes of the stub: (id, minute of the day, datatake, west, east, cloud cover). Two passes of two scenes, one of one.
#: Pass d1 lies over the AOI in two halves (10.1..10.9 and 10.7..11.3: they overlap), d2 likewise, d3 is a lone scene.
SCENES = [
    ("S2_0", 0, "d1", 10.0, 10.9, 30.0),
    ("S2_1", 1, "d1", 10.7, 11.3, 10.0),
    ("S2_2", 120, "d2", 10.0, 10.9, 60.0),
    ("S2_3", 121, "d2", 10.7, 11.3, 50.0),
    ("S2_4", 240, "d3", 10.0, 11.3, 15.0),
]


class Source:
    """Earth Search as a stub: the scenes above, newest first, and what it was asked."""

    def __init__(self) -> None:
        self.bodies: list[dict[str, Any]] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.bodies.append(body)
        features = [self.feature(*scene) for scene in reversed(SCENES)]
        return httpx.Response(200, json={"type": "FeatureCollection", "features": features, "links": []})

    @staticmethod
    def feature(name: str, minute: int, datatake: str, west: float, east: float, cloud: float) -> dict[str, Any]:
        return {
            "type": "Feature",
            "stac_version": "1.0.0",
            "id": name,
            "collection": S2,
            "geometry": outline(west, east),
            "bbox": [west, 47.4, east, 48.9],
            "properties": {
                "datetime": f"2024-05-10T{minute // 60:02d}:{minute % 60:02d}:00Z",
                "s2:datatake_id": datatake,
                "eo:cloud_cover": cloud,
                "platform": "sentinel-2a",
            },
            "assets": {"scl": {"href": f"https://{ASSET_HOST}/scenes/{name}/SCL.tif"}},
            "links": [],
        }


@pytest.fixture
def source() -> Source:
    return Source()


@pytest.fixture
def catalog(require_postgres_env: None) -> Iterator[None]:
    assert load_catalog() == 0
    with psycopg.connect(autocommit=True) as conn:
        load_collection(conn, TILES)
        upsert_items(conn, TILES, [_tile(f"t{n}", west=float(n), east=float(n + 1)) for n in range(9, 13)])
        conn.execute("DELETE FROM public.earthx_search_cache")
        conn.execute("DELETE FROM public.earthx_stats_cache")
    yield
    with psycopg.connect(autocommit=True) as conn:
        use_pgstac_search_path(conn)
        conn.execute("SELECT pgstac.delete_collection(%s)", (TILES.dataset_id,))


def _tile(name: str, *, west: float, east: float) -> dict[str, Any]:
    south, north = 47.0, 49.0
    return {
        "id": name,
        "type": "Feature",
        "stac_version": "1.0.0",
        "collection": TILES.dataset_id,
        "bbox": [west, south, east, north],
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[west, south], [east, south], [east, north], [west, north], [west, south]]],
        },
        "properties": {"datetime": "2014-01-01T00:00:00Z"},
        "assets": {},
        "links": [],
    }


def _public(host: str, port: int) -> tuple[str, ...]:
    return ("93.184.216.34",)


@asynccontextmanager
async def _client(source: Source) -> AsyncIterator[httpx.AsyncClient]:
    async def sleep(seconds: float) -> None:
        return None

    async with app.router.lifespan_context(app):
        app.state.earthx_gateway = Gateway(
            POLICY, transport=httpx.MockTransport(source.handler), resolve=_public, sleep=sleep
        )
        app.state.earthx_resolver = _public
        app.state.earthx_read_slots = ReadSlots(POLICY)
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                yield client
        finally:
            await aoi_cloud_filter.settle()


def request(query: dict[str, Any], **changes: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "collections": [S2],
        "datetime": PERIOD,
        "intersects": AOI,
        "limit": 100,
        "query_by_collection": {S2: query},
    }
    base.update(changes)
    return {key: value for key, value in base.items() if value is not None}


async def search(client: httpx.AsyncClient, body: dict[str, Any]) -> httpx.Response:
    return await client.post("/stac/search", json=body)


def found(response: httpx.Response) -> list[str]:
    return sorted(feature["id"] for feature in response.json()["features"])


CLOUD_UP_TO_25 = {"eo:cloud_cover": {"lte": 25}}


class TestTheWayOfJudging:
    async def test_without_the_key_a_search_judges_per_scene_and_the_source_does_it(
        self, catalog: None, source: Source
    ) -> None:
        async with _client(source) as client:
            response = await search(client, request(CLOUD_UP_TO_25))
        assert response.status_code == 200
        assert source.bodies[0]["query"] == {"eo:cloud_cover": {"lte": 25.0}}
        assert "earthx:aoi_filter" not in response.json(), "the source's answer is the answer"

    async def test_per_scene_sent_on_purpose_is_the_same(self, catalog: None, source: Source) -> None:
        async with _client(source) as client:
            response = await search(client, request(CLOUD_UP_TO_25, **{"earthx:evaluate": "scene"}))
        assert response.status_code == 200 and source.bodies[0]["query"] == {"eo:cloud_cover": {"lte": 25.0}}

    async def test_per_pass_the_source_is_not_asked_the_filter_and_the_platform_judges_the_passes(
        self, catalog: None, source: Source
    ) -> None:
        async with _client(source) as client:
            response = await search(client, request(CLOUD_UP_TO_25, **{"earthx:evaluate": "pass"}))
        assert response.status_code == 200
        assert "query" not in source.bodies[0], "a scene that fails alone may belong to a pass that meets it"
        # d1: 30 % over 10.0..10.9 and 10 % over what 10.7..11.3 adds (10.9..11.3): (0.9 * 30 + 0.4 * 10) / 1.3 = 23.8
        # d2: (0.9 * 60 + 0.4 * 50) / 1.3 = 57.2, d3: 15
        assert found(response) == ["S2_0", "S2_1", "S2_4"]
        assert response.json()["earthx:aoi_filter"] == {"checked": 5, "found": 3, "unreadable": 0, "limit_reached": False}

    async def test_the_same_search_per_scene_finds_other_scenes(self, catalog: None, source: Source) -> None:
        """Gegenprobe: the stub does not apply the query, so per scene the answer is what the source gave; the point is what
        it was asked: the filter, here, and in the per pass search not."""
        async with _client(source) as client:
            per_scene = await search(client, request(CLOUD_UP_TO_25, **{"earthx:evaluate": "scene"}))
            per_pass = await search(client, request(CLOUD_UP_TO_25, **{"earthx:evaluate": "pass"}))
        assert "query" in source.bodies[0] and "query" not in source.bodies[1]
        assert found(per_scene) != found(per_pass)

    async def test_a_bad_value_is_a_400_without_the_value(self, catalog: None, source: Source) -> None:
        async with _client(source) as client:
            response = await search(client, request(CLOUD_UP_TO_25, **{"earthx:evaluate": "orbit"}))
        assert response.status_code == 400 and "orbit" not in response.text
        assert "earthx:evaluate" in response.json()["detail"]

    async def test_it_is_refused_in_a_get(self, catalog: None, source: Source) -> None:
        async with _client(source) as client:
            response = await client.get("/stac/search", params={"collections": S2, "earthx:evaluate": "pass"})
        assert response.status_code == 400

    async def test_per_pass_without_a_filter_is_the_ordinary_search(self, catalog: None, source: Source) -> None:
        async with _client(source) as client:
            response = await client.post(
                "/stac/search",
                json={"collections": [S2], "datetime": PERIOD, "intersects": AOI, "earthx:evaluate": "pass"},
            )
        assert response.status_code == 200 and "earthx:aoi_filter" not in response.json()

    async def test_the_aoi_and_the_dates_stay_out_of_the_log_and_the_answer(
        self, catalog: None, source: Source, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level("DEBUG"):
            async with _client(source) as client:
                response = await search(
                    client, request(CLOUD_UP_TO_25, **{"earthx:evaluate": "pass"}, query_by_collection={S2: {**CLOUD_UP_TO_25, "earthx:aoi_coverage": {"gte": 50}}})
                )
        assert response.status_code == 200
        text = response.text + "".join(record.getMessage() + str(record.__dict__) for record in caplog.records)
        for leak in LEAKS:
            assert leak not in text
        assert "intersects" not in str(response.url)


class Reader:
    """The two ways of reading a raster, replaced: the scenes of a pass together, and one scene alone."""

    def __init__(self) -> None:
        self.passes: list[list[str]] = []
        self.scenes: list[str] = []

    def together(self, paths: list[Any], aoi: dict[str, Any], classes: frozenset[int]) -> AoiClouds:
        names = [path.item_id for path in paths]
        self.passes.append(names)
        water = 600 if "S2_0" in names else 100
        return AoiClouds(0, 1000, 1000, 80.0, {6: water, 4: 1000 - water})

    def alone(self, path: Any, aoi: dict[str, Any], classes: frozenset[int]) -> AoiClouds:
        self.scenes.append(path.item_id)
        return AoiClouds(0, 1000, 1000, 80.0, {6: 100, 4: 900})


@pytest.fixture
def reader(monkeypatch: pytest.MonkeyPatch) -> Reader:
    stub = Reader()
    monkeypatch.setattr(pass_filter, "measure_aoi_pass", stub.together)
    monkeypatch.setattr(aoi_cloud_filter, "measure_aoi_clouds", stub.alone)
    return stub


WATER_AT_LEAST_50 = {"earthx:aoi_water": {"gte": 50}}


class TestTheMeasuresInThePass:
    async def test_the_scenes_of_a_pass_are_read_together_and_a_lone_scene_alone(
        self, catalog: None, source: Source, reader: Reader
    ) -> None:
        async with _client(source) as client:
            response = await search(client, request(WATER_AT_LEAST_50, **{"earthx:evaluate": "pass"}))
        assert response.status_code == 200
        assert sorted(reader.passes) == [["S2_0", "S2_1"], ["S2_2", "S2_3"]]
        assert reader.scenes == ["S2_4"]
        assert found(response) == ["S2_0", "S2_1"], "the pass with 60 % water stays whole, the others fall"

    async def test_per_scene_every_scene_is_read_alone(self, catalog: None, source: Source, reader: Reader) -> None:
        async with _client(source) as client:
            response = await search(client, request(WATER_AT_LEAST_50, **{"earthx:evaluate": "scene"}))
        assert response.status_code == 200
        assert reader.passes == [] and sorted(reader.scenes) == [f"S2_{n}" for n in range(5)]
        assert found(response) == [], "10 % water in each"

    async def test_the_source_hears_neither_the_measure_nor_the_aoi(self, catalog: None, source: Source, reader: Reader) -> None:
        async with _client(source) as client:
            await search(client, request({**WATER_AT_LEAST_50, "eo:cloud_cover": {"lte": 90}}, **{"earthx:evaluate": "pass"}))
        assert "query" not in source.bodies[0]
        assert "earthx" not in json.dumps(source.bodies)

    async def test_a_measure_and_a_property_filter_are_both_met_by_the_pass(
        self, catalog: None, source: Source, reader: Reader
    ) -> None:
        async with _client(source) as client:
            met = await search(client, request({**WATER_AT_LEAST_50, "eo:cloud_cover": {"lte": 25}}, **{"earthx:evaluate": "pass"}))
            missed = await search(client, request({**WATER_AT_LEAST_50, "eo:cloud_cover": {"lte": 20}}, **{"earthx:evaluate": "pass"}))
        assert found(met) == ["S2_0", "S2_1"] and found(missed) == []
        assert len(reader.passes) == 1, "a pass that fails the cheap question is not read"

    async def test_the_second_time_comes_from_the_cache(self, catalog: None, source: Source, reader: Reader) -> None:
        async with _client(source) as client:
            await search(client, request(WATER_AT_LEAST_50, **{"earthx:evaluate": "pass"}))
            before = len(reader.passes)
            again = await search(client, request(WATER_AT_LEAST_50, **{"earthx:evaluate": "pass"}))
        assert len(reader.passes) == before
        assert found(again) == ["S2_0", "S2_1"]

    async def test_a_pass_that_cannot_be_read_is_counted(self, catalog: None, source: Source, monkeypatch: pytest.MonkeyPatch) -> None:
        def broken(paths: list[Any], aoi: dict[str, Any], classes: frozenset[int]) -> AoiClouds:
            raise ValueError("no")

        monkeypatch.setattr(pass_filter, "measure_aoi_pass", broken)
        monkeypatch.setattr(aoi_cloud_filter, "measure_aoi_clouds", Reader().alone)
        async with _client(source) as client:
            response = await search(client, request(WATER_AT_LEAST_50, **{"earthx:evaluate": "pass"}))
        assert response.status_code == 200
        assert response.json()["earthx:aoi_filter"]["unreadable"] == 4  # the two passes of two scenes


class TestTheCoverage:
    async def test_per_scene_each_outline_decides(self, catalog: None, source: Source) -> None:
        """The AOI lies in 10.12..11.12 degrees. S2_0 covers 10.12..10.9 (78 %), S2_1 10.7..11.12 (100 % of the rest: 42 %)."""
        async with _client(source) as client:
            response = await search(client, request({"earthx:aoi_coverage": {"gte": 60}}, **{"earthx:evaluate": "scene"}))
        assert response.status_code == 200
        assert found(response) == ["S2_0", "S2_2", "S2_4"]
        assert "query" not in source.bodies[0], "the source is never asked the coverage"
        assert all("earthx" not in json.dumps(sent) for sent in source.bodies)

    async def test_per_pass_the_outlines_of_the_pass_together_decide(self, catalog: None, source: Source) -> None:
        """Gegenprobe: together S2_0 and S2_1 cover the whole AOI, so S2_1 stays with its pass."""
        async with _client(source) as client:
            response = await search(client, request({"earthx:aoi_coverage": {"gte": 60}}, **{"earthx:evaluate": "pass"}))
        assert found(response) == ["S2_0", "S2_1", "S2_2", "S2_3", "S2_4"]

    async def test_it_needs_no_date_range_and_no_pixel_is_read(self, catalog: None, source: Source) -> None:
        async with _client(source) as client:
            response = await search(client, request({"earthx:aoi_coverage": {"gte": 60}}, datetime=None))
        assert response.status_code == 200 and found(response) == ["S2_0", "S2_2", "S2_4"]

    async def test_a_measure_inside_the_aoi_still_needs_the_date_range(self, catalog: None, source: Source) -> None:
        async with _client(source) as client:
            response = await search(client, request({"earthx:aoi_cloud_cover": {"lte": 20}}, datetime=None))
        assert response.status_code == 400 and "date range" in response.json()["detail"]

    async def test_it_needs_an_area(self, catalog: None, source: Source) -> None:
        async with _client(source) as client:
            response = await search(client, request({"earthx:aoi_coverage": {"gte": 60}}, intersects=None))
        assert response.status_code == 400 and "area" in response.json()["detail"]

    @pytest.mark.parametrize("bad", [{"gte": 101}, {"gte": -1}, {"lte": "x"}, {"gt": 5}, {}])
    async def test_a_range_outside_0_to_100_is_a_400_without_the_value(self, catalog: None, source: Source, bad: dict) -> None:
        async with _client(source) as client:
            response = await search(client, request({"earthx:aoi_coverage": bad}))
        assert response.status_code == 400
        assert "101" not in response.text and "-1" not in response.json()["detail"]

    async def test_the_coverage_map_cannot_apply_it(self, catalog: None, source: Source) -> None:
        async with _client(source) as client:
            response = await client.get(f"/coverage/{S2}", params={"query": json.dumps({"earthx:aoi_coverage": {"gte": 50}})})
        assert response.status_code == 400

    async def test_a_dataset_that_does_not_offer_it_refuses_it(self, catalog: None, source: Source) -> None:
        plain = replace(SENTINEL_2_L2A, search_capabilities=SearchCapabilities(evaluate=False, aoi_coverage=False))
        other = build_app(DatasetRegistry((*(e for e in REGISTRY if e.dataset_id != S2), plain, TILES)))
        async with other.router.lifespan_context(other):
            other.state.earthx_gateway = Gateway(POLICY, transport=httpx.MockTransport(source.handler), resolve=_public)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=other), base_url="http://test") as client:
                response = await search(client, request({"earthx:aoi_coverage": {"gte": 50}}))
        assert response.status_code == 400 and "earthx:aoi_coverage" in response.json()["detail"]
        assert source.bodies == []


class TestAMaterializedDataset:
    """A dataset the platform holds itself (the elevation model's kind): outlines in pgstac, no pixels, no source."""

    def asked(self, minimum: float, **changes: Any) -> dict[str, Any]:
        body = {
            "collections": [TILES.dataset_id],
            "intersects": AOI,
            "limit": 100,
            "query_by_collection": {TILES.dataset_id: {"earthx:aoi_coverage": {"gte": minimum}}},
        }
        body.update(changes)
        return body

    async def test_per_scene_a_tile_that_covers_enough_of_the_aoi_alone_is_kept(self, catalog: None, source: Source) -> None:
        """Tiles 9..10, 10..11, 11..12, 12..13 degrees; the AOI lies in 10.12..11.12: 88 % in tile 10, 12 % in tile 11."""
        async with _client(source) as client:
            response = await search(client, self.asked(50))
        assert response.status_code == 200
        assert found(response) == ["t10"]
        assert response.json()["earthx:aoi_filter"]["checked"] >= 2

    async def test_a_lower_bound_keeps_both_halves(self, catalog: None, source: Source) -> None:
        async with _client(source) as client:
            response = await search(client, self.asked(10))
        assert found(response) == ["t10", "t11"]

    async def test_the_source_is_not_asked_for_a_dataset_of_the_platform(self, catalog: None, source: Source) -> None:
        async with _client(source) as client:
            await search(client, self.asked(50))
        assert source.bodies == []

    async def test_with_a_dataset_of_a_source_beside_it_each_answers_its_part(self, catalog: None, source: Source) -> None:
        async with _client(source) as client:
            response = await search(
                client,
                self.asked(
                    50,
                    collections=[S2, TILES.dataset_id],
                    query_by_collection={
                        TILES.dataset_id: {"earthx:aoi_coverage": {"gte": 50}},
                        S2: {"earthx:aoi_coverage": {"gte": 60}},
                    },
                ),
            )
        assert response.status_code == 200
        assert {"t10", "S2_0", "S2_2", "S2_4"} <= set(found(response))
        assert set(response.json()["earthx:aoi_filter_by_collection"]) == {S2, TILES.dataset_id}

    async def test_a_measure_on_it_is_refused_with_the_reason(self, catalog: None, source: Source) -> None:
        async with _client(source) as client:
            response = await search(
                client,
                self.asked(50, query_by_collection={TILES.dataset_id: {"earthx:aoi_cloud_cover": {"lte": 5}}}, datetime=PERIOD),
            )
        assert response.status_code == 400
