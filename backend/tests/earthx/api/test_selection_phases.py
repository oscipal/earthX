"""Where the time of a mosaic goes between the click and the first drawn tile (plan M5-30 §8.7, finding of 13.11.2026).

124 synthetic swissALTI3D tiles (1 km, LV95, 2 m, a COG with overviews) of the real registry entry, read through the real
readers and the real app; the catalogue is a double that counts the calls it gets. What is counted here is what does not
depend on the machine and must not grow: the creation of a selection and its TileJSON open no file, the creation asks
the catalogue once for a hundred ids, and a tile opens the scenes it touches and no more than the budget. The seconds each
phase took are printed for ``pytest -s`` and said in the plan; they are not asserted, because a synthetic file on a local
disk costs a fraction of a real one (55 to 85 ms, plan §8.6).
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, asynccontextmanager
from dataclasses import replace
from pathlib import Path
from typing import Any

import morecantile
import numpy
import pytest
import rasterio
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pyproj import Transformer
from rasterio.transform import from_origin
from rasterio.warp import transform_bounds
from rio_cogeo.cogeo import cog_translate
from rio_cogeo.profiles import cog_profiles
from shapely.geometry import box, mapping

from earthx.access import mosaic_tiles as mosaic_reading
from earthx.api import mosaic_tiles
from earthx.api.tiler import build_app
from earthx.gateway import check_url
from tests.catalog.entries import SWISSALTI3D, registry_of
from tests.earthx.api.mosaic_selections import MemorySelections, batch_source_of
from tests.earthx.processing import sources
from tests.earthx.readers import mini_zarr

TERRAIN = replace(SWISSALTI3D, source=replace(SWISSALTI3D.source, asset_hosts=(sources.HOST,)))
REGISTRY = registry_of(TERRAIN)
ASSET = "dtm"
BASE = f"/collections/{TERRAIN.dataset_id}/mosaic"
TMS = morecantile.tms.get("WebMercatorQuad")

#: An area of 11 by 11 kilometres of 1 km tiles and three more beside it: 124 scenes, the case of the finding.
WEST, SOUTH = 2_598_000, 1_198_000
CELLS = [(WEST + 1000 * column, SOUTH + 1000 * row) for row in range(11) for column in range(11)] + [
    (WEST + 11_000 + 1000 * n, SOUTH) for n in range(3)
]
PIXELS = 500  # a kilometre at 2 m
STATE = "2025"


def _name(west: int, south: int) -> str:
    return f"swissalti3d_{STATE}_{west // 1000}-{south // 1000}"


def _tile_file(path: Path, west: int, south: int) -> Path:
    plain = path.with_suffix(".plain.tif")
    ramp = numpy.linspace(500.0, 900.0, PIXELS, dtype="float32")
    profile = {
        "driver": "GTiff", "dtype": "float32", "count": 1, "height": PIXELS, "width": PIXELS, "crs": "EPSG:2056",
        "transform": from_origin(west, south + 1000, 2.0, 2.0), "nodata": -9999.0,
    }  # fmt: skip
    with rasterio.open(plain, "w", **profile) as destination:
        destination.write(numpy.tile(ramp, (1, PIXELS, 1)) + (west + south) % 7)
    cog = cog_profiles.get("lzw")
    cog.update({"blockxsize": 128, "blockysize": 128})
    cog_translate(plain, path, cog, overview_resampling="nearest", quiet=True)
    plain.unlink()
    return path


def _item(west: int, south: int) -> dict[str, Any]:
    item_id = _name(west, south)
    w, s, e, n = transform_bounds("EPSG:2056", "EPSG:4326", west, south, west + 1000, south + 1000)
    return {
        "id": item_id,
        "type": "Feature",
        "bbox": [w, s, e, n],
        "geometry": mapping(box(w, s, e, n)),
        "properties": {"proj:code": "EPSG:2056", "datetime": "2025-06-01T00:00:00Z", "earthx:state": STATE},
        "assets": {
            ASSET: {"href": sources.url(item_id), "type": "image/tiff; application=geotiff; profile=cloud-optimized"}
        },
    }


class Rig:
    """The app over the 124 scenes, and what each phase asked of the catalogue and of the files."""

    def __init__(self, files: dict[str, Path], items: dict[str, dict[str, Any]]) -> None:
        self.files, self.items = files, items
        self.batches: list[list[str]] = []
        self.fetched: list[str] = []
        self.opened: list[str] = []
        self.selections = MemorySelections()


@pytest.fixture(scope="module")
def scenes(tmp_path_factory: pytest.TempPathFactory) -> tuple[dict[str, Path], dict[str, dict[str, Any]]]:
    root = tmp_path_factory.mktemp("swissalti3d")
    files: dict[str, Path] = {}
    items: dict[str, dict[str, Any]] = {}
    for west, south in CELLS:
        item = _item(west, south)
        items[item["id"]] = item
        files[sources.url(item["id"])] = _tile_file(root / f"{item['id']}.tif", west, south)
    return files, items


@pytest.fixture
def rig(
    scenes: tuple[dict[str, Path], dict[str, dict[str, Any]]], monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[Rig, TestClient]]:
    made = Rig(*scenes)
    sources.serve(made.files, monkeypatch)
    original = mosaic_reading.open_asset

    def recording(scene: Any, **options: Any) -> Any:
        made.opened.append(scene.item_id)
        return original(scene, **options)

    monkeypatch.setattr(mosaic_reading, "open_asset", recording)
    for module in ("earthx.readers.zarr_reader", "earthx.readers.cog"):
        monkeypatch.setattr(
            f"{module}.check_url", lambda url, policy, **_: check_url(url, policy, resolve=mini_zarr.from_memory)
        )
    batch = batch_source_of(made.items, made.batches)

    async def item_source(dataset_id: str, item_id: str) -> dict[str, Any]:
        made.fetched.append(item_id)
        return json.loads(json.dumps(made.items[item_id]))

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.earthx_item_source = item_source
        app.state.earthx_item_batches = batch
        app.state.earthx_cache_pool = object()
        app.state.earthx_mosaic_selections = made.selections
        yield

    app = build_app(REGISTRY, lifespan=lifespan)
    app.state.earthx_resolver = mini_zarr.from_memory
    with ExitStack() as stack:
        yield made, stack.enter_context(TestClient(app))


def _first_view() -> list[morecantile.Tile]:
    """The tiles at z13 the first view asks for: the 11 km of the area at map zoom 13.4 on a 1200 x 800 px map."""
    to_4326 = Transformer.from_crs("EPSG:2056", "EPSG:4326", always_xy=True)
    centre = to_4326.transform(WEST + 5500, SOUTH + 5500)
    to_3857 = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True).transform(*centre)
    metres_per_pixel = 2 * 20037508.342789244 / (512 * 2**13.4)
    half_w, half_h = 600 * metres_per_pixel, 400 * metres_per_pixel
    west, south = TMS.lnglat(to_3857[0] - half_w, to_3857[1] - half_h)
    east, north = TMS.lnglat(to_3857[0] + half_w, to_3857[1] + half_h)
    return list(TMS.tiles(west, south, east, north, [13]))


def _timed(call: Any) -> tuple[Any, float]:
    started = time.perf_counter()
    answer = call()
    return answer, time.perf_counter() - started


def _tile(api: TestClient, selection: str, tile: morecantile.Tile) -> Any:
    path = f"{BASE}/{selection}/tiles/WebMercatorQuad/{tile.z}/{tile.x}/{tile.y}.png"
    return api.get(path, params={"tilesize": "512", "rescale": "0,5000", "colormap_name": "terrain"})


def test_there_are_124_scenes_and_the_first_view_is_a_few_tiles_of_z13() -> None:
    assert len(CELLS) == 124
    assert 2 <= len(_first_view()) <= 9


def test_the_phases_of_the_first_view(rig: tuple[Rig, TestClient], capsys: pytest.CaptureFixture[str]) -> None:
    made, api = rig
    ids = sorted(made.items)
    phases: dict[str, tuple[float, int, int]] = {}

    created, seconds = _timed(lambda: api.post(BASE, json={"items": ids, "assets": [ASSET]}))
    assert created.status_code == 201, created.text
    phases["POST creation"] = (seconds, len(made.opened), len(made.batches))
    selection = created.json()["id"]

    # Creation: one query for a hundred ids, then the rest; the scenes are described from their items, no file is opened (F5).
    assert [len(batch) for batch in made.batches] == [100, 24]
    assert made.opened == []

    body, seconds = _timed(lambda: api.get(created.json()["tilejson"]))
    assert body.status_code == 200
    phases["GET TileJSON"] = (seconds, len(made.opened), len(made.batches))
    # The TileJSON answers from what was stored: no file, no further question to the catalogue.
    assert made.opened == [] and len(made.batches) == 2

    view = _first_view()
    per_tile: list[tuple[str, float, int]] = []
    for tile in view:
        before, fetched_before = len(made.opened), len(made.fetched)
        response, seconds = _timed(lambda tile=tile: _tile(api, selection, tile))
        assert response.status_code == 200, response.text
        reached = len(made.opened) - before
        per_tile.append((f"z{tile.z}/{tile.x}/{tile.y}", seconds, reached))
        assert 1 <= reached <= mosaic_tiles.TILE_FILE_BUDGET
        # A tile fetches the items of the scenes it reads, one each, and none of the others.
        assert len(made.fetched) - fetched_before == reached
    assert len(made.batches) == 2
    sequential = sum(seconds for _, seconds, _ in per_tile)
    files = sum(reached for *_, reached in per_tile)

    made.opened.clear()
    started = time.perf_counter()

    def arrival(tile: morecantile.Tile) -> float:
        assert _tile(api, selection, tile).status_code == 200
        return time.perf_counter() - started

    with ThreadPoolExecutor(max_workers=6) as pool:
        arrivals = sorted(pool.map(arrival, view))
    parallel = arrivals[-1]

    with capsys.disabled():
        print("\nphase                    seconds  files opened  catalogue calls")
        for name, (seconds, opened, calls) in phases.items():
            print(f"{name:<22} {seconds:9.3f} {opened:13d} {calls:16d}")
        for name, seconds, reached in per_tile:
            print(f"tile {name:<17} {seconds:9.3f} {reached:13d}")
        print(f"first view: {len(view)} tiles, {files} files; one after the other {sequential:.2f} s")
        print(f"six at a time: first tile after {arrivals[0]:.2f} s, last after {parallel:.2f} s")


def test_a_tile_far_from_the_scenes_opens_nothing(rig: tuple[Rig, TestClient]) -> None:
    made, api = rig
    selection = api.post(BASE, json={"items": sorted(made.items), "assets": [ASSET]}).json()["id"]
    far = TMS.tile(2.0, 41.0, 13)
    assert _tile(api, selection, far).status_code in (200, 404)
    assert made.opened == []
