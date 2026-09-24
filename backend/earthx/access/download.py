"""The AOI-Zuschnitt as a ZIP: one COG per asset plus a notice file (M2-06).

architekturplan.md 6.4's addendum (D3) draws the line for M2: the crop is read
from the source assets and streamed straight to the client, nothing lands on
disk or in the object store. What is built here is the part `access` is
allowed to own — cropping, mosaicking, packing — using the reader and the
already-cleared :class:`~earthx.readers.cog.AssetPath` — or, since M2-09a, the
:class:`~earthx.readers.zarr_reader.ZarrAsset` — the caller hands in.
Resolving items and hosts through `gateway` stays in `api` (architekturplan.md
3.1: `access` may import `readers` and `catalog`, not `gateway`), the same
split `access.tiles` already draws for the tile path.

**A download is always native resolution (Otto, 23.09.2026, M3-18 §10) —
never silently downscaled.** ``max_size``/an automatic pixel cap is gone; a
crop reads at the source's own ``gsd`` unless the caller explicitly asks for
a coarser one (``width``/``height`` set, F10c — a whole number of times
coarser, computed by the caller in `api`). Over the size limit, the request
is refused, never shrunk (F10a below).

**The size cap is checked before any asset is opened, not after.** Rather than
guess a source's bytes-on-the-wire (adr/0006 §3.4 measured that this depends on
the COG's block layout, not the AOI), :func:`plan_outputs` estimates each ZIP
member's pixel count from the AOI and the item's own ``gsd`` (native, unless a
coarser resolution was chosen), and its bytes-per-pixel from the item's
``raster:bands``/``bands`` — all before a single reader is opened, so a
request that could not possibly fit under :data:`MAX_TOTAL_OUTPUT_BYTES`
(F10a, M3-18 §10) never reaches `gateway` or GDAL.

**Memory (F10a/F10b, M3-18 §10).** A single item's native-resolution crop is
read and written one block at a time (:func:`_write_native_windowed_cog`), so
its full pixel array is never held in Python at once — measured (plan §10.3)
to save a fifth to a quarter of peak memory on a large crop, with the mask
identical either way. A mosaic across items still reads one item's *whole*
window at a time (`mosaic_reader`, ``threads=1``, unwindowed): items are
capped at :data:`MAX_DOWNLOAD_ITEMS`, and `FirstMethod.exit_when_filled`
already stops it as soon as the AOI is covered (measured, plan §3), so most
mosaics only ever read one item's window regardless. A single, large
native-resolution crop can still cost gigabytes (measured, plan §10.3) —
`api.tiler` limits how many such crops run at once in the process
(:data:`LARGE_DOWNLOAD_THRESHOLD_BYTES`, F10a), which belongs there, not here
(`access` has no process-wide state).

**Mosaicking (D11, adr/0006 §3.5, §4.2 Option M1):** only the crop mosaics
across items in M2, never the tile path. The item list is filtered to the
ones whose own STAC bbox actually touches the AOI before any read — the
"Vorfilter" adr/0006 §3.5 measured saves a quarter of the requests against
reading every candidate's header — and ``rio_tiler.mosaic.mosaic_reader``
merges the survivors with `FirstMethod` (first valid pixel wins), exactly the
rule the client already knows from the time line grouping (F5, F11).

**Mask instead of nodata (Otto, 23.09.2026, M3-18 §3, replacing the
20.09.2026 decision of the same name).** The data file is always a plain
bounding-box crop: every pixel keeps the source's own value and validity,
whether or not it falls inside the AOI polygon — nothing is ever set to
``nodata`` (or masked) just for lying outside the polygon. What the polygon
actually covers travels as a *separate* file instead, one per asset
(:func:`mask_filename`): a plain uint8 GeoTIFF on the same grid as the data,
``1`` inside the polygon and ``0`` outside (never a COG — nobody tiles a
binary mask). The AOI geometry itself also ships as ``aoi.geojson``, once per
ZIP. A rectangular AOI gets a mask file too, deliberately, for uniformity
(plan §11): a "rectangle" is only ever a rectangle in WGS84 lon/lat, not
necessarily aligned with a rotated source pixel grid (an MGRS/UTM tile), so
detecting the one case where the mask would be all ``1`` reliably needs
almost the same rasterisation this file already always does — not worth a
special case that a consumer of the ZIP would then also have to know about.

The *source's own* invalidity (a real gap in the scene) still has to reach
the data file somehow — not as a mask band any more either (bug B, Otto's
review of PR #86, 23.09.2026): a real Sentinel-2 window measured wildly
different nodata counts per band (8600/686/2437 nodata pixels out of roughly
a million, only 23 of them nodata in every band at once), so most of what one
band calls nodata is genuine dark data in the others. Combining per-band
masks the way the first version of this file did (``.any(axis=0)``) blanked
out real data in bands that were perfectly valid, which is what a viewer
showed as scattered white pixels over shadow, dark forest and water. The
fix (:func:`_masked_array_to_cog_bytes`, :func:`_write_native_windowed_cog`)
carries the source's own ``nodata`` value through as a plain tag instead —
GDAL's own nodata check is per band already, so this needs no bookkeeping of
its own, just not throwing that information away.

**The crop's extent (Otto, 23.09.2026, precising "mask instead of nodata",
M3-18 §13).** The data file and its mask are never padded out to the AOI's
own full bounding box — their extent is the bounding box of *the AOI
intersected with the union of this group's own item footprints*
(:func:`compute_crop_region`), the same geometry the frontend's group outline
already shows before a download starts (PR #84, ``groupOutline.ts``): a scene
that only partly covers the AOI crops (and masks) only as far as that scene
reaches; a group that fully covers the AOI crops to the AOI's own bounding box,
unchanged from before. ``aoi.geojson`` and the mask's own pixel values are
unaffected by this — both still carry the *original*, un-clipped AOI exactly
as drawn or uploaded; only the grid the data and the mask are written on
shrinks to match what the items actually cover.
"""

