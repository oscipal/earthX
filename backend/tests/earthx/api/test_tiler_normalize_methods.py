"""``normalize`` version 3 as a tile: T1 against T2 on the native level, and the refusals (NM4-11, adr/0014 §6.2–§6.4).

The numbers of a statistical method stand in the ``params`` of the URL, so the tile needs no statistic of its own and
gives the bytes of the job. The synthetic item carries two 10 m bands (``red``, ``nir``) and a 20 m classification layer
(``scl``), as in ``test_tiler_chain.py``.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Sequence
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from urllib.parse import quote

import numpy
import pytest
from fastapi.testclient import TestClient
from rasterio.io import MemoryFile
from rio_tiler.io import Reader

from earthx.api.tiler import MAX_OPERATOR_PARAMS_CHARS, build_app
from earthx.gateway import check_url
from earthx.processing import run
from earthx.processing.operators import REGISTRY as OPERATORS
from tests.earthx.api.test_tiler_mask_normalize import COG, ITEM, MASK, NO_NORMALIZE, REGISTRY
from tests.earthx.api.test_tiler_operator import _BAND, HEIGHT, NATIVE, WIDTH, _tiles
from tests.earthx.processing import sources
from tests.earthx.processing.recipes import recipe_of_data, resolved
from tests.earthx.processing.test_mask import scl_layer
from tests.earthx.readers import mini_zarr

ITEM_JSON = {
    "id": ITEM,
    "type": "Feature",
    "properties": {"proj:code": sources.CRS, "datetime": "2026-01-02T10:00:00Z"},
    "assets": {
        "red": {"href": sources.url("red"), "raster:bands": [_BAND]},
        "nir": {"href": sources.url("nir"), "raster:bands": [_BAND]},
        "scl": {"href": sources.url("scl"), "raster:bands": [{"data_type": "uint8", "nodata": 0}]},
    },
}

BOTH = ["red", "nir"]
_TARGET = {"out_min": 0.0, "out_max": 1.0, "clip": True}
METHODS = {
    "linear": {"method": "linear", "bands": BOTH, "in_min": 0.0, "in_max": 0.5, "out_min": 0.0, "out_max": 255.0, "clip": True},
    "percentile": {
        "method": "percentile",
        "bands": BOTH,
        "low": 2,
        "high": 98,
        **_TARGET,
        "measured": {"factor": 1, "bands": {"red": {"p_low": 0.12, "p_high": 0.3}, "nir": {"p_low": 0.35, "p_high": 0.5}}},
    },
    "zscore": {
        "method": "zscore",
        "bands": BOTH,
        "measured": {"factor": 1, "bands": {"red": {"mean": 0.2, "stddev": 0.05}, "nir": {"mean": 0.4, "stddev": 0.08}}},
    },
    "robust": {
        "method": "robust",
        "bands": BOTH,
        "measured": {
            "factor": 2,
            "bands": {"red": {"p25": 0.15, "median": 0.2, "p75": 0.25}, "nir": {"p25": 0.35, "median": 0.4, "p75": 0.46}},
        },
    },
}


@pytest.fixture(scope="module")
def files(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    root = tmp_path_factory.mktemp("normalize-methods-bands")
    return {
        "red": sources.build_band_cog(root / "red.tif", sources.ramp(WIDTH, HEIGHT, 1200)),
        "nir": sources.build_band_cog(root / "nir.tif", sources.ramp(WIDTH, HEIGHT, 3400)),
        "scl": sources.build_band_cog(
            root / "scl.tif", scl_layer(WIDTH // 2, HEIGHT // 2), scale=None, offset=None, resolution=20.0
        ),
    }


@pytest.fixture
def client(files: dict[str, Path], monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    sources.serve({sources.url(name): path for name, path in files.items()}, monkeypatch)
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


def _url(
    tile: tuple[int, int, int],
    steps: Sequence[tuple[str, int, dict | str]],
    *,
    dataset: str = COG,
    assets: Sequence[str] = ("red", "nir"),
    size: int | None = None,
) -> str:
    z, x, y = tile
    query = [f"asset={quote(a)}" for a in assets]
    for op, version, params in steps:
        raw = params if isinstance(params, str) else json.dumps(params)
        query += [f"op={op}", f"op_version={version}", f"params={quote(raw)}"]
    if size is not None:
        query.append(f"tilesize={size}")
    return f"/collections/{dataset}/items/{ITEM}/tiles/WebMercatorQuad/{z}/{x}/{y}.tif?{'&'.join(query)}"


def _decode(content: bytes) -> numpy.ma.MaskedArray:
    """All bands of a tile's GeoTIFF, masked where its last band (the alpha, not positive where invalid) says so."""
    with MemoryFile(content) as memory, memory.open() as dataset:
        data, alpha = dataset.read()[:-1], dataset.read(dataset.count)
    return numpy.ma.masked_array(data, mask=numpy.broadcast_to(alpha <= 0, data.shape))


