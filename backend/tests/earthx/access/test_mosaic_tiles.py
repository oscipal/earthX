"""The mosaic tile in `access`, on synthetic scenes of zone 32 read from disk (M4-17a).

What `api` will do in front of it — clearing addresses, cutting the list down to the scenes of
the tile, sorting it (M4-17b) — is not here: these tests hand the factory the scenes directly,
in the order they are to be read, and check what the reading does with them. Each scene is a
flat ``uint8`` COG with a value of its own, so that the winner of a pixel can be read off it.
"""

from __future__ import annotations

import io
import threading
from pathlib import Path
from typing import Any

import morecantile
import numpy
import pytest
import rasterio
import rasterio.env
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pyproj import Transformer
from rasterio.errors import EnvError, RasterioIOError
from rasterio.transform import from_origin
from rio_cogeo.cogeo import cog_translate
from rio_cogeo.profiles import cog_profiles
from titiler.core.errors import DEFAULT_STATUS_CODES, add_exception_handlers

from earthx.access import mosaic_tiles
from earthx.access.mosaic_tiles import (
    MOSAIC_THREADS,
    EarthxMosaicTilerFactory,
    MosaicBandsDiffer,
    MosaicScenes,
    MosaicTileReader,
)
from earthx.readers.cog import AssetPath
from earthx.readers.zarr_reader import zarr_asset
from tests.earthx.readers import mini_zarr

ZONE_32 = "EPSG:32632"
TMS = morecantile.tms.get("WebMercatorQuad")
TO_4326 = Transformer.from_crs(ZONE_32, "EPSG:4326", always_xy=True)
TO_3857 = Transformer.from_crs(ZONE_32, "EPSG:3857", always_xy=True)

#: The tile of z12 the tests look at (about 6 km a side here), and its centre in zone-32 metres,
#: rounded to the 10 m pixel: the scene boundary of the tests runs north–south through it.
TILE = TMS.tile(*TO_4326.transform(604_000.0, 5_698_500.0), 12)
SEAM_X, SEAM_Y = (
    round(value / 10) * 10
    for value in Transformer.from_crs("EPSG:3857", ZONE_32, always_xy=True).transform(
        (TMS.xy_bounds(TILE).left + TMS.xy_bounds(TILE).right) / 2,
        (TMS.xy_bounds(TILE).bottom + TMS.xy_bounds(TILE).top) / 2,
    )
)
#: Scenes reach 5 km north and south of the centre, so that they cover the tile from top to bottom.
TOP = SEAM_Y + 5000.0
ROWS = 1000
TILE_URL = f"/tiles/WebMercatorQuad/{TILE.z}/{TILE.x}/{TILE.y}.npy"
PROBE = "EARTHX_MOSAIC_PROBE"


def _scene(path: Path, left: float, width_m: float, value: int) -> AssetPath:
    """A flat one-band COG of zone 32 from ``left`` to ``left + width_m``, opened like a cleared asset."""
    width = round(width_m / 10)
    plain = path.with_suffix(".plain.tif")
    profile = {
        "driver": "GTiff", "dtype": "uint8", "count": 1, "height": ROWS, "width": width, "crs": ZONE_32,
        "transform": from_origin(left, TOP, 10.0, 10.0), "nodata": 0,
    }  # fmt: skip
    with rasterio.open(plain, "w", **profile) as destination:
        destination.write(numpy.full((ROWS, width), value, dtype="uint8"), 1)
    cog_translate(plain, path, cog_profiles.get("deflate"), quiet=True)
    plain.unlink()
    return AssetPath(str(path), dataset_id="synthetic", item_id=path.stem, asset="red")


def _bounds(scenes: list[AssetPath]) -> tuple[float, float, float, float]:
    corners = []
    for scene in scenes:
        with rasterio.open(scene) as dataset:
            left, bottom, right, top = dataset.bounds
        corners += [TO_4326.transform(left, bottom), TO_4326.transform(right, top)]
    lons, lats = zip(*corners, strict=True)
    return min(lons), min(lats), max(lons), max(lats)


