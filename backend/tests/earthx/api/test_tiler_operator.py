"""The tile of an operator: the route, its refusals, and T1 against T2 (plan M4-09 §3.4, §3.5; adr/0014 §6.2–§6.4).

``band_math`` as ``op=band_math&op_version=1&params=…`` on the tile route of the real app, over the synthetic
COGs and the CF Mini-Zarr of the processing tests, served through the real `readers`. The comparison runs the
same recipe through ``processing.run`` and reads its result onto the same tile with ``nearest``: on a level
that reads the native resolution the two are bit-identical (§6.3, row 2).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urlsplit

import numpy
import pytest
from fastapi.testclient import TestClient
from rasterio.io import MemoryFile
from rasterio.warp import transform as rasterio_transform
from rasterio.warp import transform_bounds
from rio_tiler.constants import WEB_MERCATOR_TMS, WGS84_CRS
from rio_tiler.io import Reader

from earthx.api.tiler import build_app
from earthx.catalog.datasets import SENTINEL_2_L2A, SENTINEL_2_L2A_ZARR3
from earthx.catalog.registry import DatasetRegistry, LicenseTier
from earthx.gateway import check_url
from earthx.processing import run
from earthx.processing.operators import REGISTRY as OPERATORS
from earthx.processing.recipe import recipe_from_data
from tests.earthx.processing import sources
from tests.earthx.processing.recipes import resolved
from tests.earthx.readers import mini_zarr, mini_zarr_cf

WIDTH, HEIGHT = 700, 600
ITEM = "ITEM_A"
COG = "synthetic-cog"
ZARR = "synthetic-zarr"
ZOOM = 14
NDVI = "(nir - red) / (nir + red)"
OP = {"op": "band_math", "op_version": "1"}

COG_DATASET = replace(
    SENTINEL_2_L2A, dataset_id=COG, source=replace(SENTINEL_2_L2A.source, asset_hosts=(sources.HOST,))
)
ZARR_DATASET = replace(
    SENTINEL_2_L2A_ZARR3, dataset_id=ZARR, source=replace(SENTINEL_2_L2A_ZARR3.source, asset_hosts=(mini_zarr.HOST,))
)
DISPLAY_ONLY = replace(
    COG_DATASET, dataset_id="synthetic-display", license=replace(COG_DATASET.license, tier=LicenseTier.DISPLAY)
)
NO_BAND_MATH = replace(
    COG_DATASET,
    dataset_id="synthetic-no-band-math",
    capabilities=replace(COG_DATASET.capabilities, band_math=False),
)
REGISTRY = DatasetRegistry((COG_DATASET, ZARR_DATASET, DISPLAY_ONLY, NO_BAND_MATH))

_BAND = {"data_type": "uint16", "nodata": 0, "raster:scale": sources.SCALE, "raster:offset": sources.OFFSET}


def _item(item_id: str, assets: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item_id,
        "type": "Feature",
        "properties": {"proj:code": sources.CRS, "datetime": "2026-01-02T10:00:00Z"},
        "assets": assets,
    }


ITEM_JSON = _item(
    ITEM,
    {
        "red": {"href": sources.url("red"), "raster:bands": [_BAND]},
        "nir": {"href": sources.url("nir"), "raster:bands": [_BAND]},
        "bare": {"href": sources.url("bare")},
        "wrongscale": {"href": sources.url("red"), "raster:bands": [{**_BAND, "raster:scale": 0.0002}]},
        "elsewhere": {"href": "https://elsewhere.example.invalid/red.tif", "raster:bands": [_BAND]},
        "r10m": {"href": mini_zarr_cf.GROUP_URL},
        "r10m-scaled": {"href": mini_zarr_cf.GROUP_URL, "raster:bands": [_BAND]},
    },
)


@pytest.fixture(scope="module")
def files(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    root = tmp_path_factory.mktemp("op-bands")
    return {
        "red": sources.build_band_cog(root / "red.tif", sources.ramp(WIDTH, HEIGHT, 1200)),
        "nir": sources.build_band_cog(root / "nir.tif", sources.ramp(WIDTH, HEIGHT, 3400)),
        "bare": sources.build_band_cog(root / "bare.tif", sources.ramp(WIDTH, HEIGHT, 900), scale=None, offset=None),
    }


@pytest.fixture(scope="module")
def cf_store(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return mini_zarr_cf.build_mini_zarr_cf(tmp_path_factory.mktemp("op-cf") / "mini.zarr")


@pytest.fixture
def client(files: dict[str, Path], cf_store: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    sources.serve({sources.url(name): path for name, path in files.items()}, monkeypatch, zarr_root=cf_store)
    for module in ("earthx.readers.zarr_reader", "earthx.readers.cog"):
        monkeypatch.setattr(
            f"{module}.check_url", lambda url, policy, **_: check_url(url, policy, resolve=mini_zarr.from_memory)
        )

    async def item_source(dataset_id: str, item_id: str) -> dict[str, Any]:
        return ITEM_JSON

    @asynccontextmanager
    async def lifespan(app):
        app.state.earthx_item_source = item_source
        yield

    app = build_app(REGISTRY, lifespan=lifespan)
    app.state.earthx_resolver = mini_zarr.from_memory
    with TestClient(app) as test_client:
        yield test_client


def _tiles() -> list[tuple[int, int, int]]:
    """Tiles of zoom 14 over the raster, the one with the nodata corner (top left) first."""
    west, south, east, north = transform_bounds(
        sources.CRS,
        WGS84_CRS,
        sources.ORIGIN_X,
        sources.ORIGIN_Y - HEIGHT * sources.RESOLUTION,
        sources.ORIGIN_X + WIDTH * sources.RESOLUTION,
        sources.ORIGIN_Y,
    )
    corner = WEB_MERCATOR_TMS.tile(west + 1e-5, north - 1e-5, ZOOM)
    found = [(corner.z, corner.x, corner.y)]
    for t in WEB_MERCATOR_TMS.tiles(west, south, east, north, [ZOOM]):
        if (t.z, t.x, t.y) not in found:
            found.append((t.z, t.x, t.y))
    return found


def _url(
    tile: tuple[int, int, int],
    *,
    dataset: str = COG,
    assets: tuple[str, ...] = ("red", "nir"),
    expression: str = NDVI,
    extra: str = "",
    form: str = "tif",
    **overrides: str | None,
) -> str:
    z, x, y = tile
    query = {**OP, "params": json.dumps({"expression": expression}), **overrides}
    parts = [f"asset={quote(a)}" for a in assets] + [f"{k}={quote(v)}" for k, v in query.items() if v is not None]
    return f"/collections/{dataset}/items/{ITEM}/tiles/WebMercatorQuad/{z}/{x}/{y}.{form}?{'&'.join(parts)}{extra}"


def _decode(content: bytes) -> numpy.ma.MaskedArray:
    """The GeoTIFF of a tile: band 1 is the data, band 2 the alpha band.

    rio-tiler writes a float tile's alpha as a cast of its mask: not 0 and 255, but a negative
    number where the pixel is invalid. What counts is its sign, and that the data is NaN exactly there.
    """
    with MemoryFile(content) as memory, memory.open() as dataset:
        assert dataset.count == 2
        data, alpha = dataset.read(1), dataset.read(2)
    invalid = alpha <= 0
    assert numpy.array_equal(invalid, numpy.isnan(data))
    return numpy.ma.masked_array(data, mask=invalid)


# --- T1 against T2 (adr/0014 §6.4) ---------------------------------------------------------------


def _recipe(assets: tuple[str, ...], expression: str) -> dict:
    entries = [
        resolved(ITEM, asset, href=sources.url(asset), scale=sources.SCALE, offset=sources.OFFSET) for asset in assets
    ]
    return {
        "recipe_version": 1,
        "inputs": [{"name": "s2", "dataset": "synthetic", "groups": [[ITEM]], "assets": list(assets), "resolved": entries}],
        "aoi": sources.whole(WIDTH, HEIGHT, inset=0.0),
        "steps": [{"op": "band_math", "op_version": 1, "params": {"expression": expression}}],
        "output": {"kind": "raster", "format": "cog", "dtype": "float32"},
    }


def _source_position(tile) -> tuple[numpy.ndarray, numpy.ndarray]:
    """Where the centre of each pixel of a 256 px tile lies in the Mini-Zarr's pixels (column, row)."""
    bounds = WEB_MERCATOR_TMS.xy_bounds(tile)
    step = (bounds.right - bounds.left) / 256
    xs = bounds.left + (numpy.arange(256) + 0.5) * step
    ys = bounds.top - (numpy.arange(256) + 0.5) * step
    grid_x, grid_y = numpy.meshgrid(xs, ys)
    x, y = rasterio_transform("EPSG:3857", mini_zarr_cf.ITEM_CRS, grid_x.ravel().tolist(), grid_y.ravel().tolist())
    col = (numpy.array(x).reshape(256, 256) - mini_zarr_cf.ORIGIN_X) / mini_zarr_cf.RESOLUTION_M
    row = (mini_zarr_cf.ORIGIN_Y - numpy.array(y).reshape(256, 256)) / mini_zarr_cf.RESOLUTION_M
    return col, row


