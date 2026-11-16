"""Steps on the tile below the first level (M5-10 part B, plan §11, G1–G4): the chain of the query runs on the picture of
the overview, its pyramid or its substitute, with the kernels of a job.

The rig of ``test_tiler_pyramid``: synthetic pyramid tiles in an in-process S3 and a double of the rows. ``RELIEF`` has a
pyramid from z7 down; ``TERRAIN`` stands in with RELIEF below z13, and names two bands of heights (G3).
"""

# The fixtures of test_tiler_pyramid are imported by name, and every test takes them as arguments of the same name.
# ruff: noqa: F811

from __future__ import annotations

import io
import json
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

import morecantile
import numpy
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from earthx.api import mosaic_tiles, overview_tiles
from earthx.api.tiler import _overview_names, build_app
from earthx.catalog.registry import DatasetRegistry, DefaultRender, ItemHolding, SearchCapabilities
from earthx.objectstore.overviews import upload_tile
from earthx.processing.overview import encode_tile, tile_image
from tests.earthx.access.test_mosaic_tiles import SEAM_X, TILE
from tests.earthx.api.test_tiler_mosaic import ZONE_32, Scenes, _serve
from tests.earthx.readers import mini_zarr

from ..objectstore.conftest import store, store_env  # noqa: F401 - fixtures
from .test_tiler_overview import WITH_POOL, Catalogue
from .test_tiler_pyramid import (  # noqa: F401 - fixtures
    _PLAIN,
    NODATA,
    RELIEF,
    RELIEF_ID,
    TERRAIN,
    TERRAIN_ID,
    TMS,
    VERSION,
    Pyramids,
    clock,
    path,
    pyramids,
    rows,
    stored_tile,
    tile_at,
)

BAND = RELIEF.default_render.assets[0]
CAPABLE = replace(RELIEF.capabilities, band_math=True, terrain=True)
RELIEF_STEPS = replace(RELIEF, capabilities=CAPABLE)
#: Two bands of heights in metres, as swissALTI3D has dtm and dtm_2m (G3); its standard view is the first.
TERRAIN_STEPS = replace(
    TERRAIN,
    capabilities=CAPABLE,
    band_units={**TERRAIN.band_units, "red": "m", BAND: "m"},
)
NO_TERRAIN = replace(
    RELIEF, dataset_id="synthetic-relief-plain", capabilities=replace(RELIEF.capabilities, terrain=False)
)
REGISTRY = DatasetRegistry((RELIEF_STEPS, TERRAIN_STEPS, _PLAIN))

DOUBLE = {"expression": f"{BAND} * 2", "name": "double"}
SLOPE = {"product": "slope", "bands": [BAND], "name": "slope", "slope_unit": "degrees"}


def _steps(*steps: tuple[str, int, dict], band: str | None = None) -> dict[str, Any]:
    query: dict[str, Any] = {"op": [], "op_version": [], "params": []}
    for op, version, params in steps:
        query["op"].append(op)
        query["op_version"].append(str(version))
        query["params"].append(json.dumps(params))
    if band is not None:
        query["band"] = band
    return query


def _array(response: Any) -> numpy.ma.MaskedArray:
    assert response.status_code == 200, response.text
    data = numpy.load(io.BytesIO(response.content))
    # The last band is the mask, cast: not 0 and 255 but a negative number where a float tile has no value.
    return numpy.ma.MaskedArray(data[:-1], mask=numpy.broadcast_to(data[-1] <= 0, data[:-1].shape))


def _put(pyramids: Pyramids, dataset: str, tile: morecantile.Tile, value: float) -> None:
    """A stored tile of one height everywhere, at ``tile``."""
    image = tile_image(numpy.ma.array(numpy.full((512, 512), value, dtype="float32")), tile, nodata=NODATA)
    target = pyramids.tmp_path / f"{dataset}-{tile.z}-{tile.x}-{tile.y}.tif"
    target.write_bytes(encode_tile(image))
    upload_tile(
        pyramids.store, dataset, VERSION, tile.z, tile.x, tile.y, target, checked_at=datetime(2026, 11, 14, tzinfo=UTC)
    )


