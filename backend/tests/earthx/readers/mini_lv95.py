"""A synthetic swissALTI3D tile: one float32 band with nodata -9999, in LV95 (EPSG:2056) (M5-08 plan §4.6 point 9).

The real tile is 1 km at 0.5 m (2000 px a side), LZW, blocks of 128 and overviews (measured, M5-08 plan §13). This one
covers the same kilometre at 20 m, so writing and reading stay cheap, and keeps what the chain has to deal with: a
projected grid that is neither UTM nor WGS 84, so every crop and every tile of web mercator is a reprojection.
"""

from __future__ import annotations

from pathlib import Path

import numpy
import rasterio
from rasterio.transform import from_origin
from rasterio.warp import transform_bounds
from rio_cogeo.cogeo import cog_translate
from rio_cogeo.profiles import cog_profiles

from tests.earthx.readers.mini_zarr import HOST

ASSET_PATH = "/ch.swisstopo.swissalti3d/swissalti3d_2025_2600-1199/swissalti3d_2025_2600-1199_0.5_2056.tif"
ASSET_URL = f"https://{HOST}{ASSET_PATH}"

#: The tile as the id names it: the south-west corner in kilometres of LV95.
TILE = "2600-1199"
CRS = "EPSG:2056"
#: West, south, east, north in LV95 metres.
BOUNDS_LV95 = (2_600_000.0, 1_199_000.0, 2_601_000.0, 1_200_000.0)
#: The same kilometre in WGS 84, as an item's geometry carries it.
BOUNDS = transform_bounds(CRS, "EPSG:4326", *BOUNDS_LV95)

SIZE = 50
RESOLUTION_M = (BOUNDS_LV95[2] - BOUNDS_LV95[0]) / SIZE
NODATA = -9999.0
MIN_ELEVATION, MAX_ELEVATION = 500.0, 900.0
BLOCKSIZE = 16


def build_mini_lv95(path: Path) -> Path:
    """Write a tiled, overviewed, single-band float32 COG in LV95, with one corner of nodata, and return it."""
    generator = numpy.random.default_rng(seed=20261109)
    data = generator.uniform(MIN_ELEVATION, MAX_ELEVATION, (1, SIZE, SIZE)).astype("float32")
    data[0, :5, :5] = NODATA
    profile = {
        "driver": "GTiff",
        "dtype": "float32",
        "count": 1,
        "height": SIZE,
        "width": SIZE,
        "crs": CRS,
        "nodata": NODATA,
        "transform": from_origin(BOUNDS_LV95[0], BOUNDS_LV95[3], RESOLUTION_M, RESOLUTION_M),
    }
    plain = path.with_suffix(".plain.tif")
    with rasterio.open(plain, "w", **profile) as destination:
        destination.write(data)
    cog_profile = cog_profiles.get("lzw")
    cog_profile.update({"blockxsize": BLOCKSIZE, "blockysize": BLOCKSIZE})
    cog_translate(plain, path, cog_profile, overview_resampling="nearest", quiet=True)
    plain.unlink()
    return path