def _zarr_ndvi(item_scaling: bool) -> numpy.ma.MaskedArray:
    """``(b08 - b04) / (b08 + b04)`` on the CF store's physical values, in float32 as the kernel gives it.

    Without an item scaling the store is decoded the way xarray does it (``store-cf``): in float64.
    With one, the core scales the raw values in float32, as rio-tiler's ``unscale`` does.
    """
    physical = {}
    for name in ("b04", "b08"):
        raw = mini_zarr_cf.raw_band(name)
        if item_scaling:
            data = raw.astype("float32")
            numpy.multiply(data, numpy.array([mini_zarr_cf.SCALE]), out=data, casting="unsafe")
            numpy.add(data, numpy.array([mini_zarr_cf.OFFSET]), out=data, casting="unsafe")
            physical[name] = data.astype("float64")
        else:
            physical[name] = raw.astype("float64") * mini_zarr_cf.SCALE + mini_zarr_cf.OFFSET
    mask = (mini_zarr_cf.raw_band("b04") == mini_zarr_cf.FILL) | (mini_zarr_cf.raw_band("b08") == mini_zarr_cf.FILL)
    result = ((physical["b08"] - physical["b04"]) / (physical["b08"] + physical["b04"])).astype("float32")
    return numpy.ma.masked_array(result, mask=mask)


