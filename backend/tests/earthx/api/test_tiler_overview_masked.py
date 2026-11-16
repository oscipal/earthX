"""The overview of the hits of a search: the picture below ``min_zoom`` masked to their footprints (adr/0032 Nachtrag 15.11.2026).

``POST /collections/{dataset}/overview/footprints`` stores the outlines of the hits as a selection of its own kind (no overpass,
no asset, one hit is enough) and ``GET /collections/{dataset}/overview/{selection}/tiles/...`` draws the pyramid of the dataset,
or the picture of its substitute, over those outlines only. The real app over synthetic data, as in ``test_tiler_pyramid``;
the store of the selections is the in-memory double of the mosaic tests.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import ExitStack, asynccontextmanager
from dataclasses import replace
from typing import Any

import numpy
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from shapely.geometry import box, mapping

from earthx.access.mosaic_tiles import TILE_GATE as mosaic_gate
from earthx.api import mosaic_tiles, overview_tiles
from earthx.api.tiler import build_app
from earthx.catalog.mosaic_selection import footprint_selection_id, selection_id
from earthx.catalog.pgstac import OverviewState
from earthx.catalog.registry import DatasetRegistry, ItemHolding, SearchCapabilities
from earthx.objectstore.results import Store
from tests.earthx.access.test_mosaic_tiles import SEAM_X, TO_4326
from tests.earthx.api.mosaic_selections import MemorySelections, batch_source_of
from tests.earthx.api.test_tiler_overview import WITH_POOL
from tests.earthx.readers import mini_zarr

from ..objectstore.conftest import store, store_env  # noqa: F401 - fixtures
from .test_tiler_pyramid import (
    _PLAIN,
    EXTENT,
    PROTO_ID,
    PROTOTYPE,
    RELIEF,
    RELIEF_ID,
    TERRAIN,
    TERRAIN_ID,
    TMS,
    Clock,
    FilesRig,
    Pyramids,
    Rows,
    alpha,
    array,
    clock,  # noqa: F401 - fixtures
    files_rig,  # noqa: F401, F811
    pyramids,  # noqa: F401
    rows,  # noqa: F401
    tile_at,
)


def _materialized(config: Any) -> Any:
    return replace(
        config,
        source=replace(config.source, item_holding=ItemHolding.MATERIALIZED, source_collection_id=config.dataset_id),
        coverage=replace(config.coverage, provider=config.coverage.provider.LOCAL_SQL),
        search_filters=(),
        search_capabilities=SearchCapabilities(evaluate=False, aoi_coverage=False),
    )


HELD_RELIEF, HELD_TERRAIN, HELD_PROTO = _materialized(RELIEF), _materialized(TERRAIN), _materialized(PROTOTYPE)
REGISTRY = DatasetRegistry((HELD_RELIEF, HELD_TERRAIN, HELD_PROTO, _PLAIN))


def hit(item_id: str, west: float, south: float, east: float, north: float, **properties: Any) -> dict[str, Any]:
    return {
        "id": item_id,
        "type": "Feature",
        "bbox": [west, south, east, north],
        "geometry": mapping(box(west, south, east, north)),
        "properties": properties,
    }


def left_half(z: int) -> tuple[float, float, float, float]:
    """The west half of the tile at ``z`` over the test area, in lon/lat."""
    west, south, east, north = TMS.bounds(tile_at(z))
    return west, south, (west + east) / 2, north


class Rig:
    """The app with the stores of the selections and the hits' items, and the clients it made."""

    def __init__(self, store_: Store, clock_: Clock) -> None:
        self.store = store_
        self.clock = clock_
        self.selections = MemorySelections()
        self.asked: list[list[str]] = []
        self.items: dict[str, dict[str, Any]] = {}
        self.stack = ExitStack()

    def client(self, *, pool: Any = WITH_POOL, selections: Any = "default", sources_: Any = "default") -> TestClient:
        @asynccontextmanager
        async def lifespan(app: FastAPI) -> Any:
            app.state.earthx_cache_pool = pool
            app.state.earthx_item_batches = batch_source_of(self.items, self.asked)
            app.state.earthx_mosaic_selections = self.selections if selections == "default" else selections
            app.state.earthx_overviews = (
                overview_tiles.OverviewSources(self.store, clock=self.clock.monotonic, now=self.clock.wall)
                if sources_ == "default"
                else sources_
            )
            yield

        return self.stack.enter_context(TestClient(build_app(REGISTRY, lifespan=lifespan)))

    def create(self, api: TestClient, dataset: str, *ids: str) -> str:
        response = api.post(f"/collections/{dataset}/overview/footprints", json={"items": list(ids)})
        assert response.status_code in (200, 201), response.text
        return response.json()["id"]


