#!/usr/bin/env python3
"""How many pixels of a native-level tile agree for a scene off the mosaic grid (NM4-04 §7.4).

    python -W ignore scripts/tile-bench/off_grid_identity.py

A scene of 3000 x 3000 pixels in EPSG:32633 from easting 300 000 (the west edge of the zone, where it overlaps zone
32), with a value of its own in every pixel (a ``uint32`` ramp). Two ways onto the same WebMercator tile:

* the tile path: the scene read with ``nearest`` straight onto the tile;
* the job, compared as in ``adr/0014`` §6.4: a ``WarpedVRT`` with ``nearest`` and ``tolerance`` 0.125 onto a 10 m grid
  in EPSG:32632 (the mosaic grid), then read with ``nearest`` onto the tile.

Over 9 tiles around the centre on z13 and z14 it counts equal values among the pixels valid in both, and the largest
distance in source pixels between the two values (row and column are read back from the value).
"""

import tempfile
from pathlib import Path

import morecantile
import numpy
import rasterio
from rasterio.enums import Resampling
from rasterio.transform import from_origin
from rasterio.vrt import WarpedVRT
from rio_cogeo.cogeo import cog_translate
from rio_cogeo.profiles import cog_profiles
from rio_tiler.io import Reader

ROOT = Path(tempfile.mkdtemp())
TMS = morecantile.tms.get("WebMercatorQuad")
SIDE = 3000


def cog(path: Path, data: numpy.ndarray, crs: str, transform) -> Path:
    plain = path.with_suffix(".plain.tif")
    profile = {
        "driver": "GTiff", "dtype": "uint32", "count": 1, "height": data.shape[0], "width": data.shape[1],
        "crs": crs, "transform": transform, "nodata": 0,
    }  # fmt: skip
    with rasterio.open(plain, "w", **profile) as dst:
        dst.write(data, 1)
    cog_profile = cog_profiles.get("deflate")
    cog_profile.update(blockxsize=512, blockysize=512)
    cog_translate(plain, path, cog_profile, overview_resampling="nearest", quiet=True)
    plain.unlink()
    return path


def main() -> None:
    ramp = numpy.arange(SIDE * SIDE, dtype="uint32").reshape(SIDE, SIDE) + 1
    scene = cog(ROOT / "zone33.tif", ramp, "EPSG:32633", from_origin(300000, 5300000, 10, 10))
    with rasterio.open(scene) as dataset:
        with WarpedVRT(dataset, crs="EPSG:32632", resampling=Resampling.nearest, tolerance=0.125) as vrt:
            left, top = numpy.floor(vrt.transform.c / 10) * 10, numpy.ceil(vrt.transform.f / 10) * 10
            width = int(numpy.ceil((vrt.bounds.right - left) / 10))
            height = int(numpy.ceil((top - vrt.bounds.bottom) / 10))
        grid = from_origin(left, top, 10, 10)
        options = {"crs": "EPSG:32632", "transform": grid, "width": width, "height": height}
        with WarpedVRT(dataset, resampling=Resampling.nearest, tolerance=0.125, **options) as vrt:
            warped = vrt.read(1)
    job = cog(ROOT / "job32.tif", warped, "EPSG:32632", grid)
    with Reader(str(scene)) as reader:
        west, south, east, north = reader.get_geographic_bounds("EPSG:4326")
    for zoom in (13, 14):
        same = total = farthest = 0
        centre = TMS.tile((west + east) / 2, (south + north) / 2, zoom)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                x, y = centre.x + dx, centre.y + dy
                with Reader(str(scene)) as reader:
                    direct = reader.tile(x, y, zoom, resampling_method="nearest").array
                with Reader(str(job)) as reader:
                    twice = reader.tile(x, y, zoom, resampling_method="nearest").array
                valid = ~direct.mask[0] & ~twice.mask[0]
                a = direct.data[0][valid].astype("int64") - 1
                b = twice.data[0][valid].astype("int64") - 1
                same += int((a == b).sum())
                total += int(valid.sum())
                farthest = max(farthest, int(numpy.maximum(abs(a // SIDE - b // SIDE), abs(a % SIDE - b % SIDE)).max()))
        print(f"z{zoom}: {same} of {total} valid pixels identical ({100 * same / total:.1f} %), 9 tiles; "
              f"largest offset {farthest} source pixel(s)")


if __name__ == "__main__":
    main()
