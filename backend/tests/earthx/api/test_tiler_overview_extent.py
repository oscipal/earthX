"""swissALTI3D shows an image at every level z0-z12 through its substitute (plan M5-30b §8.8, finding of 13.11.2026).

Below z13 the picture is Copernicus GLO-30. A tile of a low level touches hundreds of its 1 degree files, and the
tile reads at most `TILE_FILE_BUDGET` of them: if they are chosen over the whole tile and not over the extent of the
dataset, they can all lie outside it and the tile over the dataset is empty. The items here are 1 degree cells of a
large area in the order of their ids, the first of which lie far from the dataset, and the catalogue double
filters by rectangle and cuts at the limit as pgstac does.
"""

from __future__ import annotations

import io
from collections.abc import Callable, Iterator
from contextlib import ExitStack, asynccontextmanager
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy
import pytest
import rasterio
from fastapi import FastAPI
from fastapi.testclient import TestClient
from rasterio.transform import from_origin
from shapely.geometry import box, mapping

from earthx.api import mosaic_tiles
from earthx.api.tiler import build_app
from earthx.catalog.registry import DatasetRegistry
from tests.catalog.entries import COP_DEM_GLO_30, SWISSALTI3D
from tests.earthx.access.test_mosaic_tiles import TMS
from tests.earthx.api.test_tiler_mosaic import Scenes, _serve
from tests.earthx.api.test_tiler_overview import WITH_POOL
from tests.earthx.processing import sources
from tests.earthx.readers import mini_zarr

SURFACE = replace(COP_DEM_GLO_30, source=replace(COP_DEM_GLO_30.source, asset_hosts=(sources.HOST,)))
TERRAIN = replace(SWISSALTI3D, source=replace(SWISSALTI3D.source, asset_hosts=(sources.HOST,)))
REGISTRY = DatasetRegistry((TERRAIN, SURFACE))
BASE = f"/collections/{TERRAIN.dataset_id}/overview"
ASSET = SURFACE.default_render.assets[0]  # type: ignore[union-attr]

#: The cells of the substitute that are held: 1 degree each, over an area far larger than the dataset.
WEST, EAST, SOUTH, NORTH = -4, 26, 38, 58
CELL_PIXELS = 8
#: Where the dataset lies: its centre, and a point in the cell that holds it.
CENTRE = (sum(TERRAIN.spatial_extent.bbox[0::2]) / 2, sum(TERRAIN.spatial_extent.bbox[1::2]) / 2)


def _cell_id(west: int, south: int) -> str:
    return f"CELL_N{south:02d}_E{west + 10:03d}"


def _cell_file(path: Path, west: int, south: int) -> Path:
    profile = {
        "driver": "GTiff", "dtype": "uint8", "count": 1, "height": CELL_PIXELS, "width": CELL_PIXELS, "crs": "EPSG:4326",
        "transform": from_origin(west, south + 1, 1 / CELL_PIXELS, 1 / CELL_PIXELS), "nodata": 0,
    }  # fmt: skip
    with rasterio.open(path, "w", **profile) as destination:
        destination.write(numpy.full((1, CELL_PIXELS, CELL_PIXELS), 100, dtype="uint8"))
    return path


def _cell_item(west: int, south: int) -> dict[str, Any]:
    item_id = _cell_id(west, south)
    return {
        "id": item_id,
        "type": "Feature",
        "bbox": [west, south, west + 1, south + 1],
        "geometry": mapping(box(west, south, west + 1, south + 1)),
        "properties": {"proj:code": "EPSG:4326", "datetime": "2021-01-01T00:00:00Z"},
        "assets": {ASSET: {"href": sources.url(f"{item_id}-{ASSET}")}},
    }


class Pgstac:
    """The pgstac search as a double: items whose bbox meets the rectangle, in the order they were stored, cut at the limit."""

    def __init__(self, scenes: Scenes) -> None:
        self.scenes = scenes
        self.asked: list[tuple[str, tuple[float, float, float, float], int]] = []

    async def search(self, conn: Any, dataset_id: str, bbox: tuple[float, float, float, float], limit: int) -> list[Any]:
        self.asked.append((dataset_id, tuple(bbox), limit))
        west, south, east, north = bbox
        meets = [
            item
            for item in self.scenes.items.values()
            if item["bbox"][0] <= east and item["bbox"][2] >= west and item["bbox"][1] <= north and item["bbox"][3] >= south
        ]
        return [dict(item, collection=dataset_id) for item in meets][:limit]


@pytest.fixture(scope="module")
def cells(tmp_path_factory: pytest.TempPathFactory) -> tuple[dict[str, dict[str, Any]], dict[str, Path]]:
    """Several hundred 1 degree cells with a file each, stored by the id of the item: the ones of the south first."""
    root = tmp_path_factory.mktemp("cells")
    items: dict[str, dict[str, Any]] = {}
    files: dict[str, Path] = {}
    for south in range(SOUTH, NORTH):
        for west in range(WEST, EAST):
            item = _cell_item(west, south)
            items[item["id"]] = item
            files[sources.url(f"{item['id']}-{ASSET}")] = _cell_file(root / f"{item['id']}.tif", west, south)
    return dict(sorted(items.items())), files