def _client(scenes: list[AssetPath], *, viewer_zoom: tuple[int, int] | None = None) -> TestClient:
    mosaic = MosaicScenes("synthetic", tuple(scenes), _bounds(scenes))
    factory = EarthxMosaicTilerFactory(
        path_dependency=lambda: mosaic,
        environment_dependency=lambda: {PROBE: "on"},
        viewer_zoom_dependency=lambda: viewer_zoom,
        name="mosaic",
    )
    app = FastAPI()
    app.include_router(factory.router)
    add_exception_handlers(app, DEFAULT_STATUS_CODES)
    return TestClient(app)


def _tile(client: TestClient) -> numpy.ndarray:
    response = client.get(TILE_URL)
    assert response.status_code == 200, response.text
    return numpy.load(io.BytesIO(response.content))


def _at(tile: numpy.ndarray, x: float, y: float = SEAM_Y) -> int | None:
    """The value at a zone-32 point of the tile, or ``None`` where the tile is masked."""
    left, bottom, right, top = TMS.xy_bounds(TILE)
    mx, my = TO_3857.transform(x, y)
    size = tile.shape[-1]
    col = int((mx - left) / (right - left) * size)
    row = int((top - my) / (top - bottom) * size)
    return None if tile[-1, row, col] == 0 else int(tile[0, row, col])


@pytest.fixture
def opened(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str | None]]:
    """Each scene the mosaic opens, with the probe option its thread sees — in ``rasterio.Env`` and in GDAL."""
    seen: list[tuple[str, str | None]] = []
    lock = threading.Lock()
    original = mosaic_tiles.open_asset

    def recording(scene: Any, **options: Any) -> Any:
        try:
            probe = rasterio.env.getenv().get(PROBE)
        except EnvError:
            probe = None
        gdal = rasterio.env.get_gdal_config(PROBE)
        with lock:
            seen.append((scene.item_id, probe if probe == gdal else f"{probe} / {gdal}"))
        return original(scene, **options)

    monkeypatch.setattr(mosaic_tiles, "open_asset", recording)
    return seen


class TestOneSurfaceOverASceneBoundary:
    def test_two_neighbouring_scenes_are_one_surface_without_a_gap(self, tmp_path: Path) -> None:
        west = _scene(tmp_path / "west.tif", SEAM_X - 4000.0, 4000.0, 100)
        east = _scene(tmp_path / "east.tif", SEAM_X, 4000.0, 200)
        tile = _tile(_client([west, east]))
        assert _at(tile, SEAM_X - 500.0) == 100
        assert _at(tile, SEAM_X + 500.0) == 200
        left, _, right, _ = TMS.xy_bounds(TILE)
        line = [
            x
            for x in numpy.arange(SEAM_X - 3900.0, SEAM_X + 3900.0, 20.0)
            if left < TO_3857.transform(x, SEAM_Y)[0] < right
        ]
        assert len(line) > 20
        assert all(_at(tile, x) is not None for x in line)

    def test_where_scenes_overlap_the_first_of_the_list_wins(self, tmp_path: Path) -> None:
        west = _scene(tmp_path / "west.tif", SEAM_X - 4000.0, 5000.0, 100)
        east = _scene(tmp_path / "east.tif", SEAM_X - 1000.0, 5000.0, 200)
        forward, backward = _tile(_client([west, east])), _tile(_client([east, west]))
        assert _at(forward, SEAM_X - 500.0) == 100
        assert _at(backward, SEAM_X - 500.0) == 200
        assert _at(forward, SEAM_X - 2000.0) == _at(backward, SEAM_X - 2000.0) == 100
        assert _at(forward, SEAM_X + 2000.0) == _at(backward, SEAM_X + 2000.0) == 200

    def test_a_scene_away_from_the_tile_does_not_break_it(self, tmp_path: Path) -> None:
        here = _scene(tmp_path / "here.tif", SEAM_X - 4000.0, 8000.0, 100)
        away = _scene(tmp_path / "away.tif", SEAM_X + 50_000.0, 4000.0, 200)
        assert _at(_tile(_client([away, here])), SEAM_X) == 100

    def test_a_tile_no_scene_touches_is_a_404(self, tmp_path: Path) -> None:
        away = _scene(tmp_path / "away.tif", SEAM_X + 50_000.0, 4000.0, 200)
        assert _client([away]).get(TILE_URL).status_code == 404

    def test_a_scene_that_cannot_be_read_fails_the_tile_rather_than_letting_another_win(self, tmp_path: Path) -> None:
        missing = AssetPath(str(tmp_path / "missing.tif"), dataset_id="synthetic", item_id="missing", asset="red")
        here = _scene(tmp_path / "here.tif", SEAM_X - 4000.0, 8000.0, 100)
        scenes = MosaicScenes("synthetic", (missing, here), _bounds([here]))
        with MosaicTileReader(scenes, tms=TMS) as reader, pytest.raises(RasterioIOError):
            reader.tile(TILE.x, TILE.y, TILE.z)


