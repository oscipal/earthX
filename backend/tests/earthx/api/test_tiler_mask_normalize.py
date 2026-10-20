"""``mask`` and ``normalize`` as tiles: the refusals and T1 against T2 (plan M4-18 §3.4, §3.6; adr/0014 §6.2-§6.4).

One operator per tile, as ``band_math`` has it; the chain of several is M4-18b. The synthetic item carries a 10 m
band (``red``) and a 20 m classification layer (``scl``), so a tile with ``mask`` also reads a nested grid.
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

from earthx.api.tiler import build_app
from earthx.catalog.datasets import SENTINEL_2_L2A
from earthx.catalog.registry import DatasetRegistry, LicenseTier
from earthx.gateway import check_url
from earthx.processing import run
from earthx.processing.operators import REGISTRY as OPERATORS
from earthx.processing.recipe import recipe_from_data
from tests.earthx.api.test_tiler_operator import HEIGHT, WIDTH, _job_tile, _tiles
from tests.earthx.processing import sources
from tests.earthx.processing.recipes import resolved
from tests.earthx.processing.test_mask import scl_layer
from tests.earthx.readers import mini_zarr

ITEM = "ITEM_A"
COG = "synthetic-cog"
MASK = {"source": "scl", "classes": [3, 8, 9, 10]}
NORMALIZE = {"in_min": 0.0, "in_max": 0.5, "out_min": 0.0, "out_max": 255.0, "clip": True}

COG_DATASET = replace(
    SENTINEL_2_L2A, dataset_id=COG, source=replace(SENTINEL_2_L2A.source, asset_hosts=(sources.HOST,))
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
REGISTRY = DatasetRegistry((COG_DATASET, NO_LAYER, NO_NORMALIZE, DISPLAY_ONLY))

_BAND = {"data_type": "uint16", "nodata": 0, "raster:scale": sources.SCALE, "raster:offset": sources.OFFSET}
ITEM_JSON = {
    "id": ITEM,
    "type": "Feature",
    "properties": {"proj:code": sources.CRS, "datetime": "2026-01-02T10:00:00Z"},
    "assets": {
        "red": {"href": sources.url("red"), "raster:bands": [_BAND]},
        "scl": {"href": sources.url("scl"), "raster:bands": [{"data_type": "uint8", "nodata": 0}]},
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


@pytest.fixture
def client(files: dict[str, Path], monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    sources.serve({sources.url(name): path for name, path in files.items()}, monkeypatch)
    monkeypatch.setattr(
        "earthx.readers.cog.check_url", lambda url, policy, **_: check_url(url, policy, resolve=mini_zarr.from_memory)
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

    @pytest.mark.parametrize("route", ["statistics", "info"])
    def test_an_operator_is_for_tiles_only(self, client: TestClient, route: str) -> None:
        query = f"asset=red&asset=scl&op=mask&op_version=1&params={quote(json.dumps(MASK))}"
        assert client.get(f"/collections/{COG}/items/{ITEM}/{route}?{query}").status_code == 400