@pytest.fixture
def rig(store: Store, clock: Clock) -> Iterator[Rig]:  # noqa: F811
    rig = Rig(store, clock)
    with rig.stack:
        yield rig


def masked_path(dataset: str, selection: str, z: int, *, extension: str = "npy", x: int | None = None, y: int | None = None) -> str:
    tile = tile_at(z)
    return (
        f"/collections/{dataset}/overview/{selection}/tiles/WebMercatorQuad/{z}/{tile.x if x is None else x}/"
        f"{tile.y if y is None else y}.{extension}"
    )


class TestCreatingTheFootprintSelection:
    def test_one_hit_is_enough_and_the_answer_names_the_id_and_the_tiles(self, rig: Rig) -> None:
        rig.items["a"] = hit("a", *left_half(6))
        response = rig.client().post(f"/collections/{RELIEF_ID}/overview/footprints", json={"items": ["a"]})
        assert response.status_code == 201
        body = response.json()
        assert body["id"] == footprint_selection_id(RELIEF_ID, ["a"])
        assert body["tiles"] == f"/collections/{RELIEF_ID}/overview/{body['id']}/tiles/WebMercatorQuad/{{z}}/{{x}}/{{y}}"
        assert rig.selections.rows[body["id"]][1]["kind"] == "footprints"

    def test_the_hits_of_different_overpasses_are_one_selection(self, rig: Rig) -> None:
        rig.items["a"] = hit("a", *left_half(6), start_datetime="2020-01-01T00:00:00Z")
        rig.items["b"] = hit("b", 10.0, 40.0, 11.0, 41.0, start_datetime="2021-01-01T00:00:00Z")
        assert rig.client().post(f"/collections/{RELIEF_ID}/overview/footprints", json={"items": ["a", "b"]}).status_code == 201

    def test_the_same_hits_in_any_order_are_the_same_id_and_the_second_creation_renews_it(self, rig: Rig) -> None:
        rig.items["a"], rig.items["b"] = hit("a", *left_half(6)), hit("b", 10.0, 40.0, 11.0, 41.0)
        api = rig.client()
        first = rig.create(api, RELIEF_ID, "a", "b")
        before = len(rig.asked)
        response = api.post(f"/collections/{RELIEF_ID}/overview/footprints", json={"items": ["b", "a"]})
        assert response.status_code == 200 and response.json()["id"] == first
        assert rig.selections.renewed == [first] and len(rig.asked) == before, "renewed, and no item fetched again"

    def test_another_dataset_or_other_hits_are_another_id_and_a_mosaic_selection_never_has_it(self) -> None:
        assert len({footprint_selection_id("x", ["a"]), footprint_selection_id("y", ["a"]), footprint_selection_id("x", ["a", "b"])}) == 3
        assert footprint_selection_id("x", ["a", "b"]) != selection_id("x", ["data"], ["a", "b"])

    def test_the_outlines_come_from_our_catalogue_and_nothing_is_asked_of_a_source(self, rig: Rig) -> None:
        rig.items["a"] = hit("a", *left_half(6))
        rig.create(rig.client(), RELIEF_ID, "a")
        assert rig.asked == [["a"]]  # the batch source of a materialized dataset is pgstac

    @pytest.mark.parametrize(
        ("body", "status"),
        [
            ({"items": []}, 400),
            ({"items": ["a", "a"]}, 400),
            ({"items": ["has a space"]}, 400),
            ({"items": [f"hit-{n}" for n in range(mosaic_tiles.MAX_FOOTPRINT_ITEMS + 1)]}, 400),
            ({"items": ["a"], "assets": ["data"]}, 422),
            ({"items": "a"}, 422),
            ({}, 422),
            ({"items": ["missing"]}, 404),
        ],
        ids=["none", "twice", "shape", "too many", "an asset is no field", "no list", "no field", "unknown item"],
    )
    def test_a_selection_that_is_none_is_refused_with_the_rule_and_no_selection_is_kept(self, rig: Rig, body: dict, status: int) -> None:
        rig.items["a"] = hit("a", *left_half(6))
        response = rig.client().post(f"/collections/{RELIEF_ID}/overview/footprints", json=body)
        assert response.status_code == status, response.text
        assert rig.selections.rows == {}

    def test_a_body_larger_than_the_limit_is_413_before_it_is_read(self, rig: Rig) -> None:
        big = json.dumps({"items": ["a" * 200] * 400})
        assert len(big) > mosaic_tiles.MAX_FOOTPRINT_BODY_BYTES
        response = rig.client().post(f"/collections/{RELIEF_ID}/overview/footprints", content=big, headers={"content-type": "application/json"})
        assert response.status_code == 413

    def test_a_dataset_that_draws_nothing_below_its_first_level_has_no_footprints(self, rig: Rig) -> None:
        rig.items["a"] = hit("a", *left_half(6))
        response = rig.client().post(f"/collections/{_PLAIN.dataset_id}/overview/footprints", json={"items": ["a"]})
        assert response.status_code == 404 and rig.selections.rows == {}

    def test_a_federated_dataset_is_501_it_would_ask_a_source(self, rig: Rig) -> None:
        federated = DatasetRegistry((RELIEF, _PLAIN))
        rig.items["a"] = hit("a", *left_half(6))

        @asynccontextmanager
        async def lifespan(app: FastAPI) -> Any:
            app.state.earthx_cache_pool = WITH_POOL
            app.state.earthx_item_batches = batch_source_of(rig.items, rig.asked)
            app.state.earthx_mosaic_selections = rig.selections
            yield

        with TestClient(build_app(federated, lifespan=lifespan)) as api:
            assert api.post(f"/collections/{RELIEF_ID}/overview/footprints", json={"items": ["a"]}).status_code == 501
        assert rig.asked == []

    def test_a_hit_without_an_outline_is_a_502_and_not_kept(self, rig: Rig) -> None:
        rig.items["a"] = {"id": "a", "type": "Feature", "properties": {}}
        assert rig.client().post(f"/collections/{RELIEF_ID}/overview/footprints", json={"items": ["a"]}).status_code == 502
        assert rig.selections.rows == {}

    def test_without_the_catalogue_database_it_is_a_503(self, rig: Rig) -> None:
        rig.items["a"] = hit("a", *left_half(6))
        assert rig.client(pool=None, selections=None).post(f"/collections/{RELIEF_ID}/overview/footprints", json={"items": ["a"]}).status_code == 503


