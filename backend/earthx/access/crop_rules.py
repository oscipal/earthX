"""The rules of the AOI crop that the synchronous download and the export job share (M4-11 F1).

Pure functions and constants only: the output grid (EPSG:4326 at the native
resolution, :func:`native_crop_grid`), the extent (:func:`compute_crop_region`), the
mask (:func:`rasterize_aoi`, :func:`mask_profile`), the COG profile, the size estimate
(:func:`estimate_output_dims`, :func:`bytes_per_pixel`, :class:`PlannedOutput`) and
the names inside the ZIP. `access.download` builds the crop in memory from them;
`processing` computes the same output block by block on disk (``processing.export``)
without loading `access.download` — so the two cannot drift apart, and the child of
a job imports nothing it does not run.

Cut out of `access/download.py` (M4-11a); that module still offers every name here.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy
import rasterio
from rasterio.features import rasterize
from rasterio.transform import from_bounds as transform_from_bounds
from rasterio.warp import calculate_default_transform
from rio_cogeo.profiles import cog_profiles
from rio_tiler.constants import WGS84_CRS
from shapely.errors import ShapelyError
from shapely.geometry import mapping as shapely_mapping
from shapely.geometry import shape as shapely_shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

__all__ = [
    "AOI_FILENAME",
    "BLOCK_SIZE",
    "CITATION_FILENAME",
    "COG_PROFILE",
    "FALLBACK_BYTES_PER_PIXEL",
    "MAX_JOB_BYTES",
    "MAX_OUTPUT_SIDE_PX",
    "NOTICE_FILENAME",
    "RECIPE_FILENAME",
    "RESOLUTION_FACTORS",
    "AoiOutsideItems",
    "PlannedOutput",
    "bytes_per_pixel",
    "compute_crop_region",
    "crop_filename",
    "dtype_bytes",
    "estimate_output_dims",
    "group_dirname",
    "mask_filename",
    "mask_profile",
    "merge_first_valid",
    "native_crop_grid",
    "rasterize_aoi",
]

# Conservative fallback pixel dimension used only when an asset's `gsd` cannot
# be read off any item at all (F1, M2-06/M3-18 §10) — no longer a downscale
# mechanism for the normal case: a native-resolution crop is never clipped to
# this (Otto, 23.09.2026, M3-18 §10).
MAX_OUTPUT_SIDE_PX = 4096


# The only resolution choices the download dialog offers (F10c, M3-18 §10):
# native, and whole-number-coarser multiples of it. Generic factors, not new
# per-asset registry fields — applied to whatever `gsd` each asset already
# reports.
RESOLUTION_FACTORS: tuple[int, ...] = (1, 2, 4, 10)


# Bytes per pixel for one band's GDAL/STAC `data_type` name (adr/0006 §12.3
# names the same set for `raster:bands`). Only the sizes both real sources'
# items are measured to actually use are listed; anything else falls back to
# the conservative worst case below rather than guessing.
BYTES_PER_DTYPE: dict[str, int] = {
    "uint8": 1,
    "int8": 1,
    "byte": 1,
    "uint16": 2,
    "int16": 2,
    "uint32": 4,
    "int32": 4,
    "float32": 4,
    "uint64": 8,
    "int64": 8,
    "float64": 8,
}

# F2 (M3-18, Otto 24.09.2026): the fallback when an asset's band count or dtype
# cannot be read off the item at all — deliberately never smaller than what
# both real sources are measured to declare (Earth Search's `visual`: 3 bands
# x 1 byte; EOPF's Zarr composites: as many bands as the asset key names, dtype
# unknown). 8 bytes/band covers every dtype above; 4 bands is the widest a
# Sentinel-2 asset in the registry names today (adr/0003).
FALLBACK_BYTES_PER_BAND = 8
FALLBACK_BAND_COUNT = 4


# The most raw output one job may write, data and masks (Otto, 08.10.2026, M4-11 F5; for a
# raster job 10.10.2026, M4-12 F7): ten times the synchronous crop's 500 MB. An export counts
# it as `PlannedOutput.total_bytes` counts it, a raster job as its output plus its mask. A
# starting value [A]: at 0.041–0.046 s per MB locally (m3-18 §10.3) 5 GB are about four
# minutes without the network, well inside a job's runtime limit; the work directory needs
# up to about twice this per slot while the result is written. The one place this number
# lives: the cost estimate refuses above it, and the crop route offers a job only below it.
MAX_JOB_BYTES = 5_000_000_000

# Block size of the windowed writes, as in the processing core (adr/0014 §7.2) and the
# windowed crop (M3-18 §10.3).
BLOCK_SIZE = 1024

FALLBACK_BYTES_PER_PIXEL = FALLBACK_BAND_COUNT * FALLBACK_BYTES_PER_BAND


# DEFLATE (M3-22, Otto 26.09.2026, F2): every GeoTIFF reader we could find
# reads it, while ZSTD is an optional libtiff build dependency some current
# installers leave out (plan m3-22 §8). The ZSTD detour of M3-18 (F9) chased a
# corruption that was never in these files: it was a use-after-free in the
# tests' own read path (plan m3-22 §3), and this writer produced no unreadable
# file in 2,800 read-back runs with either codec.
COG_PROFILE = cog_profiles.get("deflate")


NOTICE_FILENAME = "ATTRIBUTION.txt"

# The requested AOI, once per ZIP, as plain GeoJSON — the same geometry the
# caller sent, in WGS84 (Otto, 23.09.2026, M3-18 §3): a consumer of the mask
# files (below) needs the polygon itself to make sense of them without also
# parsing the request that produced the ZIP.
AOI_FILENAME = "aoi.geojson"

# What `api` builds and hands in as bytes (adr/0014 §10): the recipe that describes
# the crop and the dataset's citation. `access` writes them and knows no schema.
RECIPE_FILENAME = "recipe.json"
CITATION_FILENAME = "citation.bib"


class AoiOutsideItems(ValueError):
    """Neither the requested items' own bbox nor their actual data touches the AOI."""



