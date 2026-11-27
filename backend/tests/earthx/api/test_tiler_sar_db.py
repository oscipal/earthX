"""The tile of ``sar_db`` (DS-05a): through the tile route of the real app, bit-identical to the job on the native level.

A synthetic band of digital numbers (``uint16``, 0 as nodata, 10 m in UTM 32N) on a dataset that switches
``sar_backscatter`` on, served through the real `readers`; the job runs the same step through ``processing.run``, and its
result is read onto the same tile with ``nearest`` (adr/0014 §6.3, row 2).
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
from rio_tiler.io import Reader

from earthx.api.tiler import build_app
from earthx.catalog.registry import DatasetRegistry
from earthx.processing import run
from earthx.processing.operators import REGISTRY as OPERATORS
from tests.catalog.entries import SENTINEL_2_L2A
from tests.earthx.processing import sources
from tests.earthx.processing.recipes import recipe_of_data
from tests.earthx.processing.test_sar_db import HEIGHT, VV, WIDTH, _numbers, _recipe
from tests.earthx.readers import mini_zarr

ITEM = "ITEM_A"
RADAR = replace(
    SENTINEL_2_L2A,
    dataset_id="synthetic-radar",
    source=replace(SENTINEL_2_L2A.source, asset_hosts=(sources.HOST,)),
    capabilities=replace(SENTINEL_2_L2A.capabilities, sar_backscatter=True),
    band_units={**SENTINEL_2_L2A.band_units, "vv": "DN"},
    band_descriptions={**SENTINEL_2_L2A.band_descriptions, "vv": "VV polarisation amplitude"},
    sar_quantity={"vv": "amplitude"},
)
OPTICAL = replace(RADAR, dataset_id="synthetic-optical", capabilities=SENTINEL_2_L2A.capabilities, sar_quantity={})
ITEM_JSON = {
    "id": ITEM,
    "type": "Feature",
    "properties": {"proj:code": sources.CRS, "datetime": "2026-01-02T10:00:00Z"},
    "assets": {"vv": {"href": sources.url("vv"), "raster:bands": [{"data_type": "uint16", "nodata": 0, "unit": "DN"}]}},
}


@pytest.fixture(scope="module")
def scene(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return sources.build_band_cog(tmp_path_factory.mktemp("radar") / "vv.tif", _numbers(), scale=None, offset=None, nodata=0)


@pytest.fixture
def client(scene: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    sources.serve({sources.url("vv"): scene}, monkeypatch)

    async def item_source(dataset_id: str, item_id: str) -> dict[str, Any]:
        return ITEM_JSON

    @asynccontextmanager
    async def lifespan(app):
        app.state.earthx_item_source = item_source
        yield

    app = build_app(DatasetRegistry((RADAR, OPTICAL)), lifespan=lifespan)
    app.state.earthx_resolver = mini_zarr.from_memory
    with TestClient(app) as test_client:
        yield test_client


def _native_tile() -> tuple[int, int, int]:
    """A tile of z14 (about 9.5 m a pixel here, the native 10 m) in the middle of the scene."""
    west, south, east, north = transform_bounds(
        sources.CRS,
        WGS84_CRS,
        sources.ORIGIN_X,
        sources.ORIGIN_Y - HEIGHT * sources.RESOLUTION,
        sources.ORIGIN_X + WIDTH * sources.RESOLUTION,
        sources.ORIGIN_Y,
    )
    tile = WEB_MERCATOR_TMS.tile((west + east) / 2, (south + north) / 2, 14)
    return tile.z, tile.x, tile.y


def _url(params: dict, dataset: str = RADAR.dataset_id, route: str = "tiles") -> str:
    z, x, y = _native_tile()
    query = f"asset=vv&op=sar_db&op_version=1&params={quote(json.dumps(params))}&band={params['name']}"
    if route == "statistics":
        return f"/collections/{dataset}/items/{ITEM}/statistics?{query}"
    return f"/collections/{dataset}/items/{ITEM}/tiles/WebMercatorQuad/{z}/{x}/{y}.tif?{query}"


def _decode(content: bytes) -> numpy.ma.MaskedArray:
    with MemoryFile(content) as memory, memory.open() as dataset:
        data, alpha = dataset.read(1), dataset.read(dataset.count)
    return numpy.ma.masked_array(data, mask=alpha <= 0)


def test_the_tile_is_the_job_on_the_native_level_to_the_bit(client: TestClient, tmp_path: Path) -> None:
    response = client.get(_url(VV))
    assert response.status_code == 200, response.text
    from_tile = _decode(response.content)
    step = {"op": "sar_db", "op_version": 1, "params": VV}
    result = run(recipe_of_data(_recipe([step], ["vv_db"]), OPERATORS), workdir=tmp_path, progress=lambda done, total: None)
    z, x, y = _native_tile()
    with Reader(str(result.path)) as reader:
        from_job = reader.tile(x, y, z, resampling_method="nearest").array[0]
    assert numpy.array_equal(from_tile.mask, numpy.ma.getmaskarray(from_job))
    valid = ~from_tile.mask
    assert valid.sum() > 30_000
    assert from_tile.data[valid].tobytes() == from_job.data[valid].tobytes()


def test_the_statistics_of_the_tile_are_in_db(client: TestClient) -> None:
    response = client.get(_url(VV, route="statistics"))
    assert response.status_code == 200, response.text
    (band,) = response.json().values()
    assert 0 <= band["min"] < band["max"] < 96.33  # 20·log10(65535) = 96.3294…


def test_a_dataset_without_the_capability_is_a_422(client: TestClient) -> None:
    response = client.get(_url(VV, dataset=OPTICAL.dataset_id))
    assert response.status_code == 422
    assert "does not allow sar_backscatter" in response.json()["detail"]


def test_a_quantity_other_than_the_registrys_is_a_422(client: TestClient) -> None:
    response = client.get(_url({**VV, "quantity": "intensity"}))
    assert response.status_code == 422
    assert "is an amplitude, not an intensity" in response.json()["detail"]