@pytest.fixture
def api(rows, clock, store) -> Any:  # noqa: F811
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> Any:
        app.state.earthx_cache_pool = WITH_POOL
        app.state.earthx_overviews = overview_tiles.OverviewSources(store, clock=clock.monotonic, now=clock.wall)
        yield

    with TestClient(build_app(REGISTRY, lifespan=lifespan)) as client:
        yield client


class TestStepsOnThePyramid:
    def test_band_math_runs_on_the_values_of_the_pyramid(self, rows, pyramids, api) -> None:
        rows.ready(RELIEF_ID)
        pyramids.put(RELIEF_ID, 6)
        response = api.get(path(RELIEF_ID, 6), params={"tilesize": "512", **_steps(("band_math", 2, DOUBLE))})
        tile = _array(response)
        assert tile.shape == (1, 512, 512)
        assert tile[0, 100, 100] == 200 and tile[0, 100, 400] == 400
        assert tile.mask[0, :, :10].all()  # no value in the pyramid, none computed
        assert response.headers[mosaic_tiles.SOURCE_HEADER] == "overview"

    def test_without_steps_the_tile_is_as_before(self, rows, pyramids, api) -> None:
        rows.ready(RELIEF_ID)
        pyramids.put(RELIEF_ID, 6)
        tile = _array(api.get(path(RELIEF_ID, 6), params={"tilesize": "512"}))
        assert tile[0, 100, 100] == 100

    def test_a_slope_reads_the_stored_tiles_around_and_has_no_seam(self, rows, pyramids, api) -> None:
        rows.ready(RELIEF_ID)
        centre = tile_at(6)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                _put(pyramids, RELIEF_ID, morecantile.Tile(centre.x + dx, centre.y + dy, 6), 500.0)
        tile = _array(api.get(path(RELIEF_ID, 6), params=_steps(("terrain", 1, SLOPE))))
        assert tile.shape == (1, 256, 256)
        assert not tile.mask.any()  # the ring comes from the neighbours
        numpy.testing.assert_array_equal(tile, 0.0)
        assert len(pyramids.reads) == 9

    def test_the_ring_takes_the_values_of_the_neighbour_not_those_of_the_edge(self, rows, pyramids, api) -> None:
        """GDAL's bilinear reads past the edge of a file with the edge's value; the neighbour's real value has to win."""
        rows.ready(RELIEF_ID)
        centre = tile_at(6)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                _put(
                    pyramids, RELIEF_ID, morecantile.Tile(centre.x + dx, centre.y + dy, 6), 900.0 if dx == 1 else 500.0
                )
        tile = _array(api.get(path(RELIEF_ID, 6), params=_steps(("terrain", 1, SLOPE))))
        assert not tile.mask.any()
        assert (tile[0, 1:-1, -1] > 0).all()  # the step up into the eastern neighbour is seen at the edge
        numpy.testing.assert_array_equal(tile[0, :, :-2], 0.0)

    def test_a_neighbour_without_data_leaves_its_edge_empty(self, rows, pyramids, api) -> None:
        rows.ready(RELIEF_ID)
        _put(pyramids, RELIEF_ID, tile_at(6), 500.0)
        tile = _array(api.get(path(RELIEF_ID, 6), params=_steps(("terrain", 1, SLOPE))))
        assert (
            tile.mask[0, 0].all() and tile.mask[0, -1].all() and tile.mask[0, :, 0].all() and tile.mask[0, :, -1].all()
        )
        assert not tile.mask[0, 1:-1, 1:-1].any()

    @pytest.mark.parametrize("z", [0, 1])
    def test_a_slope_at_the_antimeridian_reads_no_neighbour_from_the_other_side(self, rows, pyramids, api, z) -> None:
        rows.ready(RELIEF_ID)
        side = 2**z
        for x in range(side):
            for y in range(side):
                _put(pyramids, RELIEF_ID, morecantile.Tile(x, y, z), 500.0)
        response = api.get(
            f"/collections/{RELIEF_ID}/overview/tiles/WebMercatorQuad/{z}/0/0.npy", params=_steps(("terrain", 1, SLOPE))
        )
        tile = _array(response)
        assert tile.mask[0, :, 0].all()  # the western edge of the world: no neighbour to read
        assert not tile.mask[0, 1:-1, 1:-1].any()

    def test_the_neighbours_are_kept_for_the_next_tile(self, rows, pyramids, api) -> None:
        rows.ready(RELIEF_ID)
        centre = tile_at(6)
        for dx in (-1, 0, 1):
            _put(pyramids, RELIEF_ID, morecantile.Tile(centre.x + dx, centre.y, 6), 500.0)
        api.get(path(RELIEF_ID, 6), params=_steps(("terrain", 1, SLOPE)))
        first = len(pyramids.reads)
        api.get(path(RELIEF_ID, 6), params=_steps(("terrain", 1, SLOPE)))
        assert len(pyramids.reads) == first + 1  # the tile itself; its eight neighbours from memory

    def test_the_hits_of_a_search_are_drawn_without_steps(self, rows, pyramids, api) -> None:
        response = api.get(
            f"/collections/{RELIEF_ID}/overview/{'a' * 32}/tiles/WebMercatorQuad/6/1/1.npy",
            params=_steps(("band_math", 2, DOUBLE)),
        )
        assert response.status_code == 400
        assert response.json()["detail"] == "the hits of a search are drawn without steps"
        assert pyramids.reads == [] and rows.asked == []


