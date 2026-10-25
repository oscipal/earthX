"""The levels of a job result's TileJSON (UI-01a, Otto 25.10.2026): the picture is there at every zoom.

``result.tif`` has overviews, so a tile far out is a read of the coarsest one, and a tile far in is the file's own
pixels. The TileJSON used to name rio-tiler's levels instead — from the file's coarsest overview to the level nearest
its pixel size — and the map, which keeps to the TileJSON, lost the result when zooming out of that range and showed a
stretched tile when zooming in past it, blurrier than the scene it was made from.
"""

from __future__ import annotations

from pathlib import Path

import numpy
import pytest
import rasterio
from rasterio.io import MemoryFile
from rasterio.transform import from_origin
from rio_cogeo.cogeo import cog_translate
from rio_cogeo.profiles import cog_profiles
from rio_tiler.constants import WEB_MERCATOR_TMS
from rio_tiler.io import Reader

from tests.earthx.processing import sources

from ..objectstore.conftest import store, store_env  # noqa: F401 - fixtures
from .test_result_tiles import Rig, rig, uploaded  # noqa: F401 - fixtures

SIZE = 2048  # 20 km at 10 m: three overviews, so a tile at the coarsest level is a different read than at the finest


@pytest.fixture(scope="module")
def result_file(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("result-zoom")
    plain = root / "plain.tif"
    rows, cols = numpy.indices((SIZE, SIZE))
    with rasterio.open(
        plain,
        "w",
        driver="GTiff",
        width=SIZE,
        height=SIZE,
        count=1,
        dtype="float32",
        crs=sources.CRS,
        transform=from_origin(sources.ORIGIN_X, sources.ORIGIN_Y, sources.RESOLUTION, sources.RESOLUTION),
        nodata=-9999.0,
    ) as destination:
        destination.write(((rows // 8 + cols // 8) % 7 / 3.0 - 1).astype("float32"), 1)
    target = root / "result.tif"
    cog_translate(str(plain), str(target), cog_profiles.get("deflate"), quiet=True)
    return target


@pytest.fixture(scope="module")
def mask_files(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    path = tmp_path_factory.mktemp("result-zoom-mask") / "all.tif"
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=SIZE,
        height=SIZE,
        count=1,
        dtype="uint8",
        crs=sources.CRS,
        transform=from_origin(sources.ORIGIN_X, sources.ORIGIN_Y, sources.RESOLUTION, sources.RESOLUTION),
        tiled=True,
        blockxsize=1024,
        blockysize=1024,
        compress="deflate",
    ) as destination:
        destination.write(numpy.ones((SIZE, SIZE), "uint8"), 1)
    return {"all": path}


def test_rio_tiler_alone_would_name_a_narrow_range(result_file: Path) -> None:
    """The premise: the reader's own levels leave out what the map needs (a 20 km raster: from 8 to 13)."""
    with Reader(str(result_file)) as reader:
        assert reader.minzoom > 0
        assert reader.maxzoom < 19


def test_the_tilejson_names_every_level_from_the_coarsest_overview_to_the_finest_source(
    rig: Rig, uploaded: str  # noqa: F811
) -> None:
    body = rig.client.get(f"/results/{uploaded}/WebMercatorQuad/tilejson.json").json()
    assert (body["minzoom"], body["maxzoom"]) == (0, 19)


@pytest.mark.parametrize("zoom", [0, 3, 6, 9, 12, 14, 16, 19])
def test_a_tile_at_every_level_over_the_result_shows_it(
    rig: Rig, uploaded: str, result_file: Path, zoom: int  # noqa: F811
) -> None:
    with Reader(str(result_file)) as reader:
        west, south, east, north = reader.get_geographic_bounds(WEB_MERCATOR_TMS.rasterio_geographic_crs)
    tile = WEB_MERCATOR_TMS.tile((west + east) / 2, (south + north) / 2, zoom)
    response = rig.client.get(
        f"/results/{uploaded}/tiles/WebMercatorQuad/{tile.z}/{tile.x}/{tile.y}.tif?rescale=-1,1&colormap_name=rdylgn"
    )
    assert response.status_code == 200
    with MemoryFile(response.content) as memory, memory.open() as dataset:
        drawn = dataset.read(dataset.count) > 0
    assert drawn.any(), f"nothing of the result at level {zoom}"