def compute_crop_region(items: Sequence[Mapping[str, Any]], aoi: BaseGeometry) -> BaseGeometry:
    """The AOI intersected with the union of ``items``' own footprints (M3-18 §13).

    This, not the AOI's own bounding box, is what :func:`plan_outputs` sizes
    the request against and what the actual crop is read to (module
    docstring): the same geometry the frontend's group outline already shows
    before a download starts (PR #84, ``groupOutline.ts``) — AOI ∩ union of
    the group's own scene footprints, not the AOI padded out to its own
    corners regardless of what the scenes actually cover.

    Falls back to ``aoi`` unchanged when no item carries a usable
    ``geometry`` at all — a detail this conservative should never block a
    download over; a malformed geometry on one item is skipped rather than
    failing the whole group, the same tolerance
    :func:`filter_items_intersecting_aoi` already has for a malformed ``bbox``.

    Raises :class:`AoiOutsideItems` when the intersection is empty — this
    catches a bbox-based match (``filter_items_intersecting_aoi``) whose real,
    often rotated footprint the AOI does not actually touch, before any asset
    is opened (bug A, Otto's review of PR #86, 23.09.2026).
    """
    footprints = []
    for item in items:
        geometry = item.get("geometry")
        if not geometry:
            continue
        try:
            footprints.append(shapely_shape(geometry))
        except (ShapelyError, ValueError, TypeError, KeyError, AttributeError):
            continue
    if not footprints:
        return aoi
    try:
        region = aoi.intersection(unary_union(footprints))
    except (ShapelyError, ValueError):
        return aoi
    if region.is_empty:
        raise AoiOutsideItems("the AOI does not touch the actual footprint of any given item")
    return region



def dtype_bytes(data_type: Any) -> int:
    """Bytes per pixel for one band's dtype name, or the conservative fallback."""
    if isinstance(data_type, str):
        size = BYTES_PER_DTYPE.get(data_type.lower())
        if size is not None:
            return size
    return FALLBACK_BYTES_PER_BAND


def bytes_per_pixel(data_types: Sequence[Any] | None, asset: str) -> int:
    """Bytes one pixel of ``asset`` costs in the output, summed over its bands (F2, M3-18).

    ``data_types`` are the bands' ``data_type`` values as the item describes them
    (``raster:bands``/``bands``), ``None`` or empty where it describes none. A Zarr
    composite asset key (``SR_10m:b04,b03,b02``, adr/0007 §12.11) names its band count
    in the key itself even where the item carries no band description at all.
    """
    if data_types:
        return sum(dtype_bytes(data_type) for data_type in data_types)
    if ":" in asset:
        variables = [v for v in asset.split(":", 1)[1].split(",") if v]
        if variables:
            return len(variables) * FALLBACK_BYTES_PER_BAND
    return FALLBACK_BYTES_PER_PIXEL


# A degree of latitude is at most ~111,694 m on WGS84 (widest near the poles);
# a degree of longitude is widest at the equator, ~111,320 m. Both are used as
# upper bounds in `estimate_output_dims`, never the true value at the AOI's
# actual latitude, which is not known without opening a reader (F1) — the
# point is that the estimate can only come out too high, never too low.
_DEG_TO_M_LAT = 111_700.0
_DEG_TO_M_LON_AT_EQUATOR = 111_320.0


