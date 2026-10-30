"""The mosaic tile with steps against the mosaic job (NM4-04, adr/0014 §6.3, §6.4).

Scenes A and B are two tiles of zone 32 on one 10 m grid, overlapping by a kilometre; each has ``red`` and ``nir``
(``uint16`` with scale and offset) and a 20 m ``scl``. Inside the overlap A lacks ``nir`` in one stripe of rows, so
the job takes ``red`` from A and ``nir`` from B there; and A's ``scl`` says cloud in another stripe where B is
clear, so the masked NDVI of the job has a hole there that B does not fill. The tile has to show both, bit for bit.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator, Sequence
from contextlib import ExitStack, asynccontextmanager
from dataclasses import replace
from pathlib import Path
from typing import Any
from urllib.parse import quote

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
from rio_tiler.io import Reader
from shapely.geometry import box, mapping

from earthx.api import mosaic_tiles
from earthx.api.tiler import build_app
from earthx.catalog.datasets import SENTINEL_2_L2A
from earthx.catalog.registry import DatasetRegistry
from earthx.gateway import UpstreamError, check_url
from earthx.processing import run
from earthx.processing.operators import REGISTRY as OPERATORS
from tests.earthx.api.test_tiler_chain import _decode
from tests.earthx.processing import sources
from tests.earthx.processing.recipes import recipe_of_data, resolved
from tests.earthx.readers import mini_zarr

DATASET = "synthetic-mosaic-steps"
NO_REPROJECTION = "synthetic-mosaic-no-reprojection"
SYNTHETIC = replace(SENTINEL_2_L2A, dataset_id=DATASET, source=replace(SENTINEL_2_L2A.source, asset_hosts=(sources.HOST,)))
REGISTRY = DatasetRegistry(
    (
        SYNTHETIC,
        replace(
            SYNTHETIC,
            dataset_id=NO_REPROJECTION,
            capabilities=replace(SYNTHETIC.capabilities, reprojection=False),
        ),
    )
)
POOL = object()  # a stand-in for the cache pool: the route only asks whether there is one
TMS = morecantile.tms.get("WebMercatorQuad")
ZOOM = 14
# The native level per tile size: 512 px at z13 has the pixels of 256 px at z14 (NM4-29 §15).
NATIVE = {256: 14, 512: 13}
ZONE_32 = sources.CRS
X0, Y0 = sources.ORIGIN_X, sources.ORIGIN_Y
WIDTH, HEIGHT = 400, 300  # pixels of 10 m per scene
LEFT = {"A": X0, "B": X0 + 3000.0}  # B reaches 100 px into A
BASES = {("A", "red"): 1000, ("A", "nir"): 3000, ("B", "red"): 21000, ("B", "nir"): 25000}
#: Inside the overlap (A's columns 300 to 399): A lacks ``nir`` in rows 100–149 and is cloudy in rows 200–259.
NIR_GAP = (slice(100, 150), slice(300, 400))
CLOUD = (slice(200, 260), slice(300, 400))
CLEAR, CLOUDY = 4, 9

NDVI = {"expression": "(nir - red) / (nir + red)"}
MASK = {"source": "scl", "classes": [8, 9]}
CLOUDS_THEN_NDVI = [("mask", MASK), ("band_math", NDVI)]
_BAND = {"data_type": "uint16", "nodata": 0, "raster:scale": sources.SCALE, "raster:offset": sources.OFFSET}


def _band(item: str, asset: str) -> numpy.ndarray:
    rows, cols = numpy.indices((HEIGHT, WIDTH))
    data = (BASES[(item, asset)] + 3 * rows + cols).astype("uint16")
    if (item, asset) == ("A", "nir"):
        data[NIR_GAP] = 0
    return data


def _scl(item: str) -> numpy.ndarray:
    data = numpy.full((HEIGHT, WIDTH), CLEAR, dtype="uint8")
    if item == "A":
        data[CLOUD] = CLOUDY
    return data[::2, ::2]  # 20 m


def _cog(path: Path, data: numpy.ndarray, left: float, resolution: float, *, scaled: bool) -> Path:
    plain = path.with_suffix(".plain.tif")
    profile = {
        "driver": "GTiff", "dtype": str(data.dtype), "count": 1, "height": data.shape[0], "width": data.shape[1],
        "crs": ZONE_32, "transform": from_origin(left, Y0, resolution, resolution), "nodata": 0,
    }  # fmt: skip
    with rasterio.open(plain, "w", **profile) as destination:
        destination.write(data, 1)
        if scaled:
            destination.scales, destination.offsets = (sources.SCALE,), (sources.OFFSET,)
    cog_profile = cog_profiles.get("deflate")
    cog_profile.update({"blockxsize": 256, "blockysize": 256})
    cog_translate(plain, path, cog_profile, overview_resampling="nearest", quiet=True)
    plain.unlink()
    return path


def _address(item: str, asset: str) -> str:
    return sources.url(f"{item}-{asset}")


def _item(item: str, *, red_band: dict[str, Any] = _BAND) -> dict[str, Any]:
    west, south, east, north = transform_bounds(
        ZONE_32, "EPSG:4326", LEFT[item], Y0 - HEIGHT * 10, LEFT[item] + WIDTH * 10, Y0
    )
    return {
        "id": item,
        "type": "Feature",
        "bbox": [west, south, east, north],
        "geometry": mapping(box(west, south, east, north)),
        "properties": {"proj:code": ZONE_32, "datetime": "2026-07-24T10:00:00Z", "s2:datatake_id": "D1"},
        "assets": {
            "red": {"href": _address(item, "red"), "raster:bands": [red_band]},
            "nir": {"href": _address(item, "nir"), "raster:bands": [_BAND]},
            "scl": {"href": _address(item, "scl"), "raster:bands": [{"data_type": "uint8", "nodata": 0}]},
        },
    }


@pytest.fixture(scope="module")
def files(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    root = tmp_path_factory.mktemp("mosaic-steps")
    made = {}
    for item in "AB":
        for asset in ("red", "nir"):
            made[_address(item, asset)] = _cog(root / f"{item}-{asset}.tif", _band(item, asset), LEFT[item], 10.0, scaled=True)
        made[_address(item, "scl")] = _cog(root / f"{item}-scl.tif", _scl(item), LEFT[item], 20.0, scaled=False)
    return made


class Source:
    """The items the app fetches, and what it fetched and opened."""

    def __init__(self) -> None:
        self.items = {item: _item(item) for item in "AB"}
        self.fetched: list[str] = []
        self.opened: list[str] = []  # the addresses a reader opened (they pass `check_url` there)

    async def __call__(self, dataset_id: str, item_id: str) -> dict[str, Any]:
        self.fetched.append(item_id)
        if item_id not in self.items:
            raise UpstreamError(404, "not found")
        return json.loads(json.dumps(self.items[item_id]))


@pytest.fixture
def source(files: dict[str, Path], monkeypatch: pytest.MonkeyPatch) -> Source:
    served = Source()
    served.opened = sources.serve(files, monkeypatch)
    for module in ("earthx.readers.cog", "earthx.readers.zarr_reader"):
        monkeypatch.setattr(
            f"{module}.check_url", lambda url, policy, **_: check_url(url, policy, resolve=mini_zarr.from_memory)
        )
    return served


def _app(source: Source) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.earthx_item_source = source
        app.state.earthx_cache_pool = POOL
        yield

    app = build_app(REGISTRY, lifespan=lifespan)
    app.state.earthx_resolver = mini_zarr.from_memory
    return app


@pytest.fixture
def client(source: Source) -> Iterator[Callable[[], TestClient]]:
    """Builds the real app; every client is closed with the test."""
    stack = ExitStack()
    with stack:
        yield lambda: stack.enter_context(TestClient(_app(source)))


def _steps(steps: Sequence[tuple[Any, ...]]) -> list[str]:
    """``(op, params)`` or ``(op, params, version)``; version 1 where none is given."""
    parts = []
    for op, params, *version in steps:
        raw = params if isinstance(params, str) else json.dumps(params)
        parts += [f"op={op}", f"op_version={version[0] if version else 1}", f"params={quote(raw)}"]
    return parts


def _url(
    tile: tuple[int, int, int] | None,
    steps: Sequence[tuple[str, dict | str]],
    *,
    items: Sequence[str] = ("B", "A"),
    assets: Sequence[str] = ("red", "nir", "scl"),
    dataset: str = DATASET,
    size: int = 256,
) -> str:
    query = [f"item={item}" for item in items] + [f"asset={quote(asset)}" for asset in assets] + _steps(steps)
    if size != 256:
        query.append(f"tilesize={size}")
    if tile is None:
        path = "WebMercatorQuad/tilejson.json"
    else:
        z, x, y = tile
        path = f"tiles/WebMercatorQuad/{z}/{x}/{y}.tif"
    return f"/collections/{dataset}/mosaic/{path}?{'&'.join(query)}"


def _tiles(zoom: int = ZOOM) -> list[tuple[int, int, int]]:
    """Every tile of ``zoom`` over the two scenes (the native level of 10 m data at 51° N is z14, ~6 m per pixel)."""
    west, south, east, north = transform_bounds(ZONE_32, "EPSG:4326", X0, Y0 - HEIGHT * 10, X0 + 7000.0, Y0)
    return [(tile.z, tile.x, tile.y) for tile in TMS.tiles(west, south, east, north, [zoom])]


def _tile_at(x: float, y: float) -> tuple[tuple[int, int, int], int, int]:
    """The z14 tile over a zone-32 point and the row and column of the point in it."""
    lon, lat = Transformer.from_crs(ZONE_32, "EPSG:4326", always_xy=True).transform(x, y)
    tile = TMS.tile(lon, lat, ZOOM)
    left, bottom, right, top = TMS.xy_bounds(tile)
    mx, my = Transformer.from_crs(ZONE_32, "EPSG:3857", always_xy=True).transform(x, y)
    return (tile.z, tile.x, tile.y), int((top - my) / (top - bottom) * 256), int((mx - left) / (right - left) * 256)


def _recipe(assets: Sequence[str], chain: Sequence[tuple[str, dict]]) -> dict:
    entries = []
    for item in "AB":  # the job's order: both in the target CRS, by id (`mosaic_order`)
        for asset in assets:
            if asset == "scl":
                entry = resolved(item, asset, href=_address(item, asset), scale=None, offset=None)
                entry["bands"] = [{"data_type": "uint8", "nodata": 0, "scale": None, "offset": None}]
            else:
                entry = resolved(item, asset, href=_address(item, asset), scale=sources.SCALE, offset=sources.OFFSET)
            entries.append(entry)
    pad = 2.5
    return {
        "recipe_version": 1,
        "inputs": [{"name": "s2", "dataset": "synthetic", "groups": [["A", "B"]], "assets": list(assets), "resolved": entries}],
        "aoi": sources.aoi_around(X0 + pad, Y0 - HEIGHT * 10 + pad, X0 + 7000.0 - pad, Y0 - pad),
        "steps": [{"op": op, "op_version": 1, "params": params} for op, params in chain],
        "output": {"kind": "raster", "format": "cog", "dtype": "float32"},
    }


def _job(tmp_path: Path, assets: Sequence[str], chain: Sequence[tuple[str, dict]]) -> Path:
    result = run(recipe_of_data(_recipe(assets, chain), OPERATORS), workdir=tmp_path, progress=lambda d, t: None)
    return result.path


def _job_tile(path: Path, tile: tuple[int, int, int], size: int = 256) -> numpy.ma.MaskedArray:
    z, x, y = tile
    with Reader(str(path)) as reader:
        return reader.tile(x, y, z, resampling_method="nearest", tilesize=size).array


def _physical(item: str, asset: str, row: int, col: int) -> numpy.float32:
    raw = numpy.float32(_band(item, asset)[row, col])
    return raw * numpy.float32(sources.SCALE) + numpy.float32(sources.OFFSET)


def _ndvi(red: numpy.float32, nir: numpy.float32) -> float:
    return float((nir - red) / (nir + red))


class TestTheTileEqualsTheJobOnTheNativeLevel:
    """§6.4: the mosaic tile through the real route against the mosaic job, bit for bit, on every tile."""

    @pytest.mark.parametrize("size", NATIVE)
    @pytest.mark.parametrize(
        ("assets", "chain"),
        [(("red", "nir"), [("band_math", NDVI)]), (("red", "nir", "scl"), CLOUDS_THEN_NDVI)],
        ids=["band math", "mask, band math"],
    )
    def test_bit_for_bit(self, client, tmp_path: Path, assets, chain, size: int) -> None:
        job = _job(tmp_path, assets, chain)
        api = client()
        compared = masked = 0
        for tile in _tiles(NATIVE[size]):
            response = api.get(_url(tile, chain, assets=assets, size=size))
            assert response.status_code == 200, response.text
            from_tile, from_job = _decode(response.content), _job_tile(job, tile, size)
            assert from_tile.shape == from_job.shape, tile
            assert numpy.array_equal(from_tile.mask, numpy.ma.getmaskarray(from_job)), tile
            valid = ~from_tile.mask
            assert numpy.array_equal(from_tile.data[valid], from_job.data[valid]), tile
            compared += int(valid.sum())
            masked += int(from_tile.mask.sum())
        assert compared > 50_000 and masked > 0

    def test_where_a_lacks_nir_red_comes_from_a_and_nir_from_b(self, client) -> None:
        """First the mosaic per band, then the index: neither A's hole nor B's ``red``."""
        row, col = 125, 350  # inside NIR_GAP, in A's pixels; B's column there is 50
        tile, tile_row, tile_col = _tile_at(X0 + col * 10 + 5, Y0 - row * 10 - 5)
        value = _decode(client().get(_url(tile, [("band_math", NDVI)], assets=("red", "nir"))).content)
        assert not value.mask[0, tile_row, tile_col]
        mixed = _ndvi(_physical("A", "red", row, col), _physical("B", "nir", row, col - 300))
        only_b = _ndvi(_physical("B", "red", row, col - 300), _physical("B", "nir", row, col - 300))
        assert value[0, tile_row, tile_col] == pytest.approx(mixed, abs=2e-3)
        assert abs(mixed - only_b) > 0.05

    def test_a_cloud_of_the_first_scene_stays_a_hole_although_the_second_is_clear(self, client) -> None:
        """The job masks after the mosaic: B does not fill A's cloud. Masking scene by scene would."""
        x, y = X0 + 350 * 10 + 5, Y0 - 230 * 10 - 5  # inside CLOUD
        tile, tile_row, tile_col = _tile_at(x, y)
        api = client()
        mosaic = _decode(api.get(_url(tile, CLOUDS_THEN_NDVI)).content)
        assert mosaic.mask[0, tile_row, tile_col]
        b_alone = api.get(
            f"/collections/{DATASET}/items/B/tiles/WebMercatorQuad/{tile[0]}/{tile[1]}/{tile[2]}.tif?"
            + "&".join(["asset=red", "asset=nir", "asset=scl", *_steps(CLOUDS_THEN_NDVI)])
        )
        assert not _decode(b_alone.content).mask[0, tile_row, tile_col]

    def test_the_order_of_the_ids_and_a_fresh_app_do_not_change_the_bytes(self, client) -> None:
        tile = _tiles()[len(_tiles()) // 2]
        first = client().get(_url(tile, CLOUDS_THEN_NDVI, items=("A", "B")))
        second = client().get(_url(tile, CLOUDS_THEN_NDVI, items=("B", "A")))
        assert first.status_code == second.status_code == 200
        assert first.content == second.content


class TestTheTileJson:
    def test_it_names_the_order_and_the_unit(self, client) -> None:
        response = client().get(_url(None, CLOUDS_THEN_NDVI))
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["earthx:order"] == ["A", "B"]
        assert "op=mask" in body["tiles"][0] and "item=B" in body["tiles"][0]

    def test_a_step_that_names_a_band_an_earlier_one_removed_is_a_422_that_names_it(self, client) -> None:
        response = client().get(_url(None, [("band_math", NDVI), ("mask", MASK)]))
        assert response.status_code == 422
        assert response.json()["detail"].startswith("step 1: ")


class TestRefusedBeforeTheFirstItemIsFetched:
    """KE1: what the URL alone decides costs no request to the source."""

    @pytest.mark.parametrize(
        ("change", "status"),
        [
            ({"steps": [("band_math", NDVI)] * 5}, 400),
            ({"assets": ("red", "nir", "scl", "blue", "green")}, 400),
            ({"steps": [("band_math", "{")]}, 400),
            ({"steps": [("no_such_operator", NDVI)]}, 422),
            ({"steps": [("reproject", {"crs": "EPSG:3035"}, 2)]}, 422),
            ({"steps": [("mask", {"source": "red", "classes": [3]})]}, 422),
            ({"items": ("A",)}, 400),
            ({"dataset": NO_REPROJECTION}, 422),
            ({"tile": (7, 67, 42)}, 400),
        ],
        ids=[
            "five steps",
            "five assets",
            "params not JSON",
            "unknown operator",
            "not a tile operator",
            "mask on another band",
            "one scene",
            "dataset without reprojection",
            "below z8",
        ],
    )
    def test_refusal(self, client, source: Source, change: dict[str, Any], status: int, request) -> None:
        tile = change.pop("tile", _tiles()[0])
        options = {"steps": CLOUDS_THEN_NDVI, **change}
        response = client().get(_url(tile, options.pop("steps"), **options))
        assert response.status_code == status, response.text
        assert source.fetched == []
        if request.node.callspec.id == "not a tile operator":
            assert response.json()["detail"] == "'reproject' does not run as a tile"

    def test_a_request_over_the_limit_is_a_414_before_anything_else(self, client, source: Source) -> None:
        long = {"expression": "nir + " * 340 + "red"}
        url = _url(_tiles()[0], [("band_math", long)] * 4)
        assert len(url) > mosaic_tiles.MAX_MOSAIC_REQUEST_BYTES
        response = client().get(url)
        assert response.status_code == 414
        assert str(mosaic_tiles.MAX_MOSAIC_REQUEST_BYTES) in response.json()["detail"]
        assert source.fetched == []

    def test_one_byte_under_the_limit_is_not_refused_for_its_length(self, client) -> None:
        base = _url(_tiles()[0], [("band_math", NDVI)], assets=("red", "nir"))
        padding = mosaic_tiles.MAX_MOSAIC_REQUEST_BYTES - len(base) - len("&rescale=") - 4
        response = client().get(base + "&rescale=" + "0" * padding + ",1.0")
        assert len(base) + len("&rescale=") + padding + 4 == mosaic_tiles.MAX_MOSAIC_REQUEST_BYTES
        assert response.status_code == 200, response.text

    @pytest.mark.parametrize("extra", ["expression=nir", "algorithm=hillshade", "bbox=1,2,3,4", "aoi=x"])
    def test_a_free_expression_or_an_area_next_to_the_steps_is_a_400(self, client, source: Source, extra: str) -> None:
        response = client().get(_url(_tiles()[0], CLOUDS_THEN_NDVI) + f"&{extra}")
        assert response.status_code == 400
        assert source.fetched == []

    def test_half_a_step_is_a_400(self, client, source: Source) -> None:
        url = _url(_tiles()[0], [("band_math", NDVI)]) + "&params=" + quote(json.dumps(NDVI))
        assert client().get(url).status_code == 400
        assert source.fetched == []


class TestRefusedBeforeTheFirstFileIsOpened:
    """KE1, §8.1: what the items decide is judged on all of them, before any file is read."""

    def test_a_band_the_assets_do_not_have(self, client, source: Source) -> None:
        response = client().get(_url(_tiles()[0], [("band_math", {"expression": "swir - red"})], assets=("red", "nir")))
        assert response.status_code == 422
        assert "swir" in response.json()["detail"]
        assert source.fetched and source.opened == []

    def test_scenes_that_scale_an_asset_differently(self, client, source: Source) -> None:
        source.items["B"] = _item("B", red_band={**_BAND, "raster:scale": 0.001})
        response = client().get(_url(_tiles()[0], [("band_math", NDVI)], assets=("red", "nir")))
        assert response.status_code == 422
        assert response.json()["detail"] == "the scenes of the mosaic scale 'red' differently"
        assert source.opened == []

    def test_a_tile_of_a_away_from_b_still_compares_b(self, client, source: Source) -> None:
        """The rule holds for every tile of the mosaic, not only for those over both scenes."""
        source.items["B"] = _item("B", red_band={**_BAND, "raster:scale": 0.001})
        tile, _, _ = _tile_at(X0 + 50, Y0 - 50)  # over A only
        response = client().get(_url(tile, [("band_math", NDVI)], assets=("red", "nir")))
        assert response.status_code == 422


class TestWithoutSteps:
    def test_the_mosaic_of_one_asset_is_as_before(self, client) -> None:
        tile = _tiles()[0]
        response = client().get(f"/collections/{DATASET}/mosaic/tiles/WebMercatorQuad/{tile[0]}/{tile[1]}/{tile[2]}.tif?item=A&item=B&asset=red")
        assert response.status_code == 200, response.text

    def test_two_assets_without_steps_are_a_400(self, client, source: Source) -> None:
        response = client().get(_url(_tiles()[0], [], assets=("red", "nir")))
        assert response.status_code == 400
        assert source.fetched == []