def _job_bands(result_path: Path, tile: tuple[int, int, int], size: int = 256) -> numpy.ma.MaskedArray:
    z, x, y = tile
    with Reader(str(result_path)) as reader:
        return reader.tile(x, y, z, resampling_method="nearest", tilesize=size).array


def _recipe(assets: Sequence[str], steps: Sequence[dict], bands: Sequence[str]) -> dict:
    entries = []
    for asset in assets:
        if asset == "scl":
            entry = resolved(ITEM, asset, href=sources.url(asset), scale=None, offset=None)
            entry["bands"] = [{"data_type": "uint8", "nodata": 0, "scale": None, "offset": None}]
        else:
            entry = resolved(ITEM, asset, href=sources.url(asset), scale=sources.SCALE, offset=sources.OFFSET)
        entries.append(entry)
    return {
        "recipe_version": 2,
        "inputs": [
            {"name": "s2", "dataset": "synthetic", "groups": [[ITEM]], "assets": list(assets), "resolved": entries}
        ],
        "aoi": sources.whole(WIDTH, HEIGHT, inset=0.0),
        "steps": list(steps),
        "output": {"kind": "raster", "format": "cog", "dtype": "float32", "bands": list(bands)},
    }


def _compare(client: TestClient, result_path: Path, tile_steps, assets, size: int) -> tuple[int, int]:
    compared = masked = 0
    for tile in _tiles(NATIVE[size]):
        response = client.get(_url(tile, tile_steps, assets=assets, size=size))
        assert response.status_code == 200, response.text
        from_tile, from_job = _decode(response.content), _job_bands(result_path, tile, size)
        assert from_tile.shape == from_job.shape, tile
        assert numpy.array_equal(from_tile.mask, numpy.ma.getmaskarray(from_job)), tile
        valid = ~from_tile.mask
        assert numpy.array_equal(from_tile.data[valid], from_job.data[valid]), tile
        compared += int(valid.sum())
        masked += int(from_tile.mask.sum())
    return compared, masked


class TestTheTileEqualsTheJobOnTheNativeLevel:
    @pytest.mark.parametrize("size", NATIVE)
    @pytest.mark.parametrize("method", list(METHODS))
    def test_each_method_gives_the_bytes_of_the_job(
        self, client: TestClient, tmp_path: Path, method: str, size: int
    ) -> None:
        step = {"op": "normalize", "op_version": 3, "params": METHODS[method]}
        result = run(
            recipe_of_data(_recipe(BOTH, [step], BOTH), OPERATORS), workdir=tmp_path, progress=lambda d, t: None
        )
        compared, masked = _compare(client, result.path, [("normalize", 3, METHODS[method])], BOTH, size)
        assert compared > 10_000

    @pytest.mark.parametrize("size", NATIVE)
    def test_a_mask_before_the_method_reaches_its_values(self, client: TestClient, tmp_path: Path, size: int) -> None:
        """The tile's ``mask`` (version 1) drops the layer; the job's (version 2) keeps it unless the output leaves it out."""
        steps = [
            {"op": "mask", "op_version": 2, "params": MASK},
            {"op": "normalize", "op_version": 3, "params": METHODS["percentile"]},
        ]
        assets = ("red", "nir", "scl")
        result = run(
            recipe_of_data(_recipe(assets, steps, BOTH), OPERATORS), workdir=tmp_path, progress=lambda d, t: None
        )
        compared, masked = _compare(
            client, result.path, [("mask", 1, MASK), ("normalize", 3, METHODS["percentile"])], assets, size
        )
        assert compared > 10_000 and masked > 0

    def test_only_the_named_bands_are_converted_and_the_others_come_as_they_are(
        self, client: TestClient, files: dict[str, Path]
    ) -> None:
        tile = _tiles()[1]
        red_only = {
            **METHODS["zscore"],
            "bands": ["red"],
            "measured": {"factor": 1, "bands": {"red": METHODS["zscore"]["measured"]["bands"]["red"]}},
        }
        both = _decode(client.get(_url(tile, [("normalize", 3, METHODS["zscore"])])).content)
        red = _decode(client.get(_url(tile, [("normalize", 3, red_only)])).content)
        assert both.shape == red.shape and both.shape[0] == 2
        valid = ~red.mask[0]
        assert valid.sum() > 5_000
        # The converted band is the same either way; the other is the physical band when nobody converts it.
        assert numpy.array_equal(both.data[0][valid], red.data[0][valid])
        raw = _job_bands(files["nir"], tile).data[0].astype("float64")
        numpy.testing.assert_allclose(
            red.data[1][valid], (raw * sources.SCALE + sources.OFFSET)[valid], rtol=1e-6, atol=1e-7
        )
        assert not numpy.array_equal(both.data[1][valid], red.data[1][valid])


