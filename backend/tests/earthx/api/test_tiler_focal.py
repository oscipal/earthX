"""The tile of a ``focal`` step (M5-10 part B, adr/0030 F3, plan F4): read ``bilinear`` with its halo, the first step only.

``terrain`` on a synthetic model of heights in metres, through the tile route of the real app and the real `readers`.
The expected tile is the kernel on what rio-tiler reads for the same tile with the same halo and resampling.
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
from earthx.processing.operators import TERRAIN, TerrainParams
from tests.catalog.entries import SENTINEL_2_L2A
from tests.earthx.processing import sources
from tests.earthx.readers import mini_zarr

WIDTH, HEIGHT = 400, 360
ITEM = "ITEM_DEM"
DEM = "synthetic-dem"
NODATA = -9999.0
SLOPE = {"product": "slope", "bands": ["dem"], "name": "slope", "slope_unit": "degrees"}
DOUBLE = {"expression": "dem", "name": "copy"}

DEM_DATASET = replace(
    SENTINEL_2_L2A,
    dataset_id=DEM,
    source=replace(SENTINEL_2_L2A.source, asset_hosts=(sources.HOST,)),
    capabilities=replace(SENTINEL_2_L2A.capabilities, terrain=True),
)
NO_TERRAIN = replace(DEM_DATASET, dataset_id="synthetic-dem-no-terrain", capabilities=SENTINEL_2_L2A.capabilities)
REGISTRY = DatasetRegistry((DEM_DATASET, NO_TERRAIN))

ITEM_JSON = {
    "id": ITEM,
    "type": "Feature",
    "properties": {"proj:code": sources.CRS, "datetime": "2026-01-02T10:00:00Z"},
    "assets": {
        "dem": {
            "href": sources.url("dem"),
            "raster:bands": [{"data_type": "float32", "nodata": NODATA, "unit": "m"}],
        }
    },
}


def _heights() -> numpy.ndarray:
    rows, cols = numpy.indices((HEIGHT, WIDTH), dtype="float64")
    return (900 + 60 * numpy.sin(cols / 13) * numpy.cos(rows / 17) + 0.5 * cols).astype("float32")


@pytest.fixture(scope="module")
def dem(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("focal-dem") / "dem.tif"
    return sources.build_band_cog(path, _heights(), scale=None, offset=None, nodata=NODATA)


@pytest.fixture
def client(dem: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    sources.serve({sources.url("dem"): dem}, monkeypatch)

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


def _inner_tile(zoom: int = 14) -> tuple[int, int, int]:
    """A tile in the middle of the raster, whose halo lies inside it too."""
    west, south, east, north = transform_bounds(
        sources.CRS,
        WGS84_CRS,
        sources.ORIGIN_X,
        sources.ORIGIN_Y - HEIGHT * sources.RESOLUTION,
        sources.ORIGIN_X + WIDTH * sources.RESOLUTION,
        sources.ORIGIN_Y,
    )
    tile = WEB_MERCATOR_TMS.tile((west + east) / 2, (south + north) / 2, zoom)
    return tile.z, tile.x, tile.y


def _url(tile: tuple[int, int, int], steps: list[tuple[str, int, dict]], extra: str = "", dataset: str = DEM) -> str:
    z, x, y = tile
    parts = ["asset=dem"]
    for op, version, params in steps:
        parts += [f"op={op}", f"op_version={version}", f"params={quote(json.dumps(params))}"]
    return f"/collections/{dataset}/items/{ITEM}/tiles/WebMercatorQuad/{z}/{x}/{y}.tif?{'&'.join(parts)}{extra}"


def _decode(content: bytes) -> numpy.ma.MaskedArray:
    with MemoryFile(content) as memory, memory.open() as dataset:
        data, alpha = dataset.read(1), dataset.read(dataset.count)
    return numpy.ma.masked_array(data, mask=alpha <= 0)


def test_a_terrain_tile_is_the_kernel_on_a_bilinear_read_with_its_halo(client: TestClient, dem: Path) -> None:
    tile = _inner_tile()
    response = client.get(_url(tile, [("terrain", 1, SLOPE)]))
    assert response.status_code == 200, response.text
    got = _decode(response.content)
    assert got.shape == (256, 256)
    with Reader(str(dem)) as reader:
        image = reader.tile(
            tile[1], tile[2], tile[0], buffer=1, resampling_method="bilinear", reproject_method="bilinear"
        )
    image.band_names = ["dem"]
    expected = TERRAIN.run(image, TerrainParams.model_validate(SLOPE)).array[1]
    assert expected.shape == (256, 256)
    numpy.testing.assert_array_equal(numpy.ma.getmaskarray(got), numpy.ma.getmaskarray(expected))
    numpy.testing.assert_allclose(got.compressed(), expected.compressed(), rtol=1e-6)
    assert not numpy.ma.getmaskarray(got).any()  # the halo of an inner tile lies in the data: no ring


def test_the_statistics_of_a_terrain_tile_measure_the_whole_extent(client: TestClient) -> None:
    z, x, y = _inner_tile()
    path = _url((z, x, y), [("terrain", 1, SLOPE)]).split("/tiles/")[0]
    query = _url((z, x, y), [("terrain", 1, SLOPE)]).split("?", 1)[1]
    response = client.get(f"{path}/statistics?{query}")
    assert response.status_code == 200, response.text
    (band,) = response.json().values()
    assert 0 < band["min"] < band["max"] < 90


def test_a_focal_step_after_another_is_a_422(client: TestClient) -> None:
    response = client.get(_url(_inner_tile(), [("band_math", 2, DOUBLE), ("terrain", 1, {**SLOPE, "bands": ["copy"]})]))
    assert response.status_code == 422
    assert response.json()["detail"] == "step 1: 'terrain' runs as a tile only as the first step"


def test_a_pixel_step_after_it_runs(client: TestClient) -> None:
    after = {"expression": "slope * 2", "name": "twice"}
    response = client.get(_url(_inner_tile(), [("terrain", 1, SLOPE), ("band_math", 2, after)]) + "&band=twice")
    assert response.status_code == 200, response.text


@pytest.mark.parametrize(("extra", "reason"), [("&buffer=2", "buffer"), ("&resampling=nearest", "bilinear")])
def test_options_that_would_change_its_neighbours_are_a_400(client: TestClient, extra: str, reason: str) -> None:
    response = client.get(_url(_inner_tile(), [("terrain", 1, SLOPE)], extra))
    assert response.status_code == 400
    assert reason in response.json()["detail"]


def test_bilinear_asked_for_is_what_it_reads_anyway(client: TestClient) -> None:
    response = client.get(_url(_inner_tile(), [("terrain", 1, SLOPE)], "&resampling=bilinear"))
    assert response.status_code == 200, response.text


def test_a_dataset_without_the_capability_is_a_422(client: TestClient) -> None:
    response = client.get(_url(_inner_tile(), [("terrain", 1, SLOPE)], dataset=NO_TERRAIN.dataset_id))
    assert response.status_code == 422
    assert "does not allow terrain" in response.json()["detail"]


def test_the_halo_is_that_of_the_focal_step_after_a_selection_the_planner_puts_first() -> None:
    from earthx.processing.operators import REGISTRY as OPERATORS
    from earthx.processing.tile import halo_of

    select = OPERATORS.operator("band_math", 2)
    params = TerrainParams.model_validate(SLOPE)
    assert halo_of([(TERRAIN, params)]) == 1
    assert halo_of([(select, None), (TERRAIN, params), (select, None)]) == 1
    assert halo_of([(select, None)]) == 0