class TestTheMaskedTileOfAPyramid:
    def _ready(self, rig: Rig, rows: Rows, pyramids: Pyramids, *datasets: str, z: int = 6) -> str:  # noqa: F811
        rows.ready(*datasets)
        for dataset in datasets:
            pyramids.put(dataset, z)
        rig.items["a"] = hit("a", *left_half(z))
        return "a"

    def test_the_picture_is_there_over_the_footprints_and_transparent_elsewhere(self, rig, rows, pyramids) -> None:  # noqa: F811
        self._ready(rig, rows, pyramids, RELIEF_ID)
        api = rig.client()
        selection = rig.create(api, RELIEF_ID, "a")
        response = api.get(masked_path(RELIEF_ID, selection, 6, extension="png"), params={"tilesize": "512", "rescale": "0,255"})
        shown = alpha(response)
        assert (shown[:, 20:240] == 255).all(), "over the footprint: the picture"
        assert (shown[:, 280:] == 0).all(), "outside it: transparent"
        assert response.headers[mosaic_tiles.SOURCE_HEADER] == overview_tiles.OVERVIEW_SOURCE

    def test_the_values_over_the_footprints_are_those_of_the_pyramid(self, rig, rows, pyramids) -> None:  # noqa: F811
        self._ready(rig, rows, pyramids, RELIEF_ID)
        api = rig.client()
        selection = rig.create(api, RELIEF_ID, "a")
        tile = array(api.get(masked_path(RELIEF_ID, selection, 6), params={"tilesize": "512"}))
        whole = array(api.get(f"/collections/{RELIEF_ID}/overview/tiles/WebMercatorQuad/6/{tile_at(6).x}/{tile_at(6).y}.npy", params={"tilesize": "512"}))
        assert tile[0, 100, 100] == whole[0, 100, 100] == 100

    def test_a_tile_over_none_of_the_hits_is_a_404_before_the_object_or_its_row_is_read(self, rig, rows, pyramids) -> None:  # noqa: F811
        self._ready(rig, rows, pyramids, RELIEF_ID)
        rig.items["far"] = hit("far", -101.0, 39.0, -100.0, 40.0)
        api = rig.client()
        selection = rig.create(api, RELIEF_ID, "far")
        response = api.get(masked_path(RELIEF_ID, selection, 6))
        assert response.status_code == 404 and "outside the footprints" in response.json()["detail"]
        assert pyramids.reads == [] and rows.asked == []

    def test_the_same_url_gives_the_same_picture_whoever_asks(self, rig, rows, pyramids) -> None:  # noqa: F811
        self._ready(rig, rows, pyramids, RELIEF_ID)
        selection = rig.create(rig.client(), RELIEF_ID, "a")
        first, second = (rig.client().get(masked_path(RELIEF_ID, selection, 6, extension="png")) for _ in range(2))
        assert first.status_code == 200 and first.content == second.content

    def test_a_pyramid_that_is_not_ready_is_the_404_that_says_why(self, rig, rows, pyramids) -> None:  # noqa: F811
        rig.items["a"] = hit("a", *left_half(6))
        rows.states[RELIEF_ID] = OverviewState("building")
        api = rig.client()
        response = api.get(masked_path(RELIEF_ID, rig.create(api, RELIEF_ID, "a"), 6))
        assert response.status_code == 404 and response.headers[overview_tiles.OVERVIEW_HEADER] == "building"

    @pytest.mark.parametrize("z", [7, 9])
    def test_a_level_from_the_first_level_on_is_a_400(self, rig, rows, pyramids, z: int) -> None:  # noqa: F811
        rig.items["a"] = hit("a", *left_half(6))
        api = rig.client()
        assert api.get(masked_path(RELIEF_ID, rig.create(api, RELIEF_ID, "a"), z)).status_code == 400

    def test_a_free_expression_is_refused_as_on_every_tile(self, rig, rows, pyramids) -> None:  # noqa: F811
        rig.items["a"] = hit("a", *left_half(6))
        api = rig.client()
        assert api.get(masked_path(RELIEF_ID, rig.create(api, RELIEF_ID, "a"), 6), params={"expression": "b1*2"}).status_code == 400

    def test_the_pyramid_tile_waits_at_the_gate_of_the_pyramids(self, rig, rows, pyramids) -> None:  # noqa: F811
        from earthx.access import overview_tiles as access_overview
        from earthx.access.mosaic_tiles import TILE_GATE

        self._ready(rig, rows, pyramids, RELIEF_ID)
        seen = {"mosaic": 0, "pyramid": 0}
        for name, gate in (("mosaic", TILE_GATE), ("pyramid", access_overview.PYRAMID_GATE)):
            original = gate.enter

            async def counting(gone, _name=name, _original=original):
                seen[_name] += 1
                return await _original(gone)

            gate.enter = counting  # type: ignore[method-assign]
        try:
            api = rig.client()
            assert api.get(masked_path(RELIEF_ID, rig.create(api, RELIEF_ID, "a"), 6)).status_code == 200
        finally:
            for gate in (TILE_GATE, access_overview.PYRAMID_GATE):
                del gate.enter
        assert seen == {"mosaic": 0, "pyramid": 1}


