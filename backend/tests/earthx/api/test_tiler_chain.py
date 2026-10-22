"""A chain of operators as one tile: the refusals and T1 against T2 (plan M4-18 §3.4, §3.6; adr/0014 §6.1, §6.4).

``op``, ``op_version`` and ``params`` repeat in the tile URL, equally often and in the order of the steps. The
synthetic item carries two 10 m bands (``red``, ``nir``) and a 20 m classification layer (``scl``); the CF
Mini-Zarr carries ``b04``, ``b08`` and an ``scl`` group of the same kind. The chain ``mask → band_math`` is the
reason for the feature (a masked NDVI), the others show that the kernels, not the pair, are chained.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Sequence
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urlsplit

import numpy
import pytest
from fastapi.testclient import TestClient
from rasterio.io import MemoryFile
from rasterio.warp import transform_bounds
from rio_tiler.constants import WEB_MERCATOR_TMS, WGS84_CRS
from rio_tiler.io import Reader

from earthx.api.tiler import MAX_OPERATOR_PARAMS_CHARS, MAX_OPERATOR_STEPS, build_app
from earthx.gateway import check_url
from earthx.processing import run
from earthx.processing.operators import REGISTRY as OPERATORS
from earthx.processing.recipe import recipe_from_data
from tests.earthx.api.test_tiler_mask_normalize import (
    COG,
    ITEM,
    MASK,
    NO_LAYER,
    NORMALIZE,
    REGISTRY,
    ZARR,
    _hidden_classes,
)
from tests.earthx.api.test_tiler_operator import _BAND, HEIGHT, NDVI, WIDTH, _source_position, _tiles
from tests.earthx.processing import sources
from tests.earthx.processing.recipes import resolved
from tests.earthx.processing.test_mask import scl_layer
from tests.earthx.readers import mini_zarr, mini_zarr_cf

ITEM_JSON = {
    "id": ITEM,
    "type": "Feature",
    "properties": {"proj:code": sources.CRS, "datetime": "2026-01-02T10:00:00Z"},
    "assets": {
        "red": {"href": sources.url("red"), "raster:bands": [_BAND]},
        "nir": {"href": sources.url("nir"), "raster:bands": [_BAND]},
        "scl": {"href": sources.url("scl"), "raster:bands": [{"data_type": "uint8", "nodata": 0}]},
        "r10m": {"href": mini_zarr_cf.GROUP_URL},
        "scl20m": {"href": mini_zarr_cf.SCL_URL},
    },
}

BAND_MATH = {"expression": NDVI}
TO_BYTE = {"in_min": -1.0, "in_max": 1.0, "out_min": 0.0, "out_max": 255.0, "clip": True}
HALVE = {"in_min": 0.0, "in_max": 1.0, "out_min": 0.0, "out_max": 0.5, "clip": False}
CLOUDS_THEN_NDVI = [("mask", MASK), ("band_math", BAND_MATH)]


@pytest.fixture(scope="module")
def files(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    root = tmp_path_factory.mktemp("chain-bands")
    return {
        "red": sources.build_band_cog(root / "red.tif", sources.ramp(WIDTH, HEIGHT, 1200)),
        "nir": sources.build_band_cog(root / "nir.tif", sources.ramp(WIDTH, HEIGHT, 3400)),
        "scl": sources.build_band_cog(
            root / "scl.tif", scl_layer(WIDTH // 2, HEIGHT // 2), scale=None, offset=None, resolution=20.0
        ),
    }


@pytest.fixture(scope="module")
def cf_store(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return mini_zarr_cf.build_mini_zarr_cf(tmp_path_factory.mktemp("chain-cf") / "mini.zarr")


@pytest.fixture
def client(files: dict[str, Path], cf_store: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    sources.serve({sources.url(name): path for name, path in files.items()}, monkeypatch, zarr_root=cf_store)
    for module in ("earthx.readers.cog", "earthx.readers.zarr_reader"):
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


def _query(steps: Sequence[tuple[str, dict | str]], versions: Sequence[int] | None = None) -> list[str]:
    parts = []
    for number, (op, params) in enumerate(steps):
        version = 1 if versions is None else versions[number]
        raw = params if isinstance(params, str) else json.dumps(params)
        parts += [f"op={op}", f"op_version={version}", f"params={quote(raw)}"]
    return parts


def _url(
    tile: tuple[int, int, int],
    steps: Sequence[tuple[str, dict | str]],
    *,
    dataset: str = COG,
    assets: Sequence[str] = ("red", "nir", "scl"),
    versions: Sequence[int] | None = None,
    route: str | None = None,
) -> str:
    z, x, y = tile
    query = [f"asset={quote(a)}" for a in assets] + _query(steps, versions)
    path = route or f"tiles/WebMercatorQuad/{z}/{x}/{y}.tif"
    return f"/collections/{dataset}/items/{ITEM}/{path}?{'&'.join(query)}"


def _decode(content: bytes) -> numpy.ma.MaskedArray:
    """All bands of a tile's GeoTIFF, masked where its last band (the alpha, not positive where invalid) says so.

    A mask leaves the values under it as they were, so NaN is not asserted there.
    """
    with MemoryFile(content) as memory, memory.open() as dataset:
        data, alpha = dataset.read()[:-1], dataset.read(dataset.count)
    return numpy.ma.masked_array(data, mask=numpy.broadcast_to(alpha <= 0, data.shape))


def _job_bands(result_path: Path, tile: tuple[int, int, int]) -> numpy.ma.MaskedArray:
    z, x, y = tile
    with Reader(str(result_path)) as reader:
        return reader.tile(x, y, z, resampling_method="nearest", tilesize=256).array


def _recipe(assets: Sequence[str], chain: Sequence[tuple[str, dict]]) -> dict:
    entries = []
    for asset in assets:
        if asset == "scl":
            entry = resolved(ITEM, asset, href=sources.url(asset), scale=None, offset=None)
            entry["bands"] = [{"data_type": "uint8", "nodata": 0, "scale": None, "offset": None}]
        else:
            entry = resolved(ITEM, asset, href=sources.url(asset), scale=sources.SCALE, offset=sources.OFFSET)
        entries.append(entry)
    return {
        "recipe_version": 1,
        "inputs": [
            {"name": "s2", "dataset": "synthetic", "groups": [[ITEM]], "assets": list(assets), "resolved": entries}
        ],
        "aoi": sources.whole(WIDTH, HEIGHT, inset=0.0),
        "steps": [{"op": op, "op_version": 1, "params": params} for op, params in chain],
        "output": {"kind": "raster", "format": "cog", "dtype": "float32"},
    }


class TestTheChainEqualsTheJobOnTheNativeLevel:
    """§6.4: the tile through the real route against the job, bit for bit, on every tile of the raster."""

    @pytest.mark.parametrize(
        ("assets", "chain"),
        [
            (("red", "nir", "scl"), CLOUDS_THEN_NDVI),
            (("red", "nir", "scl"), [("mask", MASK), ("normalize", NORMALIZE)]),
            (("red", "nir", "scl"), [*CLOUDS_THEN_NDVI, ("normalize", TO_BYTE)]),
            (("red", "nir"), [("normalize", HALVE), ("band_math", {"expression": "nir - red"})]),
        ],
        ids=["mask, band math", "mask, normalize", "mask, band math, normalize", "normalize, band math"],
    )
    def test_cog_pair_with_a_nested_layer(self, client: TestClient, tmp_path: Path, assets, chain) -> None:
        result = run(recipe_from_data(_recipe(assets, chain), OPERATORS), workdir=tmp_path, progress=lambda d, t: None)
        compared = masked = 0
        for tile in _tiles():
            response = client.get(_url(tile, chain, assets=assets))
            assert response.status_code == 200, response.text
            from_tile, from_job = _decode(response.content), _job_bands(result.path, tile)
            assert from_tile.shape == from_job.shape, tile
            assert numpy.array_equal(from_tile.mask, numpy.ma.getmaskarray(from_job)), tile
            valid = ~from_tile.mask
            assert numpy.array_equal(from_tile.data[valid], from_job.data[valid]), tile
            compared += int(valid.sum())
            masked += int(from_tile.mask.sum())
        assert compared > 10_000 and masked > 0

    def test_the_mask_of_the_first_step_reaches_the_index_of_the_second(self, client: TestClient) -> None:
        tile = _tiles()[1]
        plain = _decode(client.get(_url(tile, [("band_math", BAND_MATH)], assets=("red", "nir"))).content)
        chained = _decode(client.get(_url(tile, CLOUDS_THEN_NDVI)).content)
        assert chained.shape[0] == plain.shape[0] == 1
        assert chained.mask.sum() > plain.mask.sum()
        assert (chained.mask | ~plain.mask).all()  # nothing is visible that the plain index hid
        both = ~chained.mask
        assert numpy.array_equal(chained.data[both], plain.data[both])

    def test_a_single_step_keeps_its_messages(self, client: TestClient) -> None:
        tile = _tiles()[1]
        assert client.get(_url(tile, [("mask", MASK)])).status_code == 200
        response = client.get(_url(tile, [("mask", {"source": "red", "classes": [3]})]))
        assert response.status_code == 422 and response.json()["detail"].startswith("'mask' cannot run here")
        response = client.get(_url(tile, [("normalize", {**NORMALIZE, "in_min": 1.0})]))
        assert response.status_code == 400 and response.json()["detail"].startswith("params: ")

    def test_the_order_of_the_steps_is_the_order_of_the_url(self, client: TestClient) -> None:
        """An offset before a quotient is not an offset after it, so the two orders give two pictures."""
        tile = _tiles()[1]
        shift = {"in_min": 0.0, "in_max": 1.0, "out_min": 1.0, "out_max": 2.0, "clip": False}
        quotient = {"expression": "nir / red"}
        assets = ("red", "nir")
        first = _decode(client.get(_url(tile, [("normalize", shift), ("band_math", quotient)], assets=assets)).content)
        second = _decode(client.get(_url(tile, [("band_math", quotient), ("normalize", shift)], assets=assets)).content)
        valid = ~first.mask & ~second.mask
        assert valid.sum() > 5_000
        assert numpy.array_equal(first.mask, second.mask)
        assert not numpy.allclose(first.data[valid], second.data[valid])


# --- the CF Mini-Zarr -----------------------------------------------------------------------------------


def _zarr_recipe(expression: str) -> dict:
    group = resolved(
        "ITEM_Z",
        "r10m:b04,b08",
        reader="zarr",
        scale=None,
        offset=None,
        href=mini_zarr_cf.GROUP_URL,
        variable="b04,b08",
    )
    group["bands"] = group["bands"] * 2
    layer = resolved(
        "ITEM_Z", "scl20m:scl", reader="zarr", scale=None, offset=None, href=mini_zarr_cf.SCL_URL, variable="scl"
    )
    layer["bands"] = [{"data_type": "uint8", "nodata": 0, "scale": None, "offset": None}]
    return {
        "recipe_version": 1,
        "inputs": [
            {
                "name": "z",
                "dataset": "synthetic",
                "groups": [["ITEM_Z"]],
                "assets": ["r10m:b04,b08", "scl20m:scl"],
                "resolved": [group, layer],
            }
        ],
        "aoi": sources.whole(mini_zarr_cf.SIZE, mini_zarr_cf.SIZE, inset=0.0),
        "steps": [
            {"op": "mask", "op_version": 1, "params": MASK},
            {"op": "band_math", "op_version": 1, "params": {"expression": expression}},
        ],
        "output": {"kind": "raster", "format": "cog", "dtype": "float32"},
    }


class TestTheChainEqualsTheJobOnZarr:
    """§15d: on Zarr the tile and the job may pick different neighbours within GDAL's tolerance of a pixel boundary.

    Two claims, as for each operator alone. The tile is, in every pixel, the index on the nearest source pixel of
    the 10 m bands, where the nearest pixel of the 20 m layer does not hold a hidden class. And the job's result
    read onto the same tile gives the same values and the same mask wherever no pixel centre lies within 0.125
    source pixel of a boundary of either grid, and differs in less than 5 % of the valid pixels.
    """

    def test_a_masked_index_over_a_20_m_layer_in_a_zarr_store(self, client: TestClient, tmp_path: Path) -> None:
        expression = "(b08 - b04) / (b08 + b04)"
        west, south, east, north = transform_bounds(mini_zarr_cf.ITEM_CRS, WGS84_CRS, *mini_zarr_cf.store_bounds())
        tile = WEB_MERCATOR_TMS.tile((west + east) / 2, (south + north) / 2, 14)
        key = ("r10m:b04,b08", "scl20m:scl")
        result = run(
            recipe_from_data(_zarr_recipe(expression), OPERATORS), workdir=tmp_path, progress=lambda d, t: None
        )
        assert result.meta.resampled is True and [band.name for band in result.meta.bands] == ["band_math"]
        response = client.get(
            _url(
                (tile.z, tile.x, tile.y),
                [("mask", MASK), ("band_math", {"expression": expression})],
                dataset=ZARR,
                assets=key,
            )
        )
        assert response.status_code == 200, response.text
        from_tile = _decode(response.content)[0]
        from_job = _job_bands(result.path, (tile.z, tile.x, tile.y))[0]

        col, row = _source_position(tile)
        size = mini_zarr_cf.SIZE
        inside = (col >= 0) & (col < size) & (row >= 0) & (row < size)
        fine_row = numpy.clip(numpy.floor(row).astype(int), 0, size - 1)
        fine_col = numpy.clip(numpy.floor(col).astype(int), 0, size - 1)
        coarse_row = numpy.clip(numpy.floor(row / 2).astype(int), 0, mini_zarr_cf.SCL_SIZE - 1)
        coarse_col = numpy.clip(numpy.floor(col / 2).astype(int), 0, mini_zarr_cf.SCL_SIZE - 1)
        raw = {name: mini_zarr_cf.raw_band(name) for name in ("b04", "b08")}
        band_fill = (raw["b04"] == mini_zarr_cf.FILL) | (raw["b08"] == mini_zarr_cf.FILL)
        expected_hidden = _hidden_classes()[coarse_row, coarse_col] | band_fill[fine_row, fine_col]
        valid = inside & ~expected_hidden
        assert valid.sum() > 200 and (inside & expected_hidden).sum() > 200  # both outcomes are in the tile
        assert numpy.array_equal(~from_tile.mask, valid)
        physical = {
            name: array.astype("float64") * mini_zarr_cf.SCALE + mini_zarr_cf.OFFSET for name, array in raw.items()
        }
        index = ((physical["b08"] - physical["b04"]) / (physical["b08"] + physical["b04"]))[fine_row, fine_col]
        numpy.testing.assert_allclose(from_tile.data[valid], index[valid], rtol=1e-5)

        def near(position: numpy.ndarray, scale: float) -> numpy.ndarray:
            scaled = position / scale
            return numpy.abs(scaled - numpy.round(scaled)) <= 0.125

        near_a_boundary = near(col, 1) | near(row, 1) | near(col, 2) | near(row, 2)
        job_mask = numpy.ma.getmaskarray(from_job)
        differing = (from_tile.mask != job_mask) | (~from_tile.mask & ~job_mask & (from_tile.data != from_job.data))
        assert not (differing & ~near_a_boundary).any()
        assert differing.sum() < 0.05 * valid.sum()


# --- the route and its refusals -----------------------------------------------------------------------


def _fetches(client: TestClient) -> list[str]:
    """The item ids the source is asked for from now on; the list fills as requests arrive."""
    fetched: list[str] = []
    original = client.app.state.earthx_item_source

    async def counting(dataset_id: str, item_id: str) -> dict[str, Any]:
        fetched.append(item_id)
        return await original(dataset_id, item_id)

    client.app.state.earthx_item_source = counting
    return fetched


class TestTheNumberOfSteps:
    def test_four_steps_are_the_most(self, client: TestClient) -> None:
        chain = [("normalize", HALVE)] * MAX_OPERATOR_STEPS
        assert client.get(_url(_tiles()[0], chain, assets=("red",))).status_code == 200
        response = client.get(_url(_tiles()[0], [*chain, ("normalize", HALVE)], assets=("red",)))
        assert response.status_code == 400 and f"at most {MAX_OPERATOR_STEPS} steps" in response.json()["detail"]

    @pytest.mark.parametrize(
        "query",
        [
            "op=mask&op=band_math&op_version=1&params={}",
            "op=mask&op_version=1&op_version=1&params={}",
            "op=mask&op_version=1&params={}&params={}",
            "op=mask&op=band_math&op_version=1&op_version=1&params={}",
            "op=mask&op=band_math&op_version=1&op_version=1",
            "op=mask&op=band_math",
        ],
    )
    def test_the_three_parts_come_equally_often(self, client: TestClient, query: str) -> None:
        response = client.get(f"/collections/{COG}/items/{ITEM}/tiles/WebMercatorQuad/14/1/1?asset=red&{query}")
        assert response.status_code == 400 and "equally often" in response.json()["detail"]

    def test_the_refusal_of_the_number_costs_no_request_to_the_source(self, client: TestClient) -> None:
        fetched = _fetches(client)
        too_many = client.get(_url(_tiles()[0], [("normalize", HALVE)] * (MAX_OPERATOR_STEPS + 1), assets=("red",)))
        unequal = client.get(f"/collections/{COG}/items/{ITEM}/tiles/WebMercatorQuad/14/1/1?asset=red&op=mask&op=mask")
        assert (too_many.status_code, unequal.status_code) == (400, 400)
        assert fetched == []


class TestEveryStepIsJudgedOnItsOwn:
    def test_a_step_that_does_not_run_as_a_tile_names_its_place(self, client: TestClient) -> None:
        reproject = {"crs": "EPSG:3035", "resolution": 30}
        response = client.get(_url(_tiles()[0], [("mask", MASK), ("reproject", reproject)], versions=(1, 2)))
        assert response.status_code == 422, response.text
        assert (
            response.json()["detail"].startswith("step 2: ") and "does not run as a tile" in response.json()["detail"]
        )

    def test_an_unknown_version_names_its_place(self, client: TestClient) -> None:
        response = client.get(_url(_tiles()[0], CLOUDS_THEN_NDVI, versions=(1, 9)))
        assert response.status_code == 422 and response.json()["detail"].startswith("step 2: ")

    def test_malformed_parameters_of_a_later_step_are_a_400(self, client: TestClient) -> None:
        response = client.get(_url(_tiles()[0], [("mask", MASK), ("normalize", {**NORMALIZE, "in_min": 1.0})]))
        assert response.status_code == 400 and response.json()["detail"].startswith("step 2: params: ")

    def test_parameters_longer_than_the_limit_of_a_later_step_are_a_400(self, client: TestClient) -> None:
        long = {"expression": "red + " * (MAX_OPERATOR_PARAMS_CHARS // 6) + "red"}
        response = client.get(_url(_tiles()[0], [("mask", MASK), ("band_math", long)]))
        assert response.status_code == 400 and response.json()["detail"].startswith("step 2: params are at most")

    @pytest.mark.parametrize("version", ["x", "1.0", "", "-1", "\u0661", "\uff11"], ids=repr)
    def test_a_version_that_is_not_a_whole_number_of_digits_is_a_400_before_any_request(
        self, client: TestClient, version: str
    ) -> None:
        fetched = _fetches(client)
        base = f"/collections/{COG}/items/{ITEM}/tiles/WebMercatorQuad/14/1/1?asset=red&asset=nir&asset=scl"
        mask = f"op=mask&op_version=1&params={quote(json.dumps(MASK))}"
        step = f"op=band_math&op_version={quote(version)}&params={quote(json.dumps(BAND_MATH))}"
        for query in (step, f"{mask}&{step}"):
            response = client.get(f"{base}&{query}")
            assert response.status_code == 400, (version, response.text)
            assert "op_version is a whole number" in response.json()["detail"]
        assert response.json()["detail"].startswith("step 2: ")
        assert fetched == []

    def test_empty_parts_are_a_400_before_any_request(self, client: TestClient) -> None:
        fetched = _fetches(client)
        base = f"/collections/{COG}/items/{ITEM}/tiles/WebMercatorQuad/14/1/1?asset=red&asset=nir&asset=scl"
        mask = f"op=mask&op_version=1&params={quote(json.dumps(MASK))}"
        for query in (
            "op=&op_version=&params=",
            f"{mask}&op=&op_version=1&params={{}}",
            f"{mask}&op=band_math&op_version=1&params=",
        ):
            response = client.get(f"{base}&{query}")
            assert response.status_code in (400, 422), (query, response.text)
        assert fetched == []

    def test_a_dataset_that_does_not_allow_the_first_step_is_a_422_before_any_request(self, client: TestClient) -> None:
        fetched = _fetches(client)
        response = client.get(_url(_tiles()[0], CLOUDS_THEN_NDVI, dataset=NO_LAYER.dataset_id))
        assert response.status_code == 422 and response.json()["detail"].startswith("step 1: ")
        assert "masking" in response.json()["detail"]
        wrong_layer = client.get(
            _url(_tiles()[0], [("mask", {"source": "red", "classes": [3]}), ("band_math", BAND_MATH)])
        )
        assert wrong_layer.status_code == 422 and "masks with its layer 'scl'" in wrong_layer.json()["detail"]
        assert fetched == []

    def test_a_band_the_first_step_took_away_cannot_be_named_by_the_next(self, client: TestClient) -> None:
        response = client.get(_url(_tiles()[0], [("mask", MASK), ("band_math", {"expression": "scl + red"})]))
        assert response.status_code == 422, response.text
        assert "scl" in response.json()["detail"]

    def test_a_second_mask_has_no_layer_left(self, client: TestClient) -> None:
        response = client.get(_url(_tiles()[0], [("mask", MASK), ("mask", MASK)]))
        assert response.status_code == 422 and "scl" in response.json()["detail"]

    def test_a_first_step_that_names_a_missing_band_is_a_422_before_the_first_pixel(self, client: TestClient) -> None:
        response = client.get(_url(_tiles()[0], CLOUDS_THEN_NDVI, assets=("red", "nir")))
        assert response.status_code == 422 and "scl" in response.json()["detail"]


class TestTilejson:
    def test_the_chain_travels_into_the_tile_urls(self, client: TestClient) -> None:
        response = client.get(_url((14, 1, 1), CLOUDS_THEN_NDVI, route="WebMercatorQuad/tilejson.json"))
        assert response.status_code == 200, response.text
        (template,) = response.json()["tiles"]
        carried = parse_qs(urlsplit(template).query)
        assert carried["asset"] == ["red", "nir", "scl"]
        assert (carried["op"], carried["op_version"]) == (["mask", "band_math"], ["1", "1"])
        assert [json.loads(raw) for raw in carried["params"]] == [MASK, BAND_MATH]

    def test_the_chain_is_for_tiles_and_their_tilejson_only(self, client: TestClient) -> None:
        for route in ("statistics", "info"):
            response = client.get(_url((14, 1, 1), CLOUDS_THEN_NDVI, route=route))
            assert response.status_code == 400 and "tiles and their TileJSON only" in response.json()["detail"]
