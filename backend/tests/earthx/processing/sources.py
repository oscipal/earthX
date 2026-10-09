"""Synthetic inputs for runs of the core, served through the real `readers`.

Single-band ``uint16`` COGs shaped like Sentinel-2's ``B04``/``B08``: ``scale``
and ``offset`` as GDAL tags, ``nodata 0`` with a nodata corner, 10 m in UTM 32N.
The values are a smooth ramp, so an expected result is a formula, not a second
implementation of the core.

:func:`serve` swaps only the last step of the COG path — ``vsicurl_path`` — for a
local file per address, and the resolver for a fixed public answer, the same seams
`mini_cog.serve_cog` and `mini_zarr.serve_store` use: ``check_url``, the allowlist
and ``AssetPath`` all run for real.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy
import pytest
import rasterio
from rasterio.transform import from_origin
from rasterio.warp import transform_geom
from rio_cogeo.cogeo import cog_translate
from rio_cogeo.profiles import cog_profiles

from tests.earthx.readers.mini_zarr import from_memory, serve_store

HOST = "store.example.invalid"
CRS = "EPSG:32632"
ORIGIN_X, ORIGIN_Y = 600000.0, 5700000.0
RESOLUTION = 10.0
SCALE = 0.0001
OFFSET = -0.1
NODATA = 0


def url(name: str) -> str:
    return f"https://{HOST}/products/{name}.tif"


def ramp(width: int, height: int, base: int) -> numpy.ndarray:
    """``uint16`` values ``base + 3·row + col`` (wrapped), with a nodata corner of 8×8."""
    rows, cols = numpy.indices((height, width))
    data = ((base + 3 * rows + cols) % 60000 + 1).astype("uint16")
    data[:8, :8] = NODATA
    return data


def build_band_cog(
    path: Path,
    data: numpy.ndarray,
    *,
    scale: float | None = SCALE,
    offset: float | None = OFFSET,
    resolution: float = RESOLUTION,
    blocksize: int = 256,
    nodata: int | None = NODATA,
) -> Path:
    """One band as a deflate COG with optional ``scale``/``offset`` tags."""
    height, width = data.shape
    profile = {
        "driver": "GTiff",
        "dtype": str(data.dtype),
        "count": 1,
        "height": height,
        "width": width,
        "crs": CRS,
        "transform": from_origin(ORIGIN_X, ORIGIN_Y, resolution, resolution),
        "nodata": nodata,
    }
    plain = path.with_suffix(".plain.tif")
    with rasterio.open(plain, "w", **profile) as destination:
        destination.write(data, 1)
        if scale is not None or offset is not None:
            destination.scales = (1.0 if scale is None else scale,)
            destination.offsets = (0.0 if offset is None else offset,)
    cog_profile = cog_profiles.get("deflate")
    cog_profile.update({"blockxsize": blocksize, "blockysize": blocksize})
    cog_translate(plain, path, cog_profile, overview_resampling="nearest", quiet=True)
    plain.unlink()
    return path


def serve(files: Mapping[str, Path], monkeypatch: pytest.MonkeyPatch, zarr_root: Path | None = None) -> list[str]:
    """Let the readers open ``files`` (address → local COG) and, if given, a Zarr store.

    Returns the addresses that passed ``check_url``, in order.
    """
    cleared: list[str] = []

    def vsicurl_path(checked: object) -> str:
        address = getattr(checked, "url", str(checked))
        cleared.append(address)
        return str(files[address])

    monkeypatch.setattr("earthx.readers.cog.vsicurl_path", vsicurl_path)
    monkeypatch.setattr("earthx.readers.access.resolve_host", from_memory)
    if zarr_root is not None:
        serve_store(zarr_root, monkeypatch)
    return cleared


def aoi_around(left: float, bottom: float, right: float, top: float) -> dict[str, Any]:
    """A rectangle given in UTM, as the EPSG:4326 polygon a recipe carries."""
    ring = [[left, bottom], [right, bottom], [right, top], [left, top], [left, bottom]]
    return transform_geom(CRS, "EPSG:4326", {"type": "Polygon", "coordinates": [ring]})


def whole(width: int, height: int, resolution: float = RESOLUTION, inset: float = 0.25) -> dict[str, Any]:
    """An AOI a quarter pixel inside the raster, so the output is the whole raster."""
    pad = inset * resolution
    return aoi_around(
        ORIGIN_X + pad, ORIGIN_Y - height * resolution + pad, ORIGIN_X + width * resolution - pad, ORIGIN_Y - pad
    )
