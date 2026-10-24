"""``mask`` and ``normalize`` as tiles: the refusals and T1 against T2 (plan M4-18 §3.4, §3.6; adr/0014 §6.2-§6.4).

One operator per tile, as ``band_math`` has it; the chain of several is in ``test_tiler_chain.py``. The synthetic item carries a 10 m
band (``red``) and a 20 m classification layer (``scl``), so a tile with ``mask`` also reads a nested grid; the CF
Mini-Zarr carries the same pair (``b04`` and a ``scl`` group), for the comparison on Zarr.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path
from typing import Any
from urllib.parse import quote

import numpy
import pytest
from fastapi.testclient import TestClient
from rasterio.io import MemoryFile
from rasterio.warp import transform_bounds
from rio_tiler.constants import WEB_MERCATOR_TMS, WGS84_CRS

from earthx.api.tiler import build_app
from earthx.catalog.datasets import SENTINEL_2_L2A, SENTINEL_2_L2A_ZARR3
from earthx.catalog.registry import DatasetRegistry, LicenseTier
from earthx.gateway import check_url
from earthx.processing import run
from earthx.processing.operators import REGISTRY as OPERATORS
from earthx.processing.recipe import recipe_from_data
from tests.earthx.api.test_tiler_operator import HEIGHT, WIDTH, _job_tile, _source_position, _tiles
from tests.earthx.processing import sources
from tests.earthx.processing.recipes import resolved
from tests.earthx.processing.test_mask import scl_layer
from tests.earthx.readers import mini_zarr, mini_zarr_cf

ITEM = "ITEM_A"
COG = "synthetic-cog"
ZARR = "synthetic-zarr"
MASK = {"source": "scl", "classes": [3, 8, 9, 10]}
NORMALIZE = {"in_min": 0.0, "in_max": 0.5, "out_min": 0.0, "out_max": 255.0, "clip": True}

COG_DATASET = replace(
    SENTINEL_2_L2A, dataset_id=COG, source=replace(SENTINEL_2_L2A.source, asset_hosts=(sources.HOST,))
)
ZARR_DATASET = replace(
    SENTINEL_2_L2A_ZARR3, dataset_id=ZARR, source=replace(SENTINEL_2_L2A_ZARR3.source, asset_hosts=(mini_zarr.HOST,))
)
NO_LAYER = replace(
    COG_DATASET,
    dataset_id="synthetic-no-layer",
    capabilities=replace(COG_DATASET.capabilities, masking=False),
    mask=None,
)
NO_NORMALIZE = replace(
    COG_DATASET,
    dataset_id="synthetic-no-normalize",
    capabilities=replace(COG_DATASET.capabilities, normalization=False),
)
DISPLAY_ONLY = replace(
    COG_DATASET, dataset_id="synthetic-display", license=replace(COG_DATASET.license, tier=LicenseTier.DISPLAY)
)
REGISTRY = DatasetRegistry((COG_DATASET, ZARR_DATASET, NO_LAYER, NO_NORMALIZE, DISPLAY_ONLY))

_BAND = {"data_type": "uint16", "nodata": 0, "raster:scale": sources.SCALE, "raster:offset": sources.OFFSET}
ITEM_JSON = {
    "id": ITEM,
    "type": "Feature",
    "properties": {"proj:code": sources.CRS, "datetime": "2026-01-02T10:00:00Z"},
    "assets": {
        "red": {"href": sources.url("red"), "raster:bands": [_BAND]},
        "scl": {"href": sources.url("scl"), "raster:bands": [{"data_type": "uint8", "nodata": 0}]},
        "r10m": {"href": mini_zarr_cf.GROUP_URL},
        "scl20m": {"href": mini_zarr_cf.SCL_URL},
    },
}


@pytest.fixture(scope="module")
def files(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    root = tmp_path_factory.mktemp("mask-bands")
    return {
        "red": sources.build_band_cog(root / "red.tif", sources.ramp(WIDTH, HEIGHT, 1200)),
        "scl": sources.build_band_cog(
            root / "scl.tif", scl_layer(WIDTH // 2, HEIGHT // 2), scale=None, offset=None, resolution=20.0
        ),
    }


@pytest.fixture(scope="module")
def cf_store(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return mini_zarr_cf.build_mini_zarr_cf(tmp_path_factory.mktemp("mask-cf") / "mini.zarr")


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


def _url(tile, op: str, params: dict | str, *, dataset: str = COG, assets=("red", "scl"), form: str = "tif") -> str:
    z, x, y = tile
    raw = params if isinstance(params, str) else json.dumps(params)
    query = [f"asset={quote(a)}" for a in assets] + [f"op={op}", "op_version=1", f"params={quote(raw)}"]
    return f"/collections/{dataset}/items/{ITEM}/tiles/WebMercatorQuad/{z}/{x}/{y}.{form}?{'&'.join(query)}"


def _decode(content: bytes) -> numpy.ma.MaskedArray:
    """Band 1 of a tile's GeoTIFF, masked where band 2 (the alpha, negative where invalid) says so.

    Unlike band math, ``mask`` leaves the values under the mask as they were, so NaN is not asserted there.
    """
    with MemoryFile(content) as memory, memory.open() as dataset:
        assert dataset.count == 2
        data, alpha = dataset.read(1), dataset.read(2)
    return numpy.ma.masked_array(data, mask=alpha <= 0)


def _recipe(assets: tuple[str, ...], step: dict) -> dict:
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
        "inputs": [{"name": "s2", "dataset": "synthetic", "groups": [[ITEM]], "assets": list(assets), "resolved": entries}],
        "aoi": sources.whole(WIDTH, HEIGHT, inset=0.0),
        "steps": [step],
        "output": {"kind": "raster", "format": "cog", "dtype": "float32"},
    }


class TestTheTileEqualsTheJobOnTheNativeLevel:
    @pytest.mark.parametrize(
        ("assets", "op", "params"),
        [
            (("red", "scl"), "mask", MASK),
            (("red", "scl"), "mask", {"source": "scl", "classes": [4, 5, 6, 7, 8, 9, 10, 11]}),
            (("red",), "normalize", NORMALIZE),
            (("red",), "normalize", {**NORMALIZE, "clip": False, "out_min": 1.0, "out_max": -1.0}),
        ],
        ids=["mask", "mask most classes", "normalize", "normalize reversed, unclipped"],
    )
    def test_cog_pair_with_a_nested_layer(
        self, client: TestClient, tmp_path: Path, assets: tuple[str, ...], op: str, params: dict
    ) -> None:
        step = {"op": op, "op_version": 1, "params": params}
        result = run(recipe_from_data(_recipe(assets, step), OPERATORS), workdir=tmp_path, progress=lambda d, t: None)
        compared = masked = 0
        for tile in _tiles():
            response = client.get(_url(tile, op, params, assets=assets))
            assert response.status_code == 200, response.text
            from_tile, from_job = _decode(response.content), _job_tile(result.path, tile)
            assert numpy.array_equal(from_tile.mask, numpy.ma.getmaskarray(from_job)), tile
            valid = ~from_tile.mask
            assert numpy.array_equal(from_tile.data[valid], from_job.data[valid]), tile
            compared += int(valid.sum())
            masked += int(from_tile.mask.sum())
        assert compared > 10_000 and masked > 0

    def test_the_mask_hides_more_with_more_classes(self, client: TestClient) -> None:
        tile = _tiles()[1]
        few = _decode(client.get(_url(tile, "mask", {"source": "scl", "classes": [3]})).content)
        many = _decode(client.get(_url(tile, "mask", MASK)).content)
        assert many.mask.sum() > few.mask.sum() > 0 and (many.mask | ~few.mask).all()


class TestRefusals:
    def test_a_mask_over_a_reflectance_band_is_a_422_naming_the_layer(self, client: TestClient) -> None:
        response = client.get(_url(_tiles()[0], "mask", {"source": "red", "classes": [3]}))
        assert response.status_code == 422
        assert "masks with its layer 'scl'" in response.json()["detail"]

    def test_a_class_the_layer_does_not_have_is_a_422(self, client: TestClient) -> None:
        response = client.get(_url(_tiles()[0], "mask", {"source": "scl", "classes": [3, 12]}))
        assert response.status_code == 422 and "has no class 12" in response.json()["detail"]

    def test_the_layer_missing_from_the_assets_is_a_422_naming_the_bands(self, client: TestClient) -> None:
        response = client.get(_url(_tiles()[0], "mask", MASK, assets=("red",)))
        assert response.status_code == 422 and "scl" in response.json()["detail"]

    def test_a_dataset_without_a_layer_is_a_422(self, client: TestClient) -> None:
        response = client.get(_url(_tiles()[0], "mask", MASK, dataset=NO_LAYER.dataset_id))
        assert response.status_code == 422 and "masking" in response.json()["detail"]

    def test_a_dataset_that_has_not_switched_normalization_on_is_a_422(self, client: TestClient) -> None:
        response = client.get(_url(_tiles()[0], "normalize", NORMALIZE, assets=("red",), dataset=NO_NORMALIZE.dataset_id))
        assert response.status_code == 422 and "normalization" in response.json()["detail"]

    @pytest.mark.parametrize("op", ["mask", "normalize"])
    def test_the_display_tier_does_not_run_operators(self, client: TestClient, op: str) -> None:
        params = MASK if op == "mask" else NORMALIZE
        response = client.get(_url(_tiles()[0], op, params, dataset=DISPLAY_ONLY.dataset_id))
        assert response.status_code == 422 and "does not allow processing" in response.json()["detail"]

    def test_the_refusals_cost_no_request_to_the_source(self, client: TestClient) -> None:
        fetched: list[str] = []
        original = client.app.state.earthx_item_source

        async def counting(dataset_id: str, item_id: str) -> dict[str, Any]:
            fetched.append(item_id)
            return await original(dataset_id, item_id)

        client.app.state.earthx_item_source = counting
        client.get(_url((14, 1, 1), "mask", {"source": "red", "classes": [3]}))
        client.get(_url((14, 1, 1), "mask", {"source": "scl", "classes": [12]}))
        client.get(_url((14, 1, 1), "mask", MASK, dataset=NO_LAYER.dataset_id))
        client.get(_url((14, 1, 1), "normalize", {**NORMALIZE, "in_min": 1.0, "in_max": 1.0}))
        assert fetched == []

    @pytest.mark.parametrize(
        ("op", "params"),
        [
            ("mask", {"source": "scl", "classes": []}),
            ("mask", {"source": "scl", "classes": [8, 3]}),
            ("mask", {"source": "scl", "classes": [True]}),
            ("mask", {"source": "scl"}),
            ("normalize", {**NORMALIZE, "in_min": 0.5}),
            ("normalize", {**NORMALIZE, "clip": "yes"}),
            ("normalize", {"in_min": 0.0}),
            ("normalize", "not json"),
        ],
    )
    def test_malformed_parameters_are_a_400_and_never_a_500(self, client: TestClient, op: str, params) -> None:
        response = client.get(_url(_tiles()[0], op, params, assets=("red",)))
        assert response.status_code == 400 and response.json()["detail"].startswith("params: ")

    def test_an_operator_is_for_tiles_their_tilejson_and_statistics_only(self, client: TestClient) -> None:
        query = f"asset=red&asset=scl&op=mask&op_version=1&params={quote(json.dumps(MASK))}"
        assert client.get(f"/collections/{COG}/items/{ITEM}/info?{query}").status_code == 400


# --- the CF Mini-Zarr: a 10 m band and its 20 m classification layer -------------------------------------


def _zarr_recipe() -> dict:
    band = resolved(
        "ITEM_Z", "r10m:b04", reader="zarr", scale=None, offset=None, href=mini_zarr_cf.GROUP_URL, variable="b04"
    )
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
                "assets": ["r10m:b04", "scl20m:scl"],
                "resolved": [band, layer],
            }
        ],
        "aoi": sources.whole(mini_zarr_cf.SIZE, mini_zarr_cf.SIZE, inset=0.0),
        "steps": [{"op": "mask", "op_version": 1, "params": MASK}],
        "output": {"kind": "raster", "format": "cog", "dtype": "float32"},
    }


def _hidden_classes() -> numpy.ndarray:
    """Per 20 m pixel: is it hidden by ``MASK``? Class 0 is the layer's own fill value."""
    raw = mini_zarr_cf.raw_classes()
    return numpy.isin(raw, MASK["classes"]) | (raw == mini_zarr_cf.FILL)