class TestStepsOnTheSubstitute:
    def test_the_bands_of_the_dataset_stand_for_the_band_of_the_stand_in(self, rows, pyramids, api) -> None:
        """G3: each band of TERRAIN in metres is RELIEF's one band, so a step may name either."""
        rows.ready(RELIEF_ID)
        pyramids.put(RELIEF_ID, 6)
        both = {"expression": f"red + {BAND}", "name": "sum"}
        response = api.get(path(TERRAIN_ID, 6), params={"tilesize": "512", **_steps(("band_math", 2, both))})
        tile = _array(response)
        assert response.headers[mosaic_tiles.SOURCE_HEADER] == "substitute"
        values = tile.compressed()
        assert set(numpy.unique(values)) <= {200.0, 400.0} and values.size > 0

    def test_a_slope_on_the_substitute_of_two_bands_of_heights_keeps_its_halo(self, rows, pyramids, api) -> None:
        """G3 with a focal step: the planner puts a selection of the band before the slope; the tile still reads its halo."""
        rows.ready(RELIEF_ID)
        centre = tile_at(6)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                _put(pyramids, RELIEF_ID, morecantile.Tile(centre.x + dx, centre.y + dy, 6), 500.0)
        tile = _array(api.get(path(TERRAIN_ID, 6), params=_steps(("terrain", 1, SLOPE))))
        assert tile.shape == (1, 256, 256)
        inside = ~tile.mask[0]
        assert inside.any()
        numpy.testing.assert_array_equal(tile[0][inside], 0.0)
        assert len(pyramids.reads) == 9  # the tile and its eight neighbours: the halo was read

    def test_the_names_are_those_with_the_unit_of_the_stand_in(self) -> None:
        names = _overview_names(TERRAIN_STEPS, RELIEF_STEPS)
        assert {name for name, _ in names} == {"red", BAND} and {unit for _, unit in names} == {"m"}
        assert _overview_names(RELIEF_STEPS, None) == ((BAND, "m"),)

    def test_a_band_of_another_unit_is_not_among_them(self, rows, pyramids, api) -> None:
        rows.ready(RELIEF_ID)
        pyramids.put(RELIEF_ID, 6)
        other = {"expression": "nir * 2", "name": "double"}
        response = api.get(path(TERRAIN_ID, 6), params=_steps(("band_math", 2, other)))
        assert response.status_code == 422
        assert "nir" in response.json()["detail"]
        assert pyramids.reads == []

    def test_the_files_of_the_stand_in_run_the_steps_too(self, tmp_path, monkeypatch, rows, pyramids, store) -> None:  # noqa: F811
        scenes = Scenes(tmp_path)
        catalogue = Catalogue(scenes)
        monkeypatch.setattr(mosaic_tiles, "search_items_in_bbox_async", catalogue.search)
        _serve(scenes, monkeypatch)
        scenes.add("WEST", ZONE_32, SEAM_X - 4000.0, 4000.0, 100)
        scenes.add("EAST", ZONE_32, SEAM_X, 4000.0, 200)
        files = replace(
            RELIEF_STEPS,
            source=replace(RELIEF.source, item_holding=ItemHolding.MATERIALIZED, source_collection_id=RELIEF_ID),
            coverage=replace(RELIEF.coverage, provider=RELIEF.coverage.provider.LOCAL_SQL),
            search_filters=(),
            search_capabilities=SearchCapabilities(evaluate=False, aoi_coverage=False),
        )
        wide = replace(TERRAIN_STEPS, spatial_extent=_PLAIN.spatial_extent)

        @asynccontextmanager
        async def lifespan(app: FastAPI) -> Any:
            app.state.earthx_cache_pool = WITH_POOL
            app.state.earthx_overviews = overview_tiles.OverviewSources(store)
            yield

        app = build_app(DatasetRegistry((files, wide, _PLAIN)), lifespan=lifespan)
        app.state.earthx_resolver = mini_zarr.from_memory
        base = f"/collections/{TERRAIN_ID}/overview/tiles/WebMercatorQuad/{TILE.z}/{TILE.x}/{TILE.y}.npy"
        with TestClient(app) as client:
            plain = _array(client.get(base))
            doubled = _array(client.get(base, params=_steps(("band_math", 2, DOUBLE))))
        both = ~plain.mask[0] & ~doubled.mask[0]
        assert both.any()
        numpy.testing.assert_array_equal(doubled[0][both], plain[0][both] * 2)


