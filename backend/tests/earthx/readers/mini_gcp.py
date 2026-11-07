"""A synthetic COG placed by ground control points only, like a Sentinel-1 GRD file (adr/0018 §3.1, DS-04a).

Written by this module, no binary in the repository (ENTSCHEIDUNGEN §4). Three things are deliberate:

* **no CRS and no geotransform, only GCPs**, the shape GDAL reports for an Earth Search GRD asset;
* **a position that is not affine**: the GCPs follow a grid with a sinusoidal bend of several pixels, so an affine fit
  through them (rio-tiler's own way) misses, while a thin-plate spline goes through every one;
* **every pixel its own value** (``row * SIZE + col + 1`` as ``uint16``, 0 is nodata), so a test can tell from a value
  read anywhere which source pixel it came from.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy
import rasterio
from rasterio.control import GroundControlPoint
from rasterio.crs import CRS

#: Pixels per side; small, and ``SIZE * SIZE`` stays below the ``uint16`` range.
SIZE = 96

#: Reserved for "no data here", never a pixel value.
NODATA = 0

#: Where the image lies and how large a pixel is on the ground, about 10 m in the Alps.
ORIGIN_LON = 10.0
ORIGIN_LAT = 47.0
STEP_LON = 0.00013
STEP_LAT = 0.00009

#: The bend of the position across the image, in pixels; well above what an affine fit can absorb.
BEND_PIXELS = 12.0

#: Distance between two GCPs, in pixels; the corners are GCPs as well.
GCP_SPACING = 16

GCP_CRS = CRS.from_epsg(4326)


def position(row: float, col: float) -> tuple[float, float]:
    """Longitude and latitude of the pixel position ``row``, ``col``: a grid with a bend, not an affine map."""
    bend = BEND_PIXELS * math.sin(math.pi * row / SIZE) * math.sin(math.pi * col / SIZE)
    lon = ORIGIN_LON + (col + bend) * STEP_LON
    lat = ORIGIN_LAT - (row + 0.5 * bend) * STEP_LAT
    return lon, lat


def gcps() -> list[GroundControlPoint]:
    """GCPs at pixel centres on a regular grid, each at its exact :func:`position`."""
    last = SIZE - 1
    grid = [(row, col) for row in range(0, SIZE, GCP_SPACING) for col in range(0, SIZE, GCP_SPACING)]
    places = grid + [(0, last), (last, 0), (last, last)]
    points = []
    for row, col in places:
        lon, lat = position(row + 0.5, col + 0.5)
        points.append(GroundControlPoint(row=row + 0.5, col=col + 0.5, x=lon, y=lat, z=0.0))
    return points


def source_pixel(value: int) -> tuple[int, int]:
    """Row and column of the source pixel that carries ``value``."""
    return divmod(int(value) - 1, SIZE)


def build_mini_gcp(path: Path) -> Path:
    """Write the tiled, overviewed GCP file to ``path`` and return it."""
    data = (numpy.arange(SIZE * SIZE, dtype="uint16") + 1).reshape(1, SIZE, SIZE)
    profile = {
        "driver": "GTiff",
        "dtype": "uint16",
        "count": 1,
        "height": SIZE,
        "width": SIZE,
        "nodata": NODATA,
        "tiled": True,
        "blockxsize": 32,
        "blockysize": 32,
    }
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(data)
        dst.gcps = (gcps(), GCP_CRS)
        dst.build_overviews([2, 4], rasterio.enums.Resampling.nearest)
    return path