class TestTheTileEqualsTheJobOnZarr:
    """§15d: on Zarr the tile and the job may pick different neighbours within GDAL's tolerance of a pixel boundary.

    Two claims, as for band math. The tile is, in every pixel, what the formula says on the nearest source pixel
    of each grid: the 10 m band and the 20 m layer. And the job's result read onto the same tile gives the same
    values and the same mask wherever no pixel centre lies within 0.125 source pixel of a boundary of either grid.
    """

    def test_a_mask_over_a_20_m_layer_in_a_zarr_store(self, client: TestClient, tmp_path: Path) -> None:
        west, south, east, north = transform_bounds(mini_zarr_cf.ITEM_CRS, WGS84_CRS, *mini_zarr_cf.store_bounds())
        tile = WEB_MERCATOR_TMS.tile((west + east) / 2, (south + north) / 2, 14)
        key = ("r10m:b04", "scl20m:scl")
        result = run(recipe_from_data(_zarr_recipe(), OPERATORS), workdir=tmp_path, progress=lambda d, t: None)
        assert result.meta.resampled is True and [band.name for band in result.meta.bands] == ["b04"]
        response = client.get(_url((tile.z, tile.x, tile.y), "mask", MASK, dataset=ZARR, assets=key))
        assert response.status_code == 200, response.text
        from_tile = _decode(response.content)
        from_job = _job_tile(result.path, (tile.z, tile.x, tile.y))

        col, row = _source_position(tile)
        size = mini_zarr_cf.SIZE
        inside = (col >= 0) & (col < size) & (row >= 0) & (row < size)
        fine_row = numpy.clip(numpy.floor(row).astype(int), 0, size - 1)
        fine_col = numpy.clip(numpy.floor(col).astype(int), 0, size - 1)
        coarse_row = numpy.clip(numpy.floor(row / 2).astype(int), 0, mini_zarr_cf.SCL_SIZE - 1)
        coarse_col = numpy.clip(numpy.floor(col / 2).astype(int), 0, mini_zarr_cf.SCL_SIZE - 1)
        band_fill = mini_zarr_cf.raw_band("b04")[fine_row, fine_col] == mini_zarr_cf.FILL
        expected_hidden = _hidden_classes()[coarse_row, coarse_col] | band_fill
        valid = inside & ~expected_hidden
        assert valid.sum() > 200 and (inside & expected_hidden).sum() > 200  # both outcomes are in the tile
        assert numpy.array_equal(~from_tile.mask, valid)
        physical = mini_zarr_cf.raw_band("b04").astype("float64") * mini_zarr_cf.SCALE + mini_zarr_cf.OFFSET
        numpy.testing.assert_allclose(from_tile.data[valid], physical[fine_row, fine_col][valid], rtol=1e-6)

        def near(position: numpy.ndarray, scale: float) -> numpy.ndarray:
            scaled = position / scale
            return numpy.abs(scaled - numpy.round(scaled)) <= 0.125

        near_a_boundary = near(col, 1) | near(row, 1) | near(col, 2) | near(row, 2)
        job_mask = numpy.ma.getmaskarray(from_job)
        # The tile hands back the decoded store as it is (float64), the job writes float32: compare as float32.
        tile_values = from_tile.data.astype("float32")
        differing = (from_tile.mask != job_mask) | (~from_tile.mask & ~job_mask & (tile_values != from_job.data))
        assert not (differing & ~near_a_boundary).any()
        assert differing.sum() < 0.05 * valid.sum()

    def test_the_layer_alone_as_a_zarr_asset_is_a_422_for_the_wrong_source(self, client: TestClient) -> None:
        assets = ("r10m:b04", "scl20m:scl")
        response = client.get(_url((14, 1, 1), "mask", {"source": "b04", "classes": [3]}, dataset=ZARR, assets=assets))
        assert response.status_code == 422 and "masks with its layer 'scl'" in response.json()["detail"]
