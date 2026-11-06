"""A synthetic ESA WorldCover tile: one uint8 band of class codes, nodata 0, EPSG:4326 (M5-07).

Shaped like the real map files (measured, M5-07 plan §2): class values of the legend, nodata 0, a colour table in the
file, geographic coordinates on the nominal 3° cell of :data:`TILE`. Far smaller than the real 36 000² pixels, so that
the write and the reads stay cheap.
"""

from __future__ import annotations

from pathlib import Path

import numpy
import pytest
import rasterio
from rasterio.transform import from_origin
from rio_cogeo.cogeo import cog_translate
from rio_cogeo.profiles import cog_profiles

#: The tile this store stands in for and its nominal cell (west, south, east, north).
TILE = "N45E009"
BOUNDS = (9.0, 45.0, 12.0, 48.0)

#: The eleven classes of the legend; 0 is no data.
CLASSES = (10, 20, 30, 40, 50, 60, 70, 80, 90, 95, 100)

SIZE = 72
RESOLUTION_DEG = (BOUNDS[2] - BOUNDS[0]) / SIZE
CRS = "EPSG:4326"
BLOCKSIZE = 16


def build_mini_worldcover(path: Path) -> Path:
    """Write a tiled, overviewed, single-band uint8 COG of class codes with a nodata corner, and return it."""
    generator = numpy.random.default_rng(seed=20261106)
    data = generator.choice(CLASSES, size=(1, SIZE, SIZE)).astype("uint8")
    data[0, :8, :8] = 0
    profile = {
        "driver": "GTiff",
        "dtype": "uint8",
        "count": 1,
        "height": SIZE,
        "width": SIZE,
        "crs": CRS,
        "transform": from_origin(BOUNDS[0], BOUNDS[3], RESOLUTION_DEG, RESOLUTION_DEG),
        "nodata": 0,
    }
    plain = path.with_suffix(".plain.tif")
    with rasterio.open(plain, "w", **profile) as destination:
        destination.write(data)
        destination.write_colormap(1, {0: (0, 0, 0, 0), 10: (0, 100, 0, 255), 50: (250, 0, 0, 255)})
    cog_profile = cog_profiles.get("deflate")
    cog_profile.update({"blockxsize": BLOCKSIZE, "blockysize": BLOCKSIZE})
    cog_translate(plain, path, cog_profile, overview_resampling="nearest", quiet=True)
    plain.unlink()
    return path


def serve_worldcover(local: Path, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Same seam as `mini_dem.serve_dem`."""
    cleared: list[str] = []

    def vsicurl_path(checked: object) -> str:
        cleared.append(getattr(checked, "url", str(checked)))
        return str(local)

    monkeypatch.setattr("earthx.readers.cog.vsicurl_path", vsicurl_path)
    return cleared