def _job_tile(result_path: Path, tile: tuple[int, int, int]) -> numpy.ma.MaskedArray:
    z, x, y = tile
    with Reader(str(result_path)) as reader:
        return reader.tile(x, y, z, resampling_method="nearest", tilesize=256).array[0]


class TestTheTileEqualsTheJobOnTheNativeLevel:
    @pytest.mark.parametrize(
        "expression",
        [NDVI, "where((red > 0.15) & (nir > 0.2), (nir - red) / (nir + red), -1)", "sqrt(abs(nir - red)) + red ** 3"],
    )
    def test_cog_pair_with_scale_and_offset(
        self, client: TestClient, files: dict[str, Path], tmp_path: Path, expression: str
    ) -> None:
        result = run(
            recipe_from_data(_recipe(("red", "nir"), expression), OPERATORS),
            workdir=tmp_path,
            progress=lambda done, total: None,
        )
        compared = masked_compared = 0
        for tile in _tiles():
            response = client.get(_url(tile, expression=expression))
            assert response.status_code == 200, response.text
            from_tile = _decode(response.content)
            from_job = _job_tile(result.path, tile)
            assert numpy.array_equal(from_tile.mask, numpy.ma.getmaskarray(from_job)), tile
            valid = ~from_tile.mask
            assert numpy.array_equal(from_tile.data[valid], from_job.data[valid]), tile
            compared += int(valid.sum())
            masked_compared += int(from_tile.mask.sum())
        assert compared > 1_000_000  # more than a coincidence of a few pixels
        assert masked_compared > 0  # and the nodata corner was among them

    @pytest.mark.parametrize(("group", "item_scaling"), [("r10m", False), ("r10m-scaled", True)])
    def test_the_zarr_with_cf_attributes(
        self, client: TestClient, cf_store: Path, tmp_path: Path, group: str, item_scaling: bool
    ) -> None:
        """Mini-Zarr with CF attributes: the store's own decoding, or the item's scaling on the raw values.

        Two claims. The tile is the formula on exactly the nearest source pixel, everywhere. And the
        job's result read onto the same tile gives the same bytes wherever nearest is unambiguous: the
        Zarr tile and the COG result are warped by two code paths, and where a tile pixel centre lies
        within GDAL's approximation tolerance (``0.125`` px) of a source pixel boundary they may pick
        different neighbours — measured 13 of 3489 pixels, all within 0.003 px of a boundary. The
        COG pair above has no such pixels: both sides use one warp.
        """
        west, south, east, north = transform_bounds(mini_zarr_cf.ITEM_CRS, WGS84_CRS, *mini_zarr_cf.store_bounds())
        tile = WEB_MERCATOR_TMS.tile((west + east) / 2, (south + north) / 2, ZOOM)
        key = f"{group}:b04,b08"
        expression = "(b08 - b04) / (b08 + b04)"
        entry = resolved(
            "ITEM_Z",
            key,
            reader="zarr",
            scale=sources.SCALE if item_scaling else None,
            offset=sources.OFFSET if item_scaling else None,
            href=mini_zarr_cf.GROUP_URL,
            variable="b04,b08",
        )
        entry["bands"] = entry["bands"] * 2
        recipe = {
            "recipe_version": 1,
            "inputs": [
                {"name": "z", "dataset": "synthetic", "groups": [["ITEM_Z"]], "assets": [key], "resolved": [entry]}
            ],
            "aoi": sources.whole(mini_zarr_cf.SIZE, mini_zarr_cf.SIZE, inset=0.0),
            "steps": [{"op": "band_math", "op_version": 1, "params": {"expression": expression}}],
            "output": {"kind": "raster", "format": "cog", "dtype": "float32"},
        }
        result = run(recipe_from_data(recipe, OPERATORS), workdir=tmp_path, progress=lambda done, total: None)
        response = client.get(_url((tile.z, tile.x, tile.y), dataset=ZARR, assets=(key,), expression=expression))
        assert response.status_code == 200, response.text
        from_tile = _decode(response.content)
        from_job = _job_tile(result.path, (tile.z, tile.x, tile.y))

        col, row = _source_position(tile)
        inside = (col >= 0) & (col < mini_zarr_cf.SIZE) & (row >= 0) & (row < mini_zarr_cf.SIZE)
        picked_row = numpy.clip(numpy.floor(row).astype(int), 0, mini_zarr_cf.SIZE - 1)
        picked_col = numpy.clip(numpy.floor(col).astype(int), 0, mini_zarr_cf.SIZE - 1)
        exact = _zarr_ndvi(item_scaling)[picked_row, picked_col]
        valid = inside & ~numpy.ma.getmaskarray(exact)
        assert valid.sum() > 1000
        assert numpy.array_equal(~from_tile.mask, valid)
        assert numpy.array_equal(from_tile.data[valid], numpy.ma.getdata(exact)[valid])

        near_a_boundary = (numpy.abs(col - numpy.round(col)) <= 0.125) | (numpy.abs(row - numpy.round(row)) <= 0.125)
        job_mask = numpy.ma.getmaskarray(from_job)
        differing = (from_tile.mask != job_mask) | (~from_tile.mask & ~job_mask & (from_tile.data != from_job.data))
        assert not (differing & ~near_a_boundary).any()
        assert differing.sum() < 0.02 * valid.sum()

    def test_a_tile_below_the_native_level_is_a_preview_and_not_asserted_equal(
        self, client: TestClient, files: dict[str, Path], tmp_path: Path
    ) -> None:
        """z11 reads an overview: it answers (200), and §6.3 promises nothing more for it."""
        west, south, east, north = transform_bounds(
            sources.CRS, WGS84_CRS, sources.ORIGIN_X, sources.ORIGIN_Y - 6000, sources.ORIGIN_X + 7000, sources.ORIGIN_Y
        )
        tile = WEB_MERCATOR_TMS.tile((west + east) / 2, (south + north) / 2, 11)
        response = client.get(_url((tile.z, tile.x, tile.y)))
        assert response.status_code == 200