from __future__ import annotations

import json
import math
import re
import warnings
import zipfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
from typing import Any

import numpy
import rasterio
from rasterio.enums import Resampling
from rasterio.features import rasterize
from rasterio.io import MemoryFile
from rasterio.transform import from_bounds as transform_from_bounds
from rasterio.vrt import WarpedVRT
from rasterio.warp import calculate_default_transform
from rasterio.windows import Window
from rasterio.windows import transform as window_transform
from rio_cogeo.cogeo import cog_translate
from rio_cogeo.profiles import cog_profiles
from rio_tiler.constants import WGS84_CRS
from rio_tiler.errors import EmptyMosaicError, PointOutsideBounds, TileOutsideBounds
from rio_tiler.io import BaseReader
from rio_tiler.models import ImageData
from rio_tiler.mosaic import mosaic_reader
from rioxarray.exceptions import NoDataInBounds
from shapely.errors import ShapelyError
from shapely.geometry import box
from shapely.geometry import mapping as shapely_mapping
from shapely.geometry import shape as shapely_shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from earthx.catalog.registry import DatasetConfig
from earthx.readers.cog import AssetPath
from earthx.readers.zarr_reader import ZarrAsset

__all__ = [
    "AOI_FILENAME",
    "LARGE_DOWNLOAD_THRESHOLD_BYTES",
    "MAX_DOWNLOAD_ITEMS",
    "MAX_OUTPUT_SIDE_PX",
    "MAX_TOTAL_OUTPUT_BYTES",
    "RESOLUTION_FACTORS",
    "AoiOutsideItems",
    "AoiTooLarge",
    "AssetCropBytes",
    "InvalidAoi",
    "NOTICE_FILENAME",
    "PlannedOutput",
    "build_download_zip",
    "build_notice_text",
    "check_item_count_cap",
    "check_output_size_cap",
    "compute_crop_region",
    "crop_asset",
    "crop_asset_to_cog_bytes",
    "crop_filename",
    "estimate_output_dims",
    "filter_items_intersecting_aoi",
    "mask_filename",
    "parse_aoi_geometry",
    "plan_outputs",
]

# Conservative fallback pixel dimension used only when an asset's `gsd` cannot
# be read off any item at all (F1, M2-06/M3-18 §10) — no longer a downscale
# mechanism for the normal case: a native-resolution crop is never clipped to
# this (Otto, 23.09.2026, M3-18 §10).
MAX_OUTPUT_SIDE_PX = 4096

# 500 MB total, raw, across every planned output file a request produces
# (Otto, 23.09.2026, M3-18 §10, replacing the 200 MB from 2026-09-20). Chosen
# from the measurement in plan §10.3/§10.4: at 500 MB raw the whole crop+COG
# pipeline peaks around 3.1 GB RSS and ~21 s in-process — acceptable for one
# request at a time, not for several at once (see LARGE_DOWNLOAD_THRESHOLD_BYTES).
MAX_TOTAL_OUTPUT_BYTES = 500_000_000

# Above this raw output size, `api.tiler` allows only one such download to run
# at a time per process (F10a, M3-18 §10): the measurement (plan §10.3) shows
# peak memory growing roughly linearly with raw output size, so two downloads
# at ~100 MB raw each would already approach the single-download peak the
# 500 MB cap above was sized for, and two at the cap itself would not fit
# beside the tile-serving path in the same process.
LARGE_DOWNLOAD_THRESHOLD_BYTES = 100_000_000

# The only resolution choices the download dialog offers (F10c, M3-18 §10):
# native, and whole-number-coarser multiples of it. Generic factors, not new
# per-asset registry fields — applied to whatever `gsd` each asset already
# reports.
RESOLUTION_FACTORS: tuple[int, ...] = (1, 2, 4, 10)

# How many scenes a single mosaic may touch (F4, M3-18, Otto 24.09.2026). This
# bounds runtime, not memory — `crop_asset`'s `threads=1` mosaic read already
# stops as soon as the AOI is fully covered (measured, plan §3), so this only
# matters when a mosaic genuinely needs many of its items to fill the AOI.
# Matches the per-tile mosaic cap `adr/0006` §5 "Zu Frage 4" already uses.
MAX_DOWNLOAD_ITEMS = 25