class TestAnIdThatIsNoSelection:
    def test_an_id_nobody_created_is_gone_410_and_says_how_to_create_it(self, rig, rows, pyramids) -> None:  # noqa: F811
        rows.ready(RELIEF_ID)
        response = rig.client().get(masked_path(RELIEF_ID, "0" * 32, 6))
        assert response.status_code == 410 and "overview/footprints" in response.json()["detail"]
        assert pyramids.reads == [] and rows.asked == []

    def test_an_expired_selection_is_gone_the_same_way_and_creating_it_again_gives_the_same_url(self, rig, rows, pyramids) -> None:  # noqa: F811
        rows.ready(RELIEF_ID)
        pyramids.put(RELIEF_ID, 6)
        rig.items["a"] = hit("a", *left_half(6))
        api = rig.client()
        selection = rig.create(api, RELIEF_ID, "a")
        rig.selections.expire(selection)
        assert api.get(masked_path(RELIEF_ID, selection, 6)).status_code == 410
        assert rig.create(api, RELIEF_ID, "a") == selection
        assert api.get(masked_path(RELIEF_ID, selection, 6)).status_code == 200

    @pytest.mark.parametrize("bad", ["short", "G" * 32, "A" * 32, "0" * 33])
    def test_an_id_of_the_wrong_shape_is_a_400_before_anything_is_looked_up(self, rig, bad: str) -> None:
        api = rig.client()
        assert api.get(masked_path(RELIEF_ID, bad, 6)).status_code == 400

    def test_the_selection_of_another_dataset_is_a_404(self, rig, rows, pyramids) -> None:  # noqa: F811
        rig.items["a"] = hit("a", *left_half(6))
        api = rig.client()
        selection = rig.create(api, RELIEF_ID, "a")
        assert api.get(masked_path(PROTO_ID, selection, 6)).status_code == 404

    def test_a_mosaic_selection_is_no_footprint_selection_and_the_other_way_round(self, rig, rows, pyramids) -> None:  # noqa: F811
        rig.items["a"] = hit("a", *left_half(6))
        api = rig.client()
        footprints = rig.create(api, RELIEF_ID, "a")
        rig.selections.rows["1" * 32] = (RELIEF_ID, {"dataset": RELIEF_ID, "assets": ["data"], "items": ["a", "b"], "order": [], "outlines": {}, "bounds": [0, 0, 1, 1], "described": {}})
        assert api.get(masked_path(RELIEF_ID, "1" * 32, 6)).status_code == 410
        mosaic_path = f"/collections/{RELIEF_ID}/mosaic/{footprints}/tiles/WebMercatorQuad/10/0/0.npy"
        assert api.get(mosaic_path).status_code == 410

    def test_without_the_catalogue_database_the_tile_is_a_503(self, rig) -> None:
        assert rig.client(pool=None, selections=None).get(masked_path(RELIEF_ID, "0" * 32, 6)).status_code == 503

    def test_a_dataset_without_a_pyramid_or_a_substitute_is_a_404(self, rig) -> None:
        assert rig.client().get(masked_path(_PLAIN.dataset_id, "0" * 32, 6)).status_code == 404