class TestWhatTheRouteRefuses:
    def test_a_band_without_steps_is_a_400(self, rows, pyramids, api) -> None:
        rows.ready(RELIEF_ID)
        response = api.get(path(RELIEF_ID, 6), params={"band": BAND})
        assert response.status_code == 400

    def test_a_step_the_dataset_does_not_allow_is_a_422_before_anything_is_read(
        self, rows, pyramids, store, clock
    ) -> None:  # noqa: F811
        rows.ready(NO_TERRAIN.dataset_id)

        @asynccontextmanager
        async def lifespan(app: FastAPI) -> Any:
            app.state.earthx_cache_pool = WITH_POOL
            app.state.earthx_overviews = overview_tiles.OverviewSources(store)
            yield

        with TestClient(build_app(DatasetRegistry((NO_TERRAIN, _PLAIN)), lifespan=lifespan)) as client:
            response = client.get(path(NO_TERRAIN.dataset_id, 6), params=_steps(("terrain", 1, SLOPE)))
        assert response.status_code == 422
        assert "does not allow terrain" in response.json()["detail"]
        assert pyramids.reads == [] and rows.asked == []

    def test_a_focal_step_after_another_is_a_422(self, rows, pyramids, api) -> None:
        rows.ready(RELIEF_ID)
        chained = _steps(("band_math", 2, DOUBLE), ("terrain", 1, {**SLOPE, "bands": ["double"]}))
        response = api.get(path(RELIEF_ID, 6), params=chained)
        assert response.status_code == 422
        assert "only as the first step" in response.json()["detail"]

    def test_a_band_the_steps_do_not_leave_is_a_422(self, rows, pyramids, api) -> None:
        rows.ready(RELIEF_ID)
        response = api.get(path(RELIEF_ID, 6), params=_steps(("band_math", 2, DOUBLE), band="nowhere"))
        assert response.status_code == 422
        assert "nowhere" in response.json()["detail"]

    def test_a_buffer_next_to_a_slope_is_a_400(self, rows, pyramids, api) -> None:
        rows.ready(RELIEF_ID)
        pyramids.put(RELIEF_ID, 6)
        response = api.get(path(RELIEF_ID, 6), params={"buffer": "2", **_steps(("terrain", 1, SLOPE))})
        assert response.status_code == 400

    def test_steps_are_not_a_way_to_reach_a_level_with_files(self, rows, pyramids, api) -> None:
        response = api.get(path(RELIEF_ID, 7), params=_steps(("band_math", 2, DOUBLE)))
        assert response.status_code == 400


def test_the_default_render_of_the_stand_in_names_its_band() -> None:
    assert isinstance(RELIEF.default_render, DefaultRender) and stored_tile(6)
