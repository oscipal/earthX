"""A synthetic Copernicus DEM tile: one float32 band, no nodata, EPSG:4326
(M3-11b, `docs/plans/m3-11b-dem-adapter.md` §5).

Unlike `mini_cog.py` (three uint8 bands with a nodata value, matching
Sentinel-2's `visual` asset), the real DEM is one continuous float32 elevation
band that never masks a pixel out (measured, plan §2.3). A synthetic asset
that kept `mini_cog`'s shape would let the DEM registry entry's single-asset
colormap render (`default_render.assets=("data",)`, `colormap_name="terrain"`)
pass by accident — a colormap applies to one band, not three.

Placed in geographic coordinates directly, like every real DEM tile
(`adr/0009` §3.1), rather than the UTM ground `mini_cog`/`mini_zarr` share:
the tile and download routes read the file's own CRS and transform regardless
of what an item claims (`readers/cog.py`), so nothing is lost by placing this
one differently. :data:`BOUNDS` is exactly the *nominal* cell of
:data:`TILE_NAME` (west/south/east/north on whole degrees) — the same shape
`adapters.cop_dem_bucket` builds an item's geometry from (M3-11b F3) — so
`tests.catalog.synthetic_chain` can hand-build a DEM item without reaching
into that module's own internals.
"""

from __future__ import annotations

from pathlib import Path

import numpy
import pytest
import rasterio
from rasterio.transform import from_origin
from rio_cogeo.cogeo import cog_translate
from rio_cogeo.profiles import cog_profiles

from tests.earthx.readers.mini_zarr import HOST

#: Same host the other two synthetic stores serve on — one asset_hosts entry
#: covers all three formats in `synthetic_chain`.
ASSET_PATH = "/products/mini_dem.tif"
ASSET_URL = f"https://{HOST}{ASSET_PATH}"

#: The tile name this store stands in for, and its nominal 1x1-degree cell
#: (west, south, east, north) — matching `adapters.cop_dem_bucket`'s own
#: name-to-bbox math for `Copernicus_DSM_COG_10_N51_00_E010_00_DEM`.
TILE_NAME = "Copernicus_DSM_COG_10_N51_00_E010_00_DEM"
BOUNDS = (10.0, 51.0, 11.0, 52.0)

#: One degree split into this many pixels. Small enough the write and read
#: stay cheap; the real tile is 3600 px per side (measured, plan §2.3).
SIZE = 72
RESOLUTION_DEG = (BOUNDS[2] - BOUNDS[0]) / SIZE
CRS = "EPSG:4326"

#: Comfortably inside the registry entry's own `default_render.rescale`
#: (0..5000 m) without touching either edge.
MIN_ELEVATION, MAX_ELEVATION = 100.0, 800.0

#: Small enough that a 72x72 raster still has more than one tile per level.
BLOCKSIZE = 16


def build_mini_dem(path: Path) -> Path:
    """Write a tiled, overviewed, single-band float32 COG and return it."""
    generator = numpy.random.default_rng(seed=20260926)
    data = generator.uniform(MIN_ELEVATION, MAX_ELEVATION, (1, SIZE, SIZE)).astype("float32")

    profile = {
        "driver": "GTiff",
        "dtype": "float32",
        "count": 1,
        "height": SIZE,
        "width": SIZE,
        "crs": CRS,
        "transform": from_origin(BOUNDS[0], BOUNDS[3], RESOLUTION_DEG, RESOLUTION_DEG),
        # No nodata: the real bucket's DEM COGs carry none either (measured,
        # plan §2.3) — oceans and gaps are simply absent tiles, not a masked
        # value inside a present one.
    }
    plain = path.with_suffix(".plain.tif")
    with rasterio.open(plain, "w", **profile) as destination:
        destination.write(data)
        destination.update_tags(AREA_OR_POINT="Point")

    cog_profile = cog_profiles.get("deflate")
    cog_profile.update({"blockxsize": BLOCKSIZE, "blockysize": BLOCKSIZE})
    cog_translate(plain, path, cog_profile, overview_resampling="nearest", quiet=True)
    plain.unlink()
    return path


def serve_dem(local: Path, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Same seam as `mini_cog.serve_cog` — see there for why it looks like this."""
    cleared: list[str] = []

    def vsicurl_path(checked: object) -> str:
        cleared.append(getattr(checked, "url", str(checked)))
        return str(local)

    monkeypatch.setattr("earthx.readers.cog.vsicurl_path", vsicurl_path)
    return cleared