class TestRefusals:
    @pytest.mark.parametrize(
        ("name", "params"),
        [
            ("an unknown method", {**METHODS["linear"], "method": "minmax"}),
            ("the numbers of another method", {**METHODS["zscore"], "measured": METHODS["percentile"]["measured"]}),
            ("a field of another method", {**METHODS["zscore"], "clip": True}),
            ("no numbers", {"method": "zscore", "bands": BOTH}),
            ("a negative deviation", {**METHODS["zscore"], "measured": {"factor": 1, "bands": {
                "red": {"mean": 0.2, "stddev": -1.0}, "nir": {"mean": 0.4, "stddev": 0.08}}}}),
            ("not json", "not json"),
        ],
    )
    def test_malformed_parameters_are_a_400_and_never_a_500(self, client: TestClient, name: str, params) -> None:
        response = client.get(_url(_tiles()[0], [("normalize", 3, params)]))
        assert response.status_code == 400 and response.json()["detail"].startswith("params: "), name

    def test_a_band_the_stock_does_not_have_is_a_422_naming_the_bands(self, client: TestClient) -> None:
        params = {**METHODS["linear"], "bands": ["red", "swir"]}
        response = client.get(_url(_tiles()[0], [("normalize", 3, params)]))
        assert response.status_code == 422
        assert "unknown band(s): swir" in response.json()["detail"] and "red" in response.json()["detail"]

    def test_a_dataset_that_has_not_switched_normalization_on_is_a_422(self, client: TestClient) -> None:
        response = client.get(_url(_tiles()[0], [("normalize", 3, METHODS["linear"])], dataset=NO_NORMALIZE.dataset_id))
        assert response.status_code == 422 and "normalization" in response.json()["detail"]

    def test_the_refusals_cost_no_request_to_the_source(self, client: TestClient) -> None:
        fetched: list[str] = []
        original = client.app.state.earthx_item_source

        async def counting(dataset_id: str, item_id: str) -> dict[str, Any]:
            fetched.append(item_id)
            return await original(dataset_id, item_id)

        client.app.state.earthx_item_source = counting
        client.get(_url((14, 1, 1), [("normalize", 3, {**METHODS["zscore"], "clip": True})]))
        client.get(_url((14, 1, 1), [("normalize", 3, METHODS["linear"])], dataset=NO_NORMALIZE.dataset_id))
        assert fetched == []

    def test_the_numbers_of_many_bands_may_outgrow_the_length_of_a_tile_url_and_say_so(self, client: TestClient) -> None:
        names = [f"band{i:03d}" for i in range(40)]
        params = {
            "method": "zscore",
            "bands": names,
            "measured": {"factor": 1, "bands": {name: {"mean": 0.123456789, "stddev": 0.0123456789} for name in names}},
        }
        assert len(json.dumps(params)) > MAX_OPERATOR_PARAMS_CHARS
        response = client.get(_url((14, 1, 1), [("normalize", 3, params)]))
        assert response.status_code == 400 and f"at most {MAX_OPERATOR_PARAMS_CHARS} characters" in response.json()["detail"]