# --- the route and its refusals -----------------------------------------------------------------


class TestRefusals:
    def test_the_free_expression_of_titiler_is_a_400_pointing_at_the_operator(self, client: TestClient) -> None:
        response = client.get(
            f"/collections/{COG}/items/{ITEM}/tiles/WebMercatorQuad/14/1/1?asset=red&expression=red%2Bred"
        )
        assert response.status_code == 400
        assert "op=band_math" in response.json()["detail"]

    def test_the_free_expression_is_refused_on_every_route_not_only_the_tile(self, client: TestClient) -> None:
        for route in ("statistics", "info", "WebMercatorQuad/tilejson.json"):
            response = client.get(f"/collections/{COG}/items/{ITEM}/{route}?asset=red&expression=red%2Bred")
            assert response.status_code == 400, route
            assert "op=band_math" in response.json()["detail"]

    @pytest.mark.parametrize("query", ["algorithm=hillshade", "algorithm=normalizedIndex&algorithm_params=%7B%7D"])
    def test_an_algorithm_is_a_400_pointing_at_the_operator(self, client: TestClient, query: str) -> None:
        response = client.get(f"/collections/{COG}/items/{ITEM}/tiles/WebMercatorQuad/14/1/1?asset=red&{query}")
        assert response.status_code == 400
        assert "op=band_math" in response.json()["detail"]

    def test_the_refusal_costs_no_request_to_the_source(self, client: TestClient) -> None:
        fetched: list[str] = []
        original = client.app.state.earthx_item_source

        async def counting(dataset_id: str, item_id: str) -> dict[str, Any]:
            fetched.append(item_id)
            return await original(dataset_id, item_id)

        client.app.state.earthx_item_source = counting
        client.get(f"/collections/{COG}/items/{ITEM}/tiles/WebMercatorQuad/14/1/1?asset=red&expression=red")
        client.get(_url((14, 1, 1), expression="log(red)"))
        client.get(_url((14, 1, 1), expression="red", dataset=NO_BAND_MATH.dataset_id))
        assert fetched == []

    def test_the_openapi_schema_has_no_free_expression_and_no_free_url(self, client: TestClient) -> None:
        schema = client.get("/openapi.json").json()
        names = {
            parameter["name"]
            for path in schema["paths"].values()
            for operation in path.values()
            for parameter in operation.get("parameters", [])
        }
        assert {"expression", "algorithm", "algorithm_params", "url"}.isdisjoint(names)
        assert {"op", "op_version", "params", "asset"} <= names

    def test_several_assets_without_an_operator_are_a_400(self, client: TestClient) -> None:
        response = client.get(f"/collections/{COG}/items/{ITEM}/tiles/WebMercatorQuad/14/1/1?asset=red&asset=nir")
        assert response.status_code == 400
        assert "together with op" in response.json()["detail"]

    def test_no_asset_is_still_a_422_from_the_schema(self, client: TestClient) -> None:
        assert client.get(f"/collections/{COG}/items/{ITEM}/tiles/WebMercatorQuad/14/1/1").status_code == 422

    @pytest.mark.parametrize(
        "overrides",
        [{"op_version": None}, {"params": None}, {"op": None}],
        ids=["no version", "no params", "no op"],
    )
    def test_an_operator_needs_all_three_parts(self, client: TestClient, overrides: dict) -> None:
        response = client.get(_url((14, 1, 1), **overrides))
        assert response.status_code == 400
        assert "go together" in response.json()["detail"]

    def test_each_part_once(self, client: TestClient) -> None:
        response = client.get(_url((14, 1, 1), extra="&op=band_math"))
        assert response.status_code == 400

    @pytest.mark.parametrize("version", ["x", "1.0", "-1", "0"])
    def test_a_version_that_is_not_a_positive_whole_number_is_refused_not_a_500(
        self, client: TestClient, version: str
    ) -> None:
        # "x", "1.0": the path dependency (400); "-1", "0": the schema (422) or no such version (422).
        assert client.get(_url((14, 1, 1), op_version=version)).status_code in (400, 422)

    @pytest.mark.parametrize(("op", "version"), [("nonesuch", "1"), ("band_math", "2"), ("band_math", "99")])
    def test_an_operator_or_version_the_platform_does_not_know_is_a_422(
        self, client: TestClient, op: str, version: str
    ) -> None:
        response = client.get(_url((14, 1, 1), op=op, op_version=version))
        assert response.status_code == 422
        assert "not available" in response.json()["detail"]

    def test_an_operator_that_does_not_run_as_a_tile_is_a_422(self, client: TestClient) -> None:
        raw = '{"crs": "EPSG:3035", "resolution": 10, "resampling": "nearest"}'
        response = client.get(_url((14, 1, 1), op="reproject", op_version="2", params=raw))
        assert response.status_code == 422
        assert "does not run as a tile" in response.json()["detail"]

    @pytest.mark.parametrize(
        "raw",
        ["not json", "[]", "null", '{"expression": 1}', '{"expression": "red", "unscale": true}', '{"expression": ""}'],
    )
    def test_params_that_are_not_the_operators_form_are_a_400(self, client: TestClient, raw: str) -> None:
        response = client.get(_url((14, 1, 1), params=raw))
        assert response.status_code == 400
        assert response.json()["detail"].startswith("params: ")

    @pytest.mark.parametrize(
        "expression",
        [
            "log(red)", "exp(red)", "sin(red)", "red ** 51", "red ** 0.5", "red.real", "red % 2",
            "red & nir", "~red", "red | (nir > 0)", "__import__('os')", "red;nir", "red" * 100,
        ],
    )
    def test_an_expression_outside_r5_is_a_400_from_the_check_and_never_a_500_from_numexpr(
        self, client: TestClient, expression: str
    ) -> None:
        response = client.get(_url((14, 1, 1), expression=expression))
        assert response.status_code == 400, response.text
        assert response.json()["detail"].startswith("params: ")
        assert "numexpr" not in response.json()["detail"].lower()

    def test_the_text_of_a_refusal_does_not_echo_the_expression(self, client: TestClient) -> None:
        marker = "band_that_should_not_be_echoed"
        response = client.get(_url((14, 1, 1), expression=f"{marker} % 2"))
        assert response.status_code == 400 and marker not in response.text

    def test_a_params_longer_than_the_limit_is_a_400(self, client: TestClient) -> None:
        response = client.get(_url((14, 1, 1), params="x" * 3000))
        assert response.status_code == 400

    def test_a_band_the_assets_do_not_have_is_a_422_naming_the_bands(self, client: TestClient) -> None:
        response = client.get(_url(_tiles()[0], expression="swir - red"))
        assert response.status_code == 422
        assert "swir" in response.json()["detail"] and "red, nir" in response.json()["detail"]

    def test_a_dataset_without_the_capability_is_a_422(self, client: TestClient) -> None:
        response = client.get(_url(_tiles()[0], dataset=NO_BAND_MATH.dataset_id))
        assert response.status_code == 422
        assert "band_math" in response.json()["detail"]

    def test_an_operator_needs_the_processing_licence_which_display_does_not_give(self, client: TestClient) -> None:
        response = client.get(_url(_tiles()[0], dataset=DISPLAY_ONLY.dataset_id))
        assert response.status_code == 422
        assert "does not allow processing" in response.json()["detail"]

    @pytest.mark.parametrize("route", ["statistics", "info", "point/9.0,47.0"])
    def test_an_operator_is_for_tiles_and_their_tilejson_only(self, client: TestClient, route: str) -> None:
        query = f"asset=red&asset=nir&op=band_math&op_version=1&params={quote(json.dumps({'expression': NDVI}))}"
        response = client.get(f"/collections/{COG}/items/{ITEM}/{route}?{query}")
        assert response.status_code == 400
        assert "tiles and their TileJSON only" in response.json()["detail"]

    def test_the_same_asset_twice_is_a_400(self, client: TestClient) -> None:
        assert client.get(_url(_tiles()[0], assets=("red", "red"), expression="red")).status_code == 400

    def test_more_than_sixteen_assets_is_a_400(self, client: TestClient) -> None:
        assets = tuple(f"a{i}" for i in range(17))
        assert client.get(_url(_tiles()[0], assets=assets, expression="a0")).status_code == 400

    @pytest.mark.parametrize("option", ["bidx=1", "unscale=true", "nodata=0", "rescale=0,1&resampling=bilinear"])
    def test_options_that_would_change_the_values_are_refused(self, client: TestClient, option: str) -> None:
        response = client.get(_url(_tiles()[0], extra=f"&{option}"))
        assert response.status_code == 400, response.text

    def test_an_asset_the_item_lacks_is_a_404(self, client: TestClient) -> None:
        assert client.get(_url(_tiles()[0], assets=("red", "swir"), expression="red")).status_code == 404

    def test_an_asset_on_a_host_the_dataset_does_not_declare_is_a_502_as_before(self, client: TestClient) -> None:
        response = client.get(_url(_tiles()[0], assets=("red", "elsewhere"), expression="red"))
        assert response.status_code == 502
        assert "asset_hosts" in response.json()["detail"]

    def test_item_and_file_that_disagree_on_the_scaling_are_a_502_not_a_wrong_picture(self, client: TestClient) -> None:
        response = client.get(_url(_tiles()[0], assets=("wrongscale",), expression="wrongscale"))
        assert response.status_code == 502
        assert "scaled differently" in response.json()["detail"]

    def test_an_asset_nothing_declares_a_scaling_for_is_read_as_it_is(self, client: TestClient) -> None:
        """`bare`: no `raster:bands` in the item, no tags in the file (the DEM's case): raw values, no error."""
        response = client.get(_url(_tiles()[0], assets=("bare",), expression="bare + 0"))
        assert response.status_code == 200
        valid = _decode(response.content).compressed()
        assert valid.min() >= 900  # counts, not reflectance: 0.0001 · 900 - 0.1 would be negative