def estimate_output_dims(
    aoi: BaseGeometry, gsd: float, *, resolution_factor: int = 1
) -> tuple[int, int]:
    """Conservative ``(height, width)`` in pixels for a crop of ``aoi`` at ``gsd`` m/pixel.

    Computed from the AOI geometry alone, before any reader opens a dataset
    (F1, M3-18) — deliberately never smaller than what the reader itself will
    produce for the same request: the AOI's least-poleward latitude sets the
    (largest possible) metres a degree of longitude is worth here, and a
    straddled equator is the largest case of all.

    A download is native resolution unless the caller explicitly chose a
    coarser one (Otto, 23.09.2026, M3-18 §10): there is no clamp to a maximum
    side any more, only ``resolution_factor`` (one of :data:`RESOLUTION_FACTORS`)
    dividing both dimensions down from native.
    """
    minx, miny, maxx, maxy = aoi.bounds
    least_poleward_lat = min(abs(miny), abs(maxy)) if miny * maxy > 0 else 0.0
    lon_m_per_degree = _DEG_TO_M_LON_AT_EQUATOR * math.cos(math.radians(least_poleward_lat))
    width_px = max(1, math.ceil((maxx - minx) * lon_m_per_degree / gsd))
    height_px = max(1, math.ceil((maxy - miny) * _DEG_TO_M_LAT / gsd))
    if resolution_factor != 1:
        width_px = max(1, math.ceil(width_px / resolution_factor))
        height_px = max(1, math.ceil(height_px / resolution_factor))
    return height_px, width_px



@dataclass(frozen=True)
class PlannedOutput:
    """One ZIP member's worst-case cost, computed before any reader opens anything (F1/F2, M3-18)."""

    label: str
    width: int
    height: int
    bytes_per_pixel: int

    @property
    def total_bytes(self) -> int:
        """The data file plus its companion mask file (uint8, 1 byte/pixel, M3-18 §3).

        Every asset now ships with a same-grid mask file (module docstring),
        so the estimate the size cap checks has to count it too — a single-band
        uint8 asset would otherwise have its real ZIP contribution understated
        by up to a factor of two.
        """
        return self.width * self.height * (self.bytes_per_pixel + 1)



def native_crop_grid(
    dataset: rasterio.DatasetReader, region: BaseGeometry, *, dst_crs: rasterio.crs.CRS = WGS84_CRS
) -> tuple[rasterio.Affine, int, int]:
    """The exact native-resolution output grid ``.feature()`` would produce for ``region``.

    ``rio_tiler``'s own ``Reader.feature`` (no ``width``/``height``/``max_size``)
    resamples at the dataset's native resolution, in ``dst_crs``, and sizes the
    output from the extent's own bounds divided by that resolution — not by
    windowing into a whole-dataset grid, which was tried first here and
    measured to come out sub-pixel-misaligned against ``.feature()``'s actual
    transform (plan §10, "windowed transform misalignment"). This reproduces
    that computation directly: ``calculate_default_transform`` gives the
    resolution the reprojection would use, then :func:`rasterio.transform.from_bounds`
    builds the same grid ``.feature()`` builds from the extent's own bounds.

    ``region`` (M3-18 §13) is the crop's own extent — AOI ∩ this group's own
    footprints (:func:`compute_crop_region`), not the AOI's own full bounding
    box — so a scene that only partly covers the AOI produces a grid no
    bigger than what that scene actually reaches.
    """
    res_transform, _, _ = calculate_default_transform(
        dataset.crs, dst_crs, dataset.width, dataset.height, *dataset.bounds
    )
    w_res, h_res = res_transform.a, abs(res_transform.e)
    minx, miny, maxx, maxy = region.bounds
    width = max(1, round((maxx - minx) / w_res))
    height = max(1, round((maxy - miny) / h_res))
    crop_transform = transform_from_bounds(minx, miny, maxx, maxy, width, height)
    return crop_transform, width, height



# GeoTIFF mask-file profile shared by both the windowed and the naive path
# (M3-18 §3): plain, not a COG — a same-grid, single-band 0/1 raster has no
# overviews worth building and nobody tiles a binary mask for zoom levels.
# DEFLATE for the same reason as the data COG above (M3-22, F2).
def mask_profile(*, height: int, width: int, crs: Any, transform: rasterio.Affine, block_size: int = 1024) -> dict:
    return {
        "driver": "GTiff",
        "dtype": "uint8",
        "count": 1,
        "height": height,
        "width": width,
        "crs": crs,
        "transform": transform,
        "tiled": True,
        # A multiple of 16 is GDAL's only real requirement (found for the data
        # profile above too) — it may exceed the image's own size, GDAL simply
        # pads the last block, so no extra care is needed for a small crop.
        "blockxsize": block_size,
        "blockysize": block_size,
        "compress": "deflate",
    }