class TestScenesWithAnotherNumberOfBands:
    def test_they_fail_the_tile_with_a_reason_of_their_own_and_not_in_a_failed_assert(self, tmp_path: Path) -> None:
        one = _scene(tmp_path / "one.tif", SEAM_X - 4000.0, 4000.0, 100)  # half the tile: the other half is read too
        plain, path = tmp_path / "two.plain.tif", tmp_path / "two.tif"
        profile = {
            "driver": "GTiff", "dtype": "uint8", "count": 2, "height": ROWS, "width": 800, "crs": ZONE_32,
            "transform": from_origin(SEAM_X - 4000.0, TOP, 10.0, 10.0), "nodata": 0,
        }  # fmt: skip
        with rasterio.open(plain, "w", **profile) as destination:
            destination.write(numpy.full((2, ROWS, 800), 200, dtype="uint8"))
        cog_translate(plain, path, cog_profiles.get("deflate"), quiet=True)
        two = AssetPath(str(path), dataset_id="synthetic", item_id="two", asset="red")
        scenes = MosaicScenes("synthetic", (one, two), _bounds([one]))
        with MosaicTileReader(scenes, tms=TMS) as reader, pytest.raises(MosaicBandsDiffer) as refused:
            reader.tile(TILE.x, TILE.y, TILE.z)
        assert refused.value.status_code == 422