# --- what the tile does not change --------------------------------------------------------------


class TestWhatStaysAsItWas:
    def test_a_single_asset_tile_without_an_operator_is_unchanged(self, client: TestClient) -> None:
        z, x, y = _tiles()[0]
        response = client.get(
            f"/collections/{COG}/items/{ITEM}/tiles/WebMercatorQuad/{z}/{x}/{y}.png?asset=red&rescale=0,60000"
        )
        assert response.status_code == 200

    def test_tilejson_carries_the_operator_into_its_tile_urls(self, client: TestClient) -> None:
        query = f"asset=red&asset=nir&op=band_math&op_version=1&params={quote(json.dumps({'expression': NDVI}))}"
        response = client.get(f"/collections/{COG}/items/{ITEM}/WebMercatorQuad/tilejson.json?{query}")
        assert response.status_code == 200, response.text
        (template,) = response.json()["tiles"]
        carried = parse_qs(urlsplit(template).query)
        assert carried["asset"] == ["red", "nir"]
        assert (carried["op"], carried["op_version"]) == (["band_math"], ["1"])
        assert json.loads(carried["params"][0]) == {"expression": NDVI}

    def test_the_url_names_no_recipe_no_hash_and_no_aoi(self, client: TestClient) -> None:
        (template,) = client.get(
            f"/collections/{COG}/items/{ITEM}/WebMercatorQuad/tilejson.json?asset=red&op=band_math&op_version=1"
            f"&params={quote(json.dumps({'expression': 'red'}))}"
        ).json()["tiles"]
        for forbidden in ("recipe", "hash", "aoi", "geometry"):
            assert forbidden not in template.lower()

    def test_the_same_url_gives_the_same_bytes_twice(self, client: TestClient) -> None:
        url = _url(_tiles()[0])
        assert client.get(url).content == client.get(url).content
