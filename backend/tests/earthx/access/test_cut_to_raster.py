"""A scene read past its edge with a halo gives only its own pixels (M5-10 part B, adr/0030 F3).

GDAL's bilinear reads past the edge of a file with the edge's value: past the data it would invent a neighbour the job does
not have. Near a seam each scene still interpolates without the other's pixels, a limit of reading scene by scene.
"""

from __future__ import annotations

from pathlib import Path

import morecantile
import numpy
import pytest
import rasterio
from pyproj import Transformer
from rasterio.transform import from_origin
from rio_tiler.io import Reader
from rio_tiler.mosaic import mosaic_reader
from rio_tiler.mosaic.methods.defaults import FirstMethod

from earthx.access.footprint_mask import cut_to_raster

TMS = morecantile.tms.get("WebMercatorQuad")
OPTIONS = {"buffer": 1, "resampling_method": "bilinear", "reproject_method": "bilinear"}


def _write(path: Path, heights: numpy.ndarray, left: float) -> str:
    profile = {"driver": "GTiff", "dtype": "float32", "count": 1, "crs": "EPSG:2056", "nodata": -9999.0}
    with rasterio.open(
        path,
        "w",
        height=heights.shape[0],
        width=heights.shape[1],
        transform=from_origin(left, 1200000, 2, 2),
        **profile,
    ) as dataset:
        dataset.write(heights, 1)
    return str(path)


@pytest.fixture(scope="module")
def files(tmp_path_factory: pytest.TempPathFactory) -> tuple[str, str, str, morecantile.Tile]:
    root = tmp_path_factory.mktemp("seam")
    rows, cols = numpy.indices((400, 800))
    heights = (900 + 60 * numpy.sin(cols / 13) * numpy.cos(rows / 17) + 0.5 * cols).astype("float32")
    whole = _write(root / "whole.tif", heights, 2600000)
    west = _write(root / "west.tif", heights[:, :400], 2600000)
    east = _write(root / "east.tif", heights[:, 400:], 2600800)
    lon, lat = Transformer.from_crs(2056, 4326, always_xy=True).transform(2600800, 1199600)
    return whole, west, east, TMS.tile(lon, lat, 17)


def _mosaic(paths: list[str], tile: morecantile.Tile, cut: bool) -> numpy.ndarray:
    def read(path: str, x: int, y: int, z: int, **options):
        with Reader(path) as reader:
            image = reader.tile(x, y, z, **options)
            return cut_to_raster(image, reader.crs, reader.bounds) if cut else image

    image, _ = mosaic_reader(paths, read, tile.x, tile.y, tile.z, pixel_selection=FirstMethod(), **OPTIONS)
    return image.array[0].filled(numpy.nan)


def test_away_from_the_seam_the_cut_scenes_are_one_file(files) -> None:
    whole, west, east, tile = files
    with Reader(whole) as reader:
        expected = reader.tile(tile.x, tile.y, tile.z, **OPTIONS).array[0].filled(numpy.nan)
    got = _mosaic([west, east], tile, cut=True)
    assert not numpy.isnan(got).any()  # the next scene fills what the first leaves
    # Within two pixels of the seam each scene interpolates without the other's pixels (plan M5-10 §11.6); nowhere else.
    columns = numpy.unique(numpy.argwhere(numpy.abs(got - expected) > 1e-3)[:, 1])
    assert columns.size <= 2 and (numpy.diff(columns) <= 1).all()


def test_past_the_edge_of_the_data_nothing_is_invented(files) -> None:
    _, west, _, tile = files
    with Reader(west) as reader:
        image = cut_to_raster(reader.tile(tile.x, tile.y, tile.z, **OPTIONS), reader.crs, reader.bounds)
        bounds = reader.bounds
    columns = (
        numpy.linspace(image.bounds[0], image.bounds[2], image.width, endpoint=False)
        + (image.bounds[2] - image.bounds[0]) / image.width / 2
    )
    east_edge = Transformer.from_crs(2056, 3857, always_xy=True).transform(bounds[2], 1199600)[0]
    assert numpy.ma.getmaskarray(image.array)[0][:, columns > east_edge].all()