class TestAPrototypeSourceIsNeverKept:
    @pytest.mark.parametrize("case", ["picture", "outside", "gone", "building"])
    def test_every_answer_is_private_no_store(self, rig, rows, pyramids, case: str) -> None:  # noqa: F811
        rig.items["a"] = hit("a", *left_half(6))
        rig.items["far"] = hit("far", -101.0, 39.0, -100.0, 40.0)
        rows.ready(PROTO_ID)
        pyramids.put(PROTO_ID, 6)
        if case == "building":
            rows.states[PROTO_ID] = OverviewState("building")
        api = rig.client()
        selection = rig.create(api, PROTO_ID, "far" if case == "outside" else "a")
        target = "0" * 32 if case == "gone" else selection
        response = api.get(masked_path(PROTO_ID, target, 6))
        assert response.status_code == {"picture": 200, "outside": 404, "gone": 410, "building": 404}[case]
        assert response.headers["cache-control"] == "private, no-store"

    def test_a_regular_source_is_not(self, rig, rows, pyramids) -> None:  # noqa: F811
        rows.ready(RELIEF_ID)
        pyramids.put(RELIEF_ID, 6)
        rig.items["a"] = hit("a", *left_half(6))
        api = rig.client()
        assert "no-store" not in api.get(masked_path(RELIEF_ID, rig.create(api, RELIEF_ID, "a"), 6)).headers.get("cache-control", "")