def rasterize_aoi(aoi: BaseGeometry, *, height: int, width: int, transform: rasterio.Affine) -> numpy.ndarray:
    """``1`` inside ``aoi``, ``0`` outside, on the given grid (M3-18 §3)."""
    return rasterize(
        [shapely_mapping(aoi)],
        out_shape=(height, width),
        transform=transform,
        all_touched=True,
        default_value=1,
        fill=0,
        dtype="uint8",
    )



# Everything a ZIP member name may keep. Deliberately narrow rather than a list
# of what Windows forbids: an allowlist cannot be out of date the next time an
# asset key picks up a new character.
_SAFE_IN_FILENAME = re.compile(r"[^A-Za-z0-9._-]+")


def crop_filename(asset: str, *, resolution_factor: int = 1) -> str:
    """The name the crop of ``asset`` gets inside the ZIP.

    The asset key travels into the archive, and for a Zarr dataset it is not a
    plain word: ``SR_10m:b04,b03,b02`` names the group the item advertises plus
    the variables to composite (adr/0007 §12.11). A ``:`` is not a legal
    filename on Windows — depending on the extractor the entry fails or is
    silently renamed — so every run of anything outside ``[A-Za-z0-9._-]``
    becomes a single ``_``. ``visual`` stays ``visual``; the original key is
    named in the notice file, so nothing about the archive becomes a guess.

    ``resolution_factor`` (F10c, M3-18 §10): an explicitly chosen coarser
    resolution is named in the filename itself (``visual_2x.tif``), not only
    in the notice — native (``1``) adds no suffix, unchanged from before.
    """
    # Stripped at both ends, dots included: `..` survives the allowlist on its own
    # (a dot is a legal filename character) and a member called `..` or `.._x` is a
    # name no archive should carry, whatever the extractor makes of it.
    cleaned = _SAFE_IN_FILENAME.sub("_", asset).strip("._")
    # A key made only of separators would otherwise leave an empty name, and a
    # ZIP entry called ".tif" is not something a user can tell apart from another.
    suffix = f"_{resolution_factor}x" if resolution_factor != 1 else ""
    return f"{cleaned or 'asset'}{suffix}.tif"


def mask_filename(asset: str, *, resolution_factor: int = 1) -> str:
    """The name ``asset``'s companion AOI mask file gets inside the ZIP (M3-18 §3).

    Always ``<crop_filename>_mask.tif`` — same cleaning, same resolution
    suffix, so the two files for one asset sort next to each other and the
    pairing is obvious without reading the notice file.
    """
    return f"{crop_filename(asset, resolution_factor=resolution_factor)[:-4]}_mask.tif"



def group_dirname(index: int, group_count: int) -> str:
    """The ZIP folder ``build_download_zip`` writes group ``index``'s files into (M3-17).

    Empty with a single group (P19: "verschiedene Gruppen als getrennte
    Dateien im selben ZIP" implies nothing about a lone group, which keeps
    the flat layout every download had before M3-17). ``group_count`` sets
    the zero-padding width so folders still sort correctly past ``group-09``.
    """
    if group_count <= 1:
        return ""
    width = max(2, len(str(group_count)))
    return f"group-{index + 1:0{width}d}/"


def merge_first_valid(blocks: Iterable[numpy.ma.MaskedArray]) -> numpy.ma.MaskedArray:
    """The mosaic rule: per band and pixel the first valid element, block by block (``FirstMethod``).

    ``blocks`` are the same window of each item in the order of the list, and a lazy iterable
    is read only as far as it is needed: once every element is filled, the remaining items are
    not read. The one place the rule lives: the synchronous crop reads its mosaic through
    ``rio_tiler.mosaic_reader``, whose default is the same rule; the export job (M4-11a) and
    the mosaic job (M4-12a) both call this.
    """
    mosaic: numpy.ma.MaskedArray | None = None
    for block in blocks:
        if mosaic is None:
            mosaic = numpy.ma.MaskedArray(block.data.copy(), mask=numpy.ma.getmaskarray(block).copy())
        else:
            fill = mosaic.mask & ~numpy.ma.getmaskarray(block)
            mosaic.data[fill] = block.data[fill]
            mosaic.mask[fill] = False
        if not mosaic.mask.any():
            break
    if mosaic is None:
        raise ValueError("a mosaic has at least one block")
    return mosaic