# Bytes per pixel for one band's GDAL/STAC `data_type` name (adr/0006 §12.3
# names the same set for `raster:bands`). Only the sizes both real sources'
# items are measured to actually use are listed; anything else falls back to
# the conservative worst case below rather than guessing.
_BYTES_PER_DTYPE: dict[str, int] = {
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
_FALLBACK_BYTES_PER_BAND = 8
_FALLBACK_BAND_COUNT = 4

# ZSTD, not `deflate` (M2-06's original choice): measured against a real
# synthetic COG with a masked, single-tile crop (F3, `add_mask=True`),
# `cog_translate`'s DEFLATE encoding was intermittently unreadable afterwards
# ("ZIPDecode: incorrect data check", a handful of runs in a few hundred,
# reproduced outside pytest too — not a flaky test). ZSTD was not observed to
# do this in the same measurement (200/200). The data COG has not passed
# `add_mask=True` since bug B (23.09.2026, PR #86 review) replaced its
# internal mask band with a plain `nodata` tag, so the specific corruption
# this measured may no longer apply to it — kept as-is regardless (F9,
# unconfirmed by Otto, is the place to revisit that, not here) since ZSTD is
# still a perfectly fine choice either way. Read once at import, not on every
# crop: `rio_cogeo` itself warns every time this profile is built, about
# exactly the trade-off being made here on purpose (older GDAL/libtiff builds
# may not read ZSTD-compressed TIFFs) — the warning is real, one occurrence of
# it belongs in a log or a review, not one per crop.
with warnings.catch_warnings():
    warnings.simplefilter("ignore", UserWarning)
    _MASKED_COG_PROFILE = cog_profiles.get("zstd")

NOTICE_FILENAME = "ATTRIBUTION.txt"

# The requested AOI, once per ZIP, as plain GeoJSON — the same geometry the
# caller sent, in WGS84 (Otto, 23.09.2026, M3-18 §3): a consumer of the mask
# files (below) needs the polygon itself to make sense of them without also
# parsing the request that produced the ZIP.
AOI_FILENAME = "aoi.geojson"

# "This read does not touch the data" — one exception per reader for the same
# fact. rio-tiler raises the first two for a COG; `NoDataInBounds` is what
# rioxarray raises under `XarrayReader.feature` when the AOI misses the array,
# and without it here an AOI beside a Zarr scene would be a 500 instead of the
# 400 the same AOI gets on a COG (found by M2-10's first crop over the second
# format). Used on both paths below: alone it is the whole refusal, in a mosaic
# it means skip this scene and take the next one.
_AOI_MISSES_THE_DATA = (TileOutsideBounds, PointOutsideBounds, NoDataInBounds)


class InvalidAoi(ValueError):
    """The AOI is not a usable GeoJSON polygon — no guessing, just refuse it."""


class AoiOutsideItems(ValueError):
    """Neither the requested items' own bbox nor their actual data touches the AOI."""


class AoiTooLarge(ValueError):
    """The request could not fit under the size cap, found before any asset was read."""


def parse_aoi_geometry(geometry: Mapping[str, Any]) -> BaseGeometry:
    """A GeoJSON mapping as a validated Polygon/MultiPolygon, or the reason it is not one.

    Validated with shapely rather than assumed: a self-intersecting ring or a
    point/line sent as an "AOI" is a malformed request (M2-06's "fehlerhafte
    Geometrie" acceptance case), not something a reader should be left to fail on
    in whatever way it happens to fail.
    """
    try:
        geom = shapely_shape(geometry)
    except (ShapelyError, ValueError, TypeError, KeyError, AttributeError) as error:
        raise InvalidAoi(f"the AOI is not a usable GeoJSON geometry: {error}") from None
    if geom.is_empty:
        raise InvalidAoi("the AOI geometry is empty")
    if geom.geom_type not in ("Polygon", "MultiPolygon"):
        raise InvalidAoi(f"the AOI must be a Polygon or MultiPolygon, not {geom.geom_type}")
    if not geom.is_valid:
        raise InvalidAoi("the AOI geometry is not valid (e.g. a self-intersecting ring)")
    return geom


def filter_items_intersecting_aoi(
    items: Sequence[Mapping[str, Any]], aoi: BaseGeometry
) -> list[Mapping[str, Any]]:
    """The items whose own STAC bbox actually touches the AOI.

    This is both the mosaic prefilter adr/0006 §3.5 recommends (cheaper than
    opening every candidate) and the pre-read half of the "AOI outside the
    item" check: an item whose bbox does not even reach the AOI is never opened.
    """
    matched = []
    for item in items:
        bbox = item.get("bbox")
        if not (isinstance(bbox, (list, tuple)) and len(bbox) == 4):
            continue
        if box(*bbox).intersects(aoi):
            matched.append(item)
    return matched


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


def check_item_count_cap(item_count: int, *, max_items: int = MAX_DOWNLOAD_ITEMS) -> None:
    """Refuse a mosaic that would have to touch more than ``max_items`` scenes (F4, M3-18)."""
    if item_count <= 0:
        raise AoiTooLarge("no item survived the AOI filter")
    if item_count > max_items:
        raise AoiTooLarge(
            f"This download covers {item_count} scenes; at most {max_items} fit in one download. "
            "Select fewer scenes or draw a smaller area."
        )


def _finite_positive(value: Any) -> float | None:
    """``value`` as a finite, positive float, or ``None`` for anything that is not one.

    Used on values that come straight off a STAC item — a ``gsd`` of ``0``,
    negative, ``NaN`` or a string is a malformed item, not something to divide
    by (found in the plan step's "zweckfremde Nutzung" pass, M3-18).
    """
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number <= 0:
        return None
    return number


def _asset_gsd(item: Mapping[str, Any], asset: str) -> float | None:
    """Ground sample distance of ``asset`` on ``item``, in metres/pixel, or ``None`` if unusable (F1).

    Tried in the order both real sources are measured to carry it (plan §3):
    the asset's own ``gsd``, then the first band's ``raster:bands``
    ``spatial_resolution``, then the item's own ``properties.gsd``.
    """
    item_asset = item.get("assets", {})
    item_asset = item_asset.get(asset, {}) if isinstance(item_asset, Mapping) else {}
    if not isinstance(item_asset, Mapping):
        item_asset = {}
    candidates: list[Any] = [item_asset.get("gsd")]
    bands = item_asset.get("raster:bands")
    if isinstance(bands, list) and bands and isinstance(bands[0], Mapping):
        candidates.append(bands[0].get("spatial_resolution"))
    properties = item.get("properties")
    if isinstance(properties, Mapping):
        candidates.append(properties.get("gsd"))
    for candidate in candidates:
        gsd = _finite_positive(candidate)
        if gsd is not None:
            return gsd
    return None


def _dtype_bytes(data_type: Any) -> int:
    """Bytes per pixel for one band's dtype name, or the conservative fallback."""
    if isinstance(data_type, str):
        size = _BYTES_PER_DTYPE.get(data_type.lower())
        if size is not None:
            return size
    return _FALLBACK_BYTES_PER_BAND


def _asset_bytes_per_pixel(item: Mapping[str, Any], asset: str) -> int:
    """Bytes one pixel of ``asset`` costs in the output, summed over its bands (F2).

    ``raster:bands``/``bands`` on the item's own asset entry names each band's
    dtype where a source has one (Earth Search does; EOPF's Zarr assets are
    measured not to, plan §3 — Otto's local check after this PR replaces the
    fallback below with the measured value). A Zarr composite asset key
    (``SR_10m:b04,b03,b02``, adr/0007 §12.11) names its band count in the key
    itself even where the item carries no ``raster:bands`` at all.
    """
    item_asset = item.get("assets", {})
    item_asset = item_asset.get(asset, {}) if isinstance(item_asset, Mapping) else {}
    if not isinstance(item_asset, Mapping):
        item_asset = {}
    bands = item_asset.get("raster:bands") or item_asset.get("bands")
    if isinstance(bands, list) and bands:
        return sum(_dtype_bytes(band.get("data_type") if isinstance(band, Mapping) else None) for band in bands)
    if ":" in asset:
        variables = [v for v in asset.split(":", 1)[1].split(",") if v]
        if variables:
            return len(variables) * _FALLBACK_BYTES_PER_BAND
    return _FALLBACK_BAND_COUNT * _FALLBACK_BYTES_PER_BAND


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


def plan_outputs(
    items: Sequence[Mapping[str, Any]],
    assets: Sequence[str],
    region: BaseGeometry,
    *,
    resolution_factor: int = 1,
) -> list[PlannedOutput]:
    """The worst-case size of every file :func:`build_download_zip` will write, one per asset.

    A mosaic across ``items`` is still one file per asset (M2-06; M3-17 keeps
    that shape, one call per group), so the size that matters is the single
    worst-case output, not a sum over items: the finest (smallest) resolution
    any item advertises for the asset — native unless ``resolution_factor``
    chooses a coarser one (F10c, M3-18 §10) — and the largest bytes-per-pixel
    any item advertises, in case sources ever disagree with each other.

    ``region`` (M3-18 §13) should be the crop's own extent — AOI ∩ this
    group's own footprints (:func:`compute_crop_region`) — not the AOI's own
    full bounding box, so the estimate the size cap checks is not inflated by
    an AOI corner none of the items actually reach.
    """
    planned = []
    for asset in assets:
        gsds = [gsd for gsd in (_asset_gsd(item, asset) for item in items) if gsd is not None]
        if gsds:
            height, width = estimate_output_dims(region, min(gsds), resolution_factor=resolution_factor)
        else:
            # Nothing on any item says how fine this asset is — the same
            # conservative upper bound M2-06 used for the whole request
            # (F1 option 1), scaled down the same way a known gsd would be.
            height = width = max(1, math.ceil(MAX_OUTPUT_SIDE_PX / resolution_factor))
        bytes_per_pixel = max(
            (_asset_bytes_per_pixel(item, asset) for item in items),
            default=_FALLBACK_BAND_COUNT * _FALLBACK_BYTES_PER_BAND,
        )
        planned.append(PlannedOutput(label=asset, width=width, height=height, bytes_per_pixel=bytes_per_pixel))
    return planned


def _smallest_fitting_factor(native_total_bytes: float, max_bytes: int) -> int | None:
    """The smallest value in :data:`RESOLUTION_FACTORS` that brings ``native_total_bytes`` under ``max_bytes``.

    A resolution factor divides both pixel dimensions, so it shrinks bytes by
    its square — ``None`` if even the coarsest offered factor still would not
    fit (F10c, M3-18 §10: never suggest a choice that would be refused too).
    """
    if native_total_bytes <= 0:
        return None
    needed = math.ceil(math.sqrt(native_total_bytes / max_bytes))
    for factor in RESOLUTION_FACTORS:
        if factor >= needed:
            return factor
    return None


def check_output_size_cap(
    planned: Sequence[PlannedOutput],
    *,
    max_bytes: int = MAX_TOTAL_OUTPUT_BYTES,
    native_planned: Sequence[PlannedOutput] | None = None,
) -> None:
    """Refuse a request whose planned output cannot fit, before any reader opens anything (M3-18).

    Replaces M2-06's item-count x asset-count worst case, which rejected any
    crop of three or more items regardless of what they actually mosaic into
    (plan §2) — the estimate here is per output file, built by
    :func:`plan_outputs` from the AOI and the items' own metadata, not from
    how many items or assets were asked for.

    **Never shrinks the request (Otto, 23.09.2026, M3-18 §10).** Over the cap,
    this always raises rather than silently choosing a coarser resolution.
    When ``native_planned`` is given (the same request planned at native
    resolution, F10c), the message names the smallest resolution factor from
    :data:`RESOLUTION_FACTORS` that would bring the request under the cap, as
    a suggestion the caller must still choose explicitly.
    """
    if not planned:
        raise AoiTooLarge("no output was planned for this request")
    total = sum(output.total_bytes for output in planned)
    if total <= max_bytes:
        return
    message = (
        f"This download would be about {total / 1_000_000:.0f} MB, more than the "
        f"{max_bytes / 1_000_000:.0f} MB limit. Draw a smaller area, or choose an "
        "explicitly coarser resolution in the download dialog"
    )
    if native_planned is not None:
        native_total = sum(output.total_bytes for output in native_planned)
        factor = _smallest_fitting_factor(native_total, max_bytes)
        if factor is not None and factor != 1:
            message += f" (at least {factor}x would fit)"
    raise AoiTooLarge(message + ".")


def crop_asset(
    open_reader: Callable[..., BaseReader],
    asset_paths: Sequence[AssetPath | ZarrAsset],
    region_geometry: Mapping[str, Any],
    *,
    width: int | None = None,
    height: int | None = None,
) -> ImageData:
    """The cropped, optionally mosaicked image for one asset across its item(s).

    A single path reads directly; more than one goes through
    ``rio_tiler.mosaic.mosaic_reader`` with the default `FirstMethod` (first
    valid pixel wins, adr/0006 §3.5) — the same rule a viewer already applies
    when it groups a mosaic's scenes into one step of the time line.

    ``threads=1`` (F4, M3-18): measured to hold memory flat regardless of how
    many items are in ``asset_paths`` — rio-tiler then reads items one at a
    time and stops as soon as ``FirstMethod`` has filled every pixel the AOI
    covers, instead of opening every item's reader concurrently (plan §3).

    ``width``/``height`` (Otto, 23.09.2026, M3-18 §10): ``None`` for both
    means native resolution — this function no longer clips a native read to
    any pixel cap. A caller that wants an explicitly coarser resolution
    passes both, already divided down from native by the chosen
    :data:`RESOLUTION_FACTORS` value.

    **Reads ``region_geometry``'s bounding box, not a polygon (Otto,
    23.09.2026, M3-18 §3/§13).** ``Reader.feature`` would rasterise a polygon
    as a cutline and bake it into the returned array's mask, which is exactly
    what the module docstring's "mask instead of nodata" rule forbids for the
    data file: every pixel in the bounding box has to keep the source's own
    value and validity. ``.part()`` reads the plain rectangle instead — the
    caller passes the *crop region* here (AOI ∩ this group's own footprints,
    :func:`compute_crop_region`), never the AOI's own full bounding box, so a
    scene that only partly covers the AOI is not padded out to it. The AOI
    polygon itself is rasterised separately, only for the companion mask file
    (:func:`crop_asset_to_cog_bytes`).
    """
    bbox = shapely_shape(region_geometry).bounds
    # `mosaic_reader` (below) does not carry a merged image's `nodata` through
    # at all (checked against its source, bug B, PR #86 review) — captured here
    # from whichever item's read happens to run first, so the merged image
    # still gets a nodata tag naming the same value its own per-band mask
    # already came from. Every item in one request is the same collection, so
    # this is never a guess in practice: they declare the same nodata value.
    first_nodata: list[float | None] = []

    def _read(path: AssetPath | ZarrAsset) -> ImageData:
        with open_reader(path) as reader:
            image = reader.part(bbox, width=width, height=height)
        if not first_nodata:
            first_nodata.append(image.nodata)
        return image

    if len(asset_paths) == 1:
        try:
            return _read(asset_paths[0])
        except _AOI_MISSES_THE_DATA as error:
            raise AoiOutsideItems(str(error)) from None

    try:
        image, _used = mosaic_reader(
            list(asset_paths), _read, threads=1, allowed_exceptions=_AOI_MISSES_THE_DATA
        )
    except EmptyMosaicError as error:
        raise AoiOutsideItems(str(error)) from None
    if image.nodata is None and first_nodata:
        image.nodata = first_nodata[0]
    return image


def _native_crop_grid(
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


@dataclass(frozen=True)
class AssetCropBytes:
    """The finished bytes for one asset's crop: the data COG and its companion mask (M3-18 §3)."""

    data: bytes
    mask: bytes


# GeoTIFF mask-file profile shared by both the windowed and the naive path
# (M3-18 §3): plain, not a COG — a same-grid, single-band 0/1 raster has no
# overviews worth building and nobody tiles a binary mask for zoom levels.
#
# ZSTD, not `deflate`: found while chasing bug B (Otto's review of PR #86,
# 23.09.2026) — repeating the mask-file tests alone (no code change) turned up
# the exact corruption shape F9 (§9) already measured for the data COG
# ("TIFFReadEncodedTile() failed" / "IReadBlock failed", a handful of runs in
# a few dozen), just on this tiled DEFLATE write instead. Same GDAL build,
# same failure mode, so the same fix: ZSTD was not observed to corrupt in the
# repeated runs that found this. F9 is still open (unconfirmed by Otto) for
# the data COG; this mask file never went through that review, so there is no
# separate decision to wait on here — it is the same bug on new code.
def _mask_profile(*, height: int, width: int, crs: Any, transform: rasterio.Affine, block_size: int = 1024) -> dict:
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
        "compress": "zstd",
    }


def _write_native_windowed_cog(
    dataset: rasterio.DatasetReader,
    region: BaseGeometry,
    mask_geometry: BaseGeometry | None = None,
    *,
    dst_crs: rasterio.crs.CRS = WGS84_CRS,
    block_size: int = 1024,
) -> AssetCropBytes:
    """The data COG plus its mask, read and written one block at a time (F10a/F10b, M3-18 §10/§3).

    Byte-identical to ``crop_asset`` + :func:`_masked_array_to_cog_bytes` for
    the data file, validated against the whole-array read before this was
    written. The difference is memory: no array bigger than one
    ``block_size`` x ``block_size`` block is ever held at once, measured (plan
    §10.3) to save a fifth to a quarter of peak RSS on a large crop. Used only
    for a single COG item at native resolution (:func:`crop_asset_to_cog_bytes`
    decides when that applies); a mosaic or an explicitly coarser resolution
    still goes through ``crop_asset``.

    **Per-band nodata, never a combined mask (Otto, 23.09.2026, PR #86 review,
    bug B).** ``vrt.read(masked=True)`` already gives each band its own
    validity — a real Sentinel-2 ``visual`` window measured 8600/686/2437
    nodata pixels across its three bands in one 1024×1024 window, only 23 of
    them nodata in *every* band, so most of those pixels are genuine dark data
    (deep shadow, water), not "no coverage". Combining them with ``.any(axis=0)``
    into one shared mask band — this function's first version — invalidated
    all three bands wherever *any one* was at its own nodata value, turning
    real dark pixels into blanked-out ones a viewer shows as empty/white. The
    fix carries the source's own ``nodata`` value through as a plain tag
    instead (:data:`rasterio.io.DatasetReader.nodata`, the same value
    ``vrt.read(masked=True)`` already used to build each band's own mask) —
    GDAL's nodata check is per band by definition, so this is "keep what the
    source delivers, per band" with no bookkeeping of our own. No internal
    mask band is written for the data file at all any more.

    **The extent and the mask geometry are two different things (M3-18
    §13).** ``region`` (AOI ∩ this group's own footprints,
    :func:`compute_crop_region`) sizes the grid; ``mask_geometry`` — the
    *original*, un-clipped AOI, defaulting to ``region`` when not given —
    is what the mask file's ``1``/``0`` values are rasterised from. They
    agree everywhere a full-AOI-covering scene makes ``region`` equal to the
    AOI itself; they can differ at a partial scene's own edge, where
    ``region``'s bounding box can include a sliver the mask still correctly
    marks ``0`` (outside the AOI) or, for a corner the scene does not reach at
    all, real image nodata.
    """
    mask_geometry = mask_geometry if mask_geometry is not None else region
    crop_transform, width, height = _native_crop_grid(dataset, region, dst_crs=dst_crs)
    mask_mapping = shapely_mapping(mask_geometry)
    any_valid_in_aoi = False
    with WarpedVRT(
        dataset, crs=dst_crs, transform=crop_transform, width=width, height=height,
        resampling=Resampling.nearest,
    ) as vrt:
        nodata = vrt.nodata
        fill_value = nodata if nodata is not None else 0
        profile: dict[str, Any] = {
            "driver": "GTiff",
            "dtype": vrt.dtypes[0],
            "count": vrt.count,
            "height": height,
            "width": width,
            "crs": dst_crs,
            "transform": crop_transform,
            "tiled": True,
            "blockxsize": block_size,
            "blockysize": block_size,
            "nodata": nodata,
        }
        mask_profile = _mask_profile(height=height, width=width, crs=dst_crs, transform=crop_transform)
        with MemoryFile() as plain_mem, MemoryFile() as aoi_mask_mem:
            with plain_mem.open(**profile) as dst, aoi_mask_mem.open(**mask_profile) as mask_dst:
                for row0 in range(0, height, block_size):
                    block_height = min(block_size, height - row0)
                    for col0 in range(0, width, block_size):
                        block_width = min(block_size, width - col0)
                        window = Window(col0, row0, block_width, block_height)
                        block = vrt.read(window=window, masked=True)
                        block_transform = window_transform(window, crop_transform)
                        inside = rasterize(
                            [mask_mapping],
                            out_shape=(block_height, block_width),
                            transform=block_transform,
                            all_touched=True,
                            default_value=1,
                            fill=0,
                            dtype="uint8",
                        )
                        # "Has real data" for the AoiOutsideItems check below only
                        # (never for the data file itself, module docstring): a
                        # pixel counts once *any* band is valid there, not only
                        # when every band is — the same criterion a mosaic's
                        # FirstMethod already uses to call a pixel "filled".
                        any_band_valid = ~numpy.ma.getmaskarray(block).all(axis=0)
                        if (inside.astype(bool) & any_band_valid).any():
                            any_valid_in_aoi = True
                        dst.write(numpy.ma.filled(block, fill_value), window=window)
                        mask_dst.write(inside, 1, window=window)
            if not any_valid_in_aoi:
                raise AoiOutsideItems("the AOI does not cover any valid pixel of this item")
            with plain_mem.open() as plain_ds, MemoryFile() as cog_mem:
                cog_translate(
                    plain_ds,
                    cog_mem.name,
                    _MASKED_COG_PROFILE,
                    in_memory=True,
                    quiet=True,
                )
                data_bytes = cog_mem.read()
            mask_bytes = aoi_mask_mem.read()
    return AssetCropBytes(data=data_bytes, mask=mask_bytes)


def _rasterize_aoi_mask(aoi: BaseGeometry, *, height: int, width: int, transform: rasterio.Affine) -> numpy.ndarray:
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


def _write_mask_tif_bytes(inside: numpy.ndarray, *, transform: rasterio.Affine, crs: Any) -> bytes:
    height, width = inside.shape
    profile = _mask_profile(height=height, width=width, crs=crs, transform=transform)
    with MemoryFile() as mem:
        with mem.open(**profile) as dst:
            dst.write(inside, 1)
        return mem.read()


def _image_to_asset_crop_bytes(image: ImageData, mask_geometry: BaseGeometry) -> AssetCropBytes:
    """The data COG plus its companion mask, from an already-read ``ImageData`` (M3-18 §3).

    ``image.nodata`` (bug B, 23.09.2026, PR #86 review) is rio-tiler's own
    record of the value it already used to build ``image.array``'s per-band
    mask — passing it on to :func:`_masked_array_to_cog_bytes` is what lets
    the output file keep that same per-band nodata, not a mask combined across
    bands.

    ``mask_geometry`` is the *original*, un-clipped AOI (M3-18 §13) — the
    grid ``image`` is already on came from the crop *region*
    (:func:`compute_crop_region`), a possibly smaller extent than the AOI's
    own bounding box, but the mask's ``1``/``0`` values are always the AOI
    polygon itself, never the region.

    **Rejects an AOI that misses the real data (bug A, Otto's review of PR
    #86, 23.09.2026).** ``.part()`` (unlike ``.feature()``'s cutline read)
    never raises for a bbox that turns out not to overlap the dataset at all —
    it silently returns an entirely masked array. Left unchecked, a mosaic
    whose STAC bbox passed the pre-filter but whose *actual*, often rotated
    footprint the AOI polygon misses (M2-10's "a bbox is not the data") would
    have come back as a normal-looking but completely empty ZIP instead of the
    :class:`AoiOutsideItems` the windowed path (:func:`_write_native_windowed_cog`)
    already raises for the equivalent single-item case.
    """
    _count, height, width = image.array.shape
    inside = _rasterize_aoi_mask(mask_geometry, height=height, width=width, transform=image.transform)
    any_band_valid = ~numpy.ma.getmaskarray(image.array).all(axis=0)
    if not (inside.astype(bool) & any_band_valid).any():
        raise AoiOutsideItems("the AOI does not cover any valid pixel of this item")
    data_bytes = _masked_array_to_cog_bytes(image.array, image.transform, image.crs, image.nodata)
    mask_bytes = _write_mask_tif_bytes(inside, transform=image.transform, crs=image.crs)
    return AssetCropBytes(data=data_bytes, mask=mask_bytes)


def crop_asset_to_cog_bytes(
    open_reader: Callable[..., BaseReader],
    asset_paths: Sequence[AssetPath | ZarrAsset],
    region_geometry: Mapping[str, Any],
    *,
    width: int | None = None,
    height: int | None = None,
    mask_geometry: Mapping[str, Any] | None = None,
) -> AssetCropBytes:
    """The finished data COG and mask for one asset's crop — the windowed path where it applies, else the naive one.

    A single :class:`~earthx.readers.cog.AssetPath` at native resolution
    (``width``/``height`` both ``None``) uses :func:`_write_native_windowed_cog`
    (F10a/F10b, M3-18 §10). Everything else — a mosaic of several items, a
    Zarr asset, or an explicitly coarser resolution — goes through the
    existing whole-array :func:`crop_asset` path: those cases are already
    bounded (mosaics by ``MAX_DOWNLOAD_ITEMS`` and ``exit_when_filled``,
    coarser reads by the smaller pixel count) so windowing them was not part
    of what plan §10.3 measured.

    ``region_geometry`` (M3-18 §13) is the crop's own extent — AOI ∩ this
    group's own footprints (:func:`compute_crop_region`) — and sizes the read;
    ``mask_geometry``, defaulting to ``region_geometry`` when not given, is
    the *original* AOI the mask's ``1``/``0`` values are rasterised from. A
    caller that never computed a region (most existing callers, and every
    test that predates M3-18 §13) gets the previous behaviour unchanged: one
    geometry doing both jobs.
    """
    region = shapely_shape(region_geometry)
    mask_shape = shapely_shape(mask_geometry) if mask_geometry is not None else region
    native = width is None and height is None
    if native and len(asset_paths) == 1 and isinstance(asset_paths[0], AssetPath):
        try:
            with open_reader(asset_paths[0]) as reader:
                # `.dataset` is what rio-tiler's own `Reader` (the real
                # `CogReader`) exposes; a reader that does not have one (a test
                # double, or a future reader type) simply does not get the
                # windowed optimisation — correctness never depends on it.
                dataset = getattr(reader, "dataset", None)
                if dataset is not None:
                    return _write_native_windowed_cog(dataset, region, mask_shape)
                image = reader.part(region.bounds, width=None, height=None)
        except _AOI_MISSES_THE_DATA as error:
            raise AoiOutsideItems(str(error)) from None
        return _image_to_asset_crop_bytes(image, mask_shape)

    image = crop_asset(open_reader, asset_paths, region_geometry, width=width, height=height)
    return _image_to_asset_crop_bytes(image, mask_shape)


def _masked_array_to_cog_bytes(
    array: numpy.ma.MaskedArray,
    transform: rasterio.Affine,
    crs: rasterio.crs.CRS | None,
    nodata: float | None = None,
) -> bytes:
    """A real COG (internal tiling and overviews), built without touching disk.

    Two in-memory GDAL datasets, never a filesystem path: the plain GeoTIFF is
    written by hand here (not ``ImageData.to_raster``, see below), and
    ``cog_translate`` needs somewhere to write the COG it turns that into.
    ``MemoryFile.name`` is a ``/vsimem/...`` path — GDAL's own virtual
    filesystem — so both writes stay in the process's RAM (D3: "nichts wird auf
    Platte geschrieben").

    **Per-band nodata, never a combined mask (Otto, 23.09.2026, PR #86 review,
    bug B).** ``array``'s own mask is already per band — the reader built it
    from each band's own value against the source's declared ``nodata``
    (:func:`_write_native_windowed_cog`'s docstring has the measurement: a
    real Sentinel-2 window had three very different per-band nodata counts,
    almost none of them nodata in *every* band). Filling with ``nodata`` and
    tagging the output with the same value keeps that per-band distinction —
    GDAL checks nodata per band by construction — instead of an internal mask
    band this function's first version wrote from ``array``'s mask
    ``.any(axis=0)``-combined across bands, which invalidated every band
    wherever *any one* of them happened to sit at its own nodata value
    (mostly real dark data, not missing coverage). The AOI polygon never
    touches this file at all any more (module docstring); its own mask has a
    separate file (:func:`_write_mask_tif_bytes`).
    """
    filled = numpy.ma.filled(array, nodata if nodata is not None else 0)

    count, height, width = filled.shape
    profile: dict[str, Any] = {
        "driver": "GTiff",
        "dtype": filled.dtype,
        "count": count,
        "height": height,
        "width": width,
        "transform": transform,
        "nodata": nodata,
    }
    if crs:
        profile["crs"] = crs

    with MemoryFile() as plain_mem:
        with plain_mem.open(**profile) as dst:
            dst.write(filled)
        with plain_mem.open() as plain_ds, MemoryFile() as cog_mem:
            cog_translate(
                plain_ds,
                cog_mem.name,
                _MASKED_COG_PROFILE,
                in_memory=True,
                quiet=True,
            )
            return cog_mem.read()


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


def build_notice_text(
    config: DatasetConfig,
    *,
    item_ids: Sequence[str],
    assets: Sequence[str] = (),
    resolution_factor: int = 1,
) -> str:
    """Attribution, the source's terms and a citation, as one plain-text file.

    Registry.py's own rule stays intact: attribution and the terms notice are
    two separate texts, never merged into one sentence, so that an unmodified
    notice can never end up implying the data were modified. A crop is treated
    as modified data throughout — cropping changes what bytes reach the user
    even where it resamples nothing, and the conservative attribution text is
    the one that cannot under-claim what happened to the pixels.

    Always English (Otto, 22.09.2026): the platform offers no language choice.
    """
    license_ = config.license
    year = datetime.now(timezone.utc).year
    lines = [config.title]

    attribution = license_.attribution_modified or license_.attribution_unmodified
    if attribution:
        lines.append(attribution.format(year=year))

    if license_.terms is not None:
        text = license_.terms.notice["en"]
        lines.append(text.format(terms_url=license_.terms.url))
        lines.append(license_.terms.url)

    if config.citation:
        lines.append(config.citation)

    lines.append("Items: " + ", ".join(item_ids))
    if assets:
        # The file names in the archive are cleaned (`crop_filename`), so the keys
        # they came from are written out here — otherwise a Zarr crop's bands
        # could not be traced back to what was asked for.
        lines.append(
            "Assets: "
            + ", ".join(
                f"{asset} ({crop_filename(asset, resolution_factor=resolution_factor)}, "
                f"mask: {mask_filename(asset, resolution_factor=resolution_factor)})"
                for asset in assets
            )
        )
    lines.append(
        "Resolution: native"
        if resolution_factor == 1
        else f"Resolution: {resolution_factor}x coarser than native (chosen explicitly)"
    )
    # Mask instead of nodata (Otto, 23.09.2026, M3-18 §3): every pixel in a data
    # file keeps its bounding-box value regardless of the AOI polygon's shape;
    # each asset's own mask file (above) is where the polygon actually lives —
    # `AOI_FILENAME` is the polygon itself, once per ZIP, so the mask files need
    # no further explanation than a pointer to it.
    lines.append(
        f"Mask: {AOI_FILENAME} carries the requested area; each asset's own mask "
        "file is 1 inside it, 0 outside — the data files are not cropped to it."
    )
    lines.append("Generated: " + datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
    return "\n\n".join(lines) + "\n"


@dataclass(frozen=True)
class AssetCrop:
    """One asset's already-resolved read candidates — one path per surviving item.

    ``width``/``height`` (F10c, M3-18 §10): ``None`` for both means native
    resolution; a caller that resolved an explicitly coarser factor (against
    this asset's own ``gsd``) passes both, already computed down from native.
    """

    asset: str
    paths: tuple[AssetPath | ZarrAsset, ...]
    width: int | None = None
    height: int | None = None


def build_download_zip(
    *,
    config: DatasetConfig,
    open_reader: Callable[..., BaseReader],
    crops: Sequence[AssetCrop],
    aoi_geometry: Mapping[str, Any],
    item_ids: Sequence[str],
    region_geometry: Mapping[str, Any] | None = None,
    resolution_factor: int = 1,
    gdal_env: Mapping[str, str] | None = None,
) -> bytes:
    """The finished ZIP: a data COG and a mask file per requested asset, the AOI
    as GeoJSON, plus :data:`NOTICE_FILENAME`.

    Built entirely in memory (a ``BytesIO`` buffer, never a temp file) so the
    caller can stream the result without anything having touched disk.

    ``aoi_geometry`` is always the *original* AOI, exactly as drawn or
    uploaded (Otto, 23.09.2026, M3-18 §13): it is what ``aoi.geojson`` carries
    and what each mask's ``1``/``0`` values are rasterised from, never
    narrowed down to what the items actually cover. ``region_geometry`` — AOI
    ∩ this group's own footprints, :func:`compute_crop_region`, defaulting to
    ``aoi_geometry`` when not given — is what actually sizes the data and
    mask files' grid: a scene that only partly covers the AOI crops (and
    masks) only as far as that scene reaches, never padded out to the AOI's
    own full bounding box.

    ``resolution_factor`` (F10c, M3-18 §10) only names the resolution the
    caller already resolved into each ``crop``'s ``width``/``height`` — it is
    never used to compute pixels here, only to label the filenames and the
    notice file with the value the caller chose.

    ``gdal_env`` (F7, M3-18): the same GDAL/VSI settings `gateway` builds for
    the tile path (``earthx.gateway.gdal.gdal_options``) — timeouts, the read
    cache, no directory listings on open. `access` may not import `gateway`
    (architekturplan.md 3.1), so the caller in `api` resolves it and hands the
    plain dict in. ``rasterio.Env`` is thread-local: the caller runs this whole
    function through ``run_in_threadpool``, so the context has to be entered
    here, on the worker thread that actually reads, not around the ``await``.
    """
    region_geometry = region_geometry if region_geometry is not None else aoi_geometry
    with rasterio.Env(**(gdal_env or {})):
        buffer = BytesIO()
        with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
            for crop in crops:
                crop_bytes = crop_asset_to_cog_bytes(
                    open_reader,
                    crop.paths,
                    region_geometry,
                    width=crop.width,
                    height=crop.height,
                    mask_geometry=aoi_geometry,
                )
                archive.writestr(
                    crop_filename(crop.asset, resolution_factor=resolution_factor), crop_bytes.data
                )
                archive.writestr(
                    mask_filename(crop.asset, resolution_factor=resolution_factor), crop_bytes.mask
                )
            # The original AOI, unclipped (Otto, 23.09.2026, M3-18 §13) — never
            # `region_geometry`, whatever the items actually cover.
            archive.writestr(AOI_FILENAME, json.dumps(dict(aoi_geometry)))
            archive.writestr(
                NOTICE_FILENAME,
                build_notice_text(
                    config,
                    item_ids=item_ids,
                    assets=[crop.asset for crop in crops],
                    resolution_factor=resolution_factor,
                ),
            )
        return buffer.getvalue()