class TestTheSubstituteOverTheHits:
    """swissALTI3D's hits: GLO-30's pyramid below z7, cut to the extent of swissALTI3D and to the hits."""

    @staticmethod
    def _expected(z: int, hits: tuple[float, float, float, float]) -> numpy.ndarray:
        """The pixels of the tile at ``z`` that lie in the extent of TERRAIN and in the hits (centres, as the route cuts)."""
        left, bottom, right, top = TMS.xy_bounds(tile_at(z))
        columns = left + (numpy.arange(512) + 0.5) * (right - left) / 512
        rows_ = top - (numpy.arange(512) + 0.5) * (top - bottom) / 512

        def box_of(west: float, south: float, east: float, north: float) -> numpy.ndarray:
            (w, s_), (e, n) = TMS.xy(west, south), TMS.xy(east, north)
            return ((columns >= w) & (columns <= e))[None, :] & ((rows_ >= s_) & (rows_ <= n))[:, None]

        return box_of(*EXTENT) & box_of(*hits)

    def test_the_stand_in_s_pyramid_is_masked_to_the_hits_and_says_substitute(self, rig, rows, pyramids) -> None:  # noqa: F811
        rows.ready(RELIEF_ID)
        pyramids.put(RELIEF_ID, 5)
        # The hits cover the part of the tile east of 8.0 degrees, which lies inside the extent of TERRAIN (7 to 9).
        west, south, east, north = TMS.bounds(tile_at(5))
        hits = (8.0, south, east, north)
        rig.items["t"] = hit("t", *hits)
        api = rig.client()
        selection = rig.create(api, TERRAIN_ID, "t")
        response = api.get(masked_path(TERRAIN_ID, selection, 5, extension="png"), params={"tilesize": "512", "rescale": "0,255"})
        shown = alpha(response) != 0
        expected = self._expected(5, hits)
        assert response.headers[mosaic_tiles.SOURCE_HEADER] == mosaic_tiles.SUBSTITUTE_SOURCE
        assert [dataset for dataset, _ in rows.asked] == [RELIEF_ID]
        assert expected.any() and (~expected).any()
        assert not shown[~expected].any(), "nothing beyond the hits or the extent"
        assert shown[expected].mean() > 0.9

    def test_a_tile_over_none_of_the_hits_is_a_404_before_anything_is_asked(self, rig, rows, pyramids) -> None:  # noqa: F811
        rows.ready(RELIEF_ID)
        rig.items["t"] = hit("t", 7.0, 46.0, 7.1, 46.1)
        api = rig.client()
        selection = rig.create(api, TERRAIN_ID, "t")
        far = TMS.tile(-100.0, 40.0, 6)
        assert api.get(masked_path(TERRAIN_ID, selection, 6, x=far.x, y=far.y)).status_code == 404
        assert rows.asked == [] and pyramids.reads == []

    def test_hits_outside_the_extent_of_the_dataset_leave_nothing_to_draw_a_404_before_anything_is_asked(
        self, rig, rows, pyramids  # noqa: F811
    ) -> None:
        rows.ready(RELIEF_ID)
        pyramids.put(RELIEF_ID, 5)
        west, south, east, _ = TMS.bounds(tile_at(5))
        rig.items["t"] = hit("t", west, south, west + 1.0, south + 1.0)  # in the tile, west of the extent
        api = rig.client()
        response = api.get(masked_path(TERRAIN_ID, rig.create(api, TERRAIN_ID, "t"), 5))
        assert response.status_code == 404 and rows.asked == [] and pyramids.reads == []


