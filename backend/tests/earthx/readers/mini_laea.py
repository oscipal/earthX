"""A synthetic BEV ALS-DGM tile: one float32 band with nodata -9999, in ETRS89-LAEA (EPSG:3035) (M5-09 plan §4.7).

The real tile is a 50 km cell at 1 m (50 001 px a side), LZW, blocks of 512 and overviews (all 55 headers, M5-09 plan
§2.4). This one covers the same cell at 1 km, so writing and reading stay cheap, and keeps what the chain has to deal
with: a projected grid that is neither UTM nor WGS 84, so every crop and every tile of web mercator is a reprojection.
The cell lies inside the extent of the entry, because the materialization refuses a tile outside it; the heights are
random and the file only ever lives in a test's temporary directory.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy
import rasterio
from rasterio.transform import from_origin
from rasterio.warp import transform_bounds
from rio_cogeo.cogeo import cog_translate
from rio_cogeo.profiles import cog_profiles

from tests.earthx.readers.mini_zarr import HOST

CRS = "EPSG:3035"
NORTH, EAST = 2_650_000, 4_800_000
#: The tile as the BEV names it: the lower left corner of the 50 km cell in EPSG:3035.
TILE = f"CRS3035RES50000mN{NORTH}E{EAST}"
DAY = date(2025, 9, 15)
ASSET_URL = f"https://{HOST}/download/ALS/DTM/{DAY.strftime('%Y%m%d')}/ALS_DTM_{TILE}.tif"
#: A made-up DOI in the form the feed carries (M5-09 plan §2.4).
DOI = "10.48677/00000000-0000-4000-8000-000000000000"
#: West, south, east, north in metres of EPSG:3035.
BOUNDS_LAEA = (float(EAST), float(NORTH), EAST + 50_000.0, NORTH + 50_000.0)
#: The same cell in WGS 84.
BOUNDS = transform_bounds(CRS, "EPSG:4326", *BOUNDS_LAEA)
#: Five kilometres in the middle of the cell, in WGS 84: what the chain crops, since the whole cell at the 1 m of the
#: item would be far over the download limit.
AOI_BOUNDS = transform_bounds(CRS, "EPSG:4326", EAST + 22_500.0, NORTH + 22_500.0, EAST + 27_500.0, NORTH + 27_500.0)

SIZE = 50
RESOLUTION_M = (BOUNDS_LAEA[2] - BOUNDS_LAEA[0]) / SIZE
NODATA = -9999.0
MIN_ELEVATION, MAX_ELEVATION = 400.0, 2400.0
BLOCKSIZE = 16


def build_mini_laea(path: Path) -> Path:
    """Write a tiled, overviewed, single-band float32 COG in EPSG:3035, with one corner of nodata, and return it."""
    generator = numpy.random.default_rng(seed=20261116)
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
        "transform": from_origin(BOUNDS_LAEA[0], BOUNDS_LAEA[3], RESOLUTION_M, RESOLUTION_M),
    }
    plain = path.with_suffix(".plain.tif")
    with rasterio.open(plain, "w", **profile) as destination:
        destination.write(data)
    cog_profile = cog_profiles.get("lzw")
    cog_profile.update({"blockxsize": BLOCKSIZE, "blockysize": BLOCKSIZE})
    cog_translate(plain, path, cog_profile, overview_resampling="nearest", quiet=True)
    plain.unlink()
    return path