@pytest.fixture
def client(
    cells: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Callable[[], tuple[TestClient, Pgstac, Scenes]]]:
    scenes = Scenes(tmp_path)
    scenes.items, scenes.files = dict(cells[0]), dict(cells[1])
    pgstac = Pgstac(scenes)
    monkeypatch.setattr(mosaic_tiles, "search_items_in_bbox_async", pgstac.search)
    stack = ExitStack()

    def build() -> tuple[TestClient, Pgstac, Scenes]:
        _serve(scenes, monkeypatch)

        @asynccontextmanager
        async def lifespan(app: FastAPI) -> Any:
            app.state.earthx_item_source = None
            app.state.earthx_cache_pool = WITH_POOL
            yield

        app = build_app(REGISTRY, lifespan=lifespan)
        app.state.earthx_resolver = mini_zarr.from_memory
        return stack.enter_context(TestClient(app)), pgstac, scenes

    with stack:
        yield build


def _pixel_of(tile: numpy.ndarray, z: int, lon: float, lat: float) -> tuple[int, int]:
    """Row and column of a point in the tile of level ``z`` that holds it."""
    holder = TMS.tile(lon, lat, z)
    left, bottom, right, top = TMS.xy_bounds(holder)
    x, y = TMS.xy(lon, lat)
    size = tile.shape[-1]
    return int((top - y) / (top - bottom) * size), int((x - left) / (right - left) * size)


def test_the_fixture_is_large_and_the_first_cells_by_id_lie_away_from_the_dataset(cells: Any) -> None:
    items = cells[0]
    west, south, east, north = TERRAIN.spatial_extent.bbox
    assert len(items) > 500
    first = list(items)[: mosaic_tiles.TILE_FILE_BUDGET]
    assert not any(
        items[item_id]["bbox"][0] <= east and items[item_id]["bbox"][2] >= west
        and items[item_id]["bbox"][1] <= north and items[item_id]["bbox"][3] >= south
        for item_id in first
    )  # fmt: skip


@pytest.mark.parametrize("z", range(0, TERRAIN.viewer.min_zoom))  # type: ignore[union-attr]
def test_the_tile_over_the_dataset_has_an_image_at_every_level_below_its_first(client: Any, z: int) -> None:
    api, _, _ = client()
    holder = TMS.tile(*CENTRE, z)
    response = api.get(f"{BASE}/tiles/WebMercatorQuad/{z}/{holder.x}/{holder.y}.npy")
    assert response.status_code == 200, (z, response.text)
    tile = numpy.load(io.BytesIO(response.content))
    row, column = _pixel_of(tile, z, *CENTRE)
    assert tile[-1, row, column] != 0, f"z{z}: no image over the centre of the dataset"
    assert tile[0, row, column] == 100


def _meets_extent(item: dict[str, Any]) -> bool:
    west, south, east, north = TERRAIN.spatial_extent.bbox
    bbox = item["bbox"]
    return bbox[0] <= east and bbox[2] >= west and bbox[1] <= north and bbox[3] >= south


class TestWhereTheSubstituteStandsIn:
    def test_the_catalogue_is_asked_for_the_tile_where_it_lies_over_the_dataset(self, client: Any) -> None:
        api, pgstac, _ = client()
        assert api.get(f"{BASE}/tiles/WebMercatorQuad/0/0/0.npy").status_code == 200
        ((dataset_id, bbox, _),) = pgstac.asked
        assert dataset_id == SURFACE.dataset_id
        assert bbox == pytest.approx(TERRAIN.spatial_extent.bbox)

    def test_a_tile_beside_the_dataset_is_a_404_and_asks_nothing(self, client: Any) -> None:
        api, pgstac, scenes = client()
        holder = TMS.tile(-3.0, 40.0, 8)
        response = api.get(f"{BASE}/tiles/WebMercatorQuad/8/{holder.x}/{holder.y}.npy")
        assert response.status_code == 404
        assert pgstac.asked == [] and scenes.opened == []

    def test_with_more_cells_over_the_dataset_than_the_budget_reads_those_over_it_are_read_and_the_rest_is_said(
        self, client: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        api, _, scenes = client()
        monkeypatch.setattr(mosaic_tiles, "TILE_FILE_BUDGET", 4)
        response = api.get(f"{BASE}/tiles/WebMercatorQuad/0/0/0.npy")
        assert response.status_code == 200, response.text
        assert len(scenes.opened) == 4
        assert all(_meets_extent(scenes.items[item_id]) for item_id in scenes.opened)
        assert int(response.headers[mosaic_tiles.PARTIAL_HEADER]) > 0

    def test_the_cells_the_budget_reads_are_those_with_the_most_over_the_dataset(
        self, client: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        api, _, scenes = client()
        monkeypatch.setattr(mosaic_tiles, "TILE_FILE_BUDGET", 1)
        assert api.get(f"{BASE}/tiles/WebMercatorQuad/0/0/0.npy").status_code == 200
        west, south, east, north = TERRAIN.spatial_extent.bbox
        (opened,) = scenes.opened
        bbox = scenes.items[opened]["bbox"]
        # a cell that lies whole in the dataset, not one that reaches into it by a corner
        assert west <= bbox[0] and bbox[2] <= east and south <= bbox[1] and bbox[3] <= north

    def test_the_cap_of_the_catalogue_cuts_after_the_choice_over_the_dataset(
        self, client: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        api, _, scenes = client()
        monkeypatch.setattr(mosaic_tiles, "SUBSTITUTE_ITEM_CAP", 3)
        response = api.get(f"{BASE}/tiles/WebMercatorQuad/0/0/0.npy")
        assert response.status_code == 200, response.text
        assert len(scenes.opened) == 3
        assert all(_meets_extent(scenes.items[item_id]) for item_id in scenes.opened)
        assert int(response.headers[mosaic_tiles.PARTIAL_HEADER]) >= 1