class TestTheFilesOfTheSubstituteOverTheHits:
    """Below z7 without a pyramid to read (and from z7 on) the stand-in's files are read; the picture is masked to the hits."""

    def _client(self, files: FilesRig, selections: MemorySelections, items: dict[str, dict[str, Any]]) -> TestClient:
        wide = _materialized(files.wide)

        @asynccontextmanager
        async def lifespan(app: FastAPI) -> Any:
            app.state.earthx_cache_pool = WITH_POOL
            app.state.earthx_item_batches = batch_source_of(items)
            app.state.earthx_mosaic_selections = selections
            app.state.earthx_overviews = overview_tiles.OverviewSources(files.store)
            yield

        app = build_app(DatasetRegistry((files.files, wide, _PLAIN)), lifespan=lifespan)
        app.state.earthx_resolver = mini_zarr.from_memory
        return files.stack.enter_context(TestClient(app))

    @staticmethod
    def _around_the_scenes(margin: float) -> tuple[float, float, float, float]:
        lon, lat = TO_4326.transform(604_000.0, 5_698_500.0)
        return lon - margin, lat - margin, lon + margin, lat + margin

    def _tile(self, api: TestClient, selection: str | None) -> Any:
        tile = TMS.tile(*TO_4326.transform(604_000.0, 5_698_500.0), 6)
        prefix = f"/collections/{TERRAIN_ID}/overview" + ("" if selection is None else f"/{selection}")
        return api.get(f"{prefix}/tiles/WebMercatorQuad/6/{tile.x}/{tile.y}.png", params={"tilesize": "512", "rescale": "0,255"})

    def test_the_files_over_the_hits_are_the_picture_and_the_catalogue_is_asked_only_over_the_hits(
        self, files_rig, rows, pyramids  # noqa: F811
    ) -> None:
        rows.states[RELIEF_ID] = OverviewState("none")
        items = {"t": hit("t", *self._around_the_scenes(0.2))}
        selections = MemorySelections()
        api = self._client(files_rig, selections, items)
        selection = api.post(f"/collections/{TERRAIN_ID}/overview/footprints", json={"items": ["t"]}).json()["id"]
        whole = alpha(self._tile(api, None))
        files_rig.catalogue.asked.clear()
        masked_response = self._tile(api, selection)
        masked = alpha(masked_response)
        assert masked_response.headers[mosaic_tiles.SOURCE_HEADER] == mosaic_tiles.SUBSTITUTE_SOURCE
        assert {"EAST", "WEST"} <= set(files_rig.scenes.opened)
        ((_, (west, south, east, north), _),) = files_rig.catalogue.asked
        hits = self._around_the_scenes(0.2)
        assert hits[0] - 1e-9 <= west and east <= hits[2] + 1e-9 and hits[1] - 1e-9 <= south and north <= hits[3] + 1e-9, (
            "the catalogue is asked over the hits, not over the whole tile"
        )
        assert (masked != 0).any() and (masked != 0).sum() <= (whole != 0).sum()

    def test_the_files_east_of_a_seam_are_drawn_and_those_west_of_it_are_not_when_the_hits_lie_east_of_it(
        self, files_rig, rows, pyramids  # noqa: F811
    ) -> None:
        rows.states[RELIEF_ID] = OverviewState("none")
        seam_lon, seam_lat = TO_4326.transform(SEAM_X, 5_698_500.0)
        items = {"t": hit("t", seam_lon, seam_lat - 0.1, seam_lon + 0.1, seam_lat + 0.1)}
        api = self._client(files_rig, MemorySelections(), items)
        selection = api.post(f"/collections/{TERRAIN_ID}/overview/footprints", json={"items": ["t"]}).json()["id"]
        tile = TMS.tile(seam_lon, seam_lat, 12)
        left, _, right, _ = TMS.xy_bounds(tile)
        seam_x, _ = TMS.xy(seam_lon, seam_lat)
        seam_column = int((seam_x - left) / (right - left) * 512)
        params = {"tilesize": "512", "rescale": "0,255"}
        base = f"/collections/{TERRAIN_ID}/overview"
        tail = f"tiles/WebMercatorQuad/12/{tile.x}/{tile.y}.png"
        whole = alpha(api.get(f"{base}/{tail}", params=params)) != 0
        masked = alpha(api.get(f"{base}/{selection}/{tail}", params=params)) != 0
        assert whole[:, : seam_column - 5].any() and whole[:, seam_column + 5 :].any(), "the files lie on both sides of the seam"
        assert not masked[:, : seam_column - 5].any(), "west of the hits: transparent"
        assert masked[:, seam_column + 5 :].any(), "over the hits: the picture"

    def test_hits_elsewhere_in_the_tile_leave_the_files_picture_transparent(self, files_rig, rows, pyramids) -> None:  # noqa: F811
        rows.states[RELIEF_ID] = OverviewState("none")
        lon, lat = TO_4326.transform(604_000.0, 5_698_500.0)
        items = {"t": hit("t", lon + 2.0, lat + 1.0, lon + 2.5, lat + 1.5)}
        api = self._client(files_rig, MemorySelections(), items)
        selection = api.post(f"/collections/{TERRAIN_ID}/overview/footprints", json={"items": ["t"]}).json()["id"]
        response = self._tile(api, selection)
        assert response.status_code in (200, 404)
        if response.status_code == 200:
            assert not (alpha(response) != 0).any()

    def test_the_file_reads_wait_at_the_gate_of_the_mosaic(self, files_rig, rows) -> None:  # noqa: F811
        from earthx.access import overview_tiles as access_overview

        rows.states[RELIEF_ID] = OverviewState("none")
        seen = {"mosaic": 0, "pyramid": 0}
        for name, gate in (("mosaic", mosaic_gate), ("pyramid", access_overview.PYRAMID_GATE)):
            original = gate.enter

            async def counting(gone, _name=name, _original=original):
                seen[_name] += 1
                return await _original(gone)

            gate.enter = counting  # type: ignore[method-assign]
        try:
            api = self._client(files_rig, MemorySelections(), {"t": hit("t", *self._around_the_scenes(0.2))})
            selection = api.post(f"/collections/{TERRAIN_ID}/overview/footprints", json={"items": ["t"]}).json()["id"]
            assert self._tile(api, selection).status_code == 200
        finally:
            for gate in (mosaic_gate, access_overview.PYRAMID_GATE):
                del gate.enter
        assert seen == {"mosaic": 1, "pyramid": 0}