class TestZarrScenes:
    def test_zarr_scenes_make_a_mosaic_too_and_the_first_wins(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mini_zarr.serve_store(mini_zarr.build_mini_zarr(tmp_path / "mini.zarr"), monkeypatch)

        def scene(variable: str) -> Any:
            return zarr_asset(
                f"{mini_zarr.BASE_URL}/r10m", mini_zarr.POLICY, dataset_id="synthetic", item_id=variable,
                asset="reflectance", crs=mini_zarr.ITEM_CRS, resolve=mini_zarr.from_memory, variable=variable,
            )  # fmt: skip

        left, bottom, right, top = mini_zarr.store_bounds()
        to_4326 = Transformer.from_crs(mini_zarr.ITEM_CRS, "EPSG:4326", always_xy=True)
        west, south = to_4326.transform(left, bottom)
        east, north = to_4326.transform(right, top)
        tile = TMS.tile(*to_4326.transform((left + right) / 2, (bottom + top) / 2), 16)

        def read(*variables: str) -> numpy.ndarray:
            mosaic = MosaicScenes("synthetic", tuple(scene(v) for v in variables), (west, south, east, north))
            factory = EarthxMosaicTilerFactory(
                path_dependency=lambda: mosaic, environment_dependency=lambda: {}, name="mosaic"
            )
            app = FastAPI()
            app.include_router(factory.router)
            response = TestClient(app).get(f"/tiles/WebMercatorQuad/{tile.z}/{tile.x}/{tile.y}.npy")
            assert response.status_code == 200, response.text
            return numpy.load(io.BytesIO(response.content))

        both, b04, b02 = read("b04", "b02"), read("b04"), read("b02")
        assert numpy.array_equal(both, b04)
        assert not numpy.array_equal(both, b02)


class TestReadingInPortions:
    def test_a_tile_the_first_portion_fills_opens_no_further_scene(
        self, tmp_path: Path, opened: list[tuple[str, str | None]]
    ) -> None:
        scenes = [
            _scene(tmp_path / f"s{index}.tif", SEAM_X - 5000.0, 10000.0, 10 + index)
            for index in range(MOSAIC_THREADS + 2)
        ]
        tile = _tile(_client(scenes))
        assert _at(tile, SEAM_X) == 10
        assert sorted(item for item, _ in opened) == sorted(scene.item_id for scene in scenes[:MOSAIC_THREADS])

    def test_a_gap_after_the_first_portion_is_filled_from_the_next(
        self, tmp_path: Path, opened: list[tuple[str, str | None]]
    ) -> None:
        wests = [
            _scene(tmp_path / f"w{index}.tif", SEAM_X - 5000.0, 5000.0, 10 + index) for index in range(MOSAIC_THREADS)
        ]
        east = _scene(tmp_path / "east.tif", SEAM_X, 5000.0, 200)
        tile = _tile(_client([*wests, east]))
        assert _at(tile, SEAM_X - 500.0) == 10
        assert _at(tile, SEAM_X + 500.0) == 200
        assert len(opened) == MOSAIC_THREADS + 1

    def test_every_scene_is_read_under_the_gdal_configuration_of_the_route(
        self, tmp_path: Path, opened: list[tuple[str, str | None]]
    ) -> None:
        scenes = [
            _scene(tmp_path / f"s{index}.tif", SEAM_X - 4000.0 + index * 2000.0, 4000.0, 50) for index in range(3)
        ]
        _tile(_client(scenes))
        assert len(opened) == 3
        assert {probe for _, probe in opened} == {"on"}


class TestTheRoutes:
    def test_only_the_tile_and_the_tilejson_exist(self, tmp_path: Path) -> None:
        client = _client([_scene(tmp_path / "a.tif", SEAM_X - 4000.0, 4000.0, 100)])
        paths = set(client.app.openapi()["paths"])
        assert paths == {
            "/tiles/{tileMatrixSetId}/{z}/{x}/{y}",
            "/tiles/{tileMatrixSetId}/{z}/{x}/{y}.{format}",
            "/{tileMatrixSetId}/tilejson.json",
        }
        names = {
            parameter["name"]
            for route in client.app.openapi()["paths"].values()
            for operation in route.values()
            for parameter in operation.get("parameters", [])
        }
        assert names.isdisjoint({"url", "aoi", "bbox", "geometry", "intersects"})

    def test_the_tilejson_names_the_extent_of_all_scenes_and_the_released_levels(self, tmp_path: Path) -> None:
        west = _scene(tmp_path / "west.tif", SEAM_X - 4000.0, 4000.0, 100)
        east = _scene(tmp_path / "east.tif", SEAM_X + 20_000.0, 4000.0, 200)
        response = _client([west, east], viewer_zoom=(8, 14)).get("/WebMercatorQuad/tilejson.json?asset=red")
        assert response.status_code == 200
        body = response.json()
        assert body["bounds"] == pytest.approx(list(_bounds([west, east])))
        assert (body["minzoom"], body["maxzoom"]) == (8, 14)
        assert "/tiles/WebMercatorQuad/{z}/{x}/{y}" in body["tiles"][0]
        assert "asset=red" in body["tiles"][0]
        assert body["earthx:order"] == [west.item_id, east.item_id]

    def test_two_fresh_apps_answer_the_same_url_with_the_same_bytes(self, tmp_path: Path) -> None:
        west = _scene(tmp_path / "west.tif", SEAM_X - 4000.0, 5000.0, 100)
        east = _scene(tmp_path / "east.tif", SEAM_X - 1000.0, 5000.0, 200)
        png = TILE_URL.removesuffix(".npy") + ".png"
        first, second = _client([west, east]).get(png), _client([west, east]).get(png)
        assert first.status_code == second.status_code == 200
        assert first.content == second.content


class TestTheScenes:
    def test_the_factory_refuses_a_reader_dependency_of_its_own(self) -> None:
        with pytest.raises(TypeError, match="reader_dependency"):
            EarthxMosaicTilerFactory(
                path_dependency=lambda: None, reader_dependency=lambda: None, name="mosaic"
            )  # fmt: skip

    def test_a_mosaic_has_a_scene(self) -> None:
        with pytest.raises(ValueError, match="at least one scene"):
            MosaicScenes("synthetic", (), (0.0, 0.0, 1.0, 1.0))

    def test_a_plain_string_is_no_scene(self) -> None:
        with pytest.raises(TypeError, match="KLAERUNGEN B8"):
            MosaicScenes("synthetic", ("/vsicurl/https://anywhere.example.invalid/x.tif",), (0.0, 0.0, 1.0, 1.0))  # type: ignore[arg-type]

    def test_the_reader_takes_nothing_but_mosaic_scenes(self) -> None:
        with pytest.raises(TypeError, match="MosaicScenes"):
            MosaicTileReader("/vsicurl/https://anywhere.example.invalid/x.tif")  # type: ignore[arg-type]
