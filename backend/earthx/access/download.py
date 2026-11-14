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

**Groups, one gemergte Datei each, in one ZIP (P19, M3-17).** A request may
name more than one group of items (`api.tiler`'s ``DownloadRequest.groups`` —
the same per-overpass grouping the results list and PR #84's group outline
already use, not a new grouping this module invents). Each group mosaics and
masks on its own extent (:class:`GroupCrop`, ``compute_crop_region`` per
group); :func:`build_download_zip` writes a single group flat, as every
download did before M3-17, and more than one into its own ``group-NN/``
folder so the archive still holds exactly what P19 asks for: separate files
per group, together in one ZIP.

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

**The grid is the source's (NM4-75, Otto 03.11.2026; adr/0028).** The files of a layout lie in the CRS of the
scenes, at their pixel size and on their pixel lattice (:func:`~earthx.access.crop_rules.source_crop_grid`); only a
scene of another CRS than its group's is warped onto it. :func:`_laid_out_crop_bytes` writes them. The reading of
the sections above (EPSG:4326 at the native resolution, ``crop_asset``, ``_write_native_windowed_cog``) is what
remains for a reader that offers no raster dataset (a Zarr store) and what the export job without a layout writes.

**The rules are shared (M4-11 F1).** Grid, extent, mask, COG profile, size estimate
and the names inside the ZIP live in :mod:`earthx.access.crop_rules`, so the export
job of `processing` writes the same files without loading this module.
"""

from __future__ import annotations

import json
import logging
import math
import re
import zipfile
import zlib
from collections.abc import Callable, Iterable, Mapping, Sequence
from contextlib import ExitStack
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
from typing import Any

import numpy
import rasterio
from rasterio.enums import Resampling
from rasterio.errors import RasterioError
from rasterio.io import MemoryFile
from rasterio.vrt import WarpedVRT
from rasterio.windows import Window
from rasterio.windows import transform as window_transform
from rio_cogeo.cogeo import cog_translate
from rio_tiler.constants import WGS84_CRS
from rio_tiler.errors import EmptyMosaicError, PointOutsideBounds, TileOutsideBounds
from rio_tiler.io import BaseReader
from rio_tiler.models import ImageData
from rio_tiler.mosaic import mosaic_reader
from rioxarray.exceptions import NoDataInBounds
from shapely.errors import ShapelyError
from shapely.geometry import box
from shapely.geometry import shape as shapely_shape
from shapely.geometry.base import BaseGeometry

from earthx.access.band_export import (
    BANDS_FILENAME,
    EXPORTS_DIR,
    FORM_MULTI_BAND,
    FORM_PER_BAND,
    BandMeta,
    BandsFile,
    ExportPlanError,
    FilePlan,
    StackReader,
    aoi_on_grid,
    apply_band_tags,
    band_meta,
    bands_text,
    file_profile,
    kept_nodata,
    plan_files,
    resampling_for,
    write_blocks,
)
from earthx.access.crop_rules import (
    AOI_FILENAME,
    BLOCK_SIZE,
    CITATION_FILENAME,
    COG_PROFILE,
    FALLBACK_BYTES_PER_PIXEL,
    MAX_OUTPUT_SIDE_PX,
    NOTICE_FILENAME,
    RECIPE_FILENAME,
    AoiOutsideItems,
    PlannedOutput,
    asset_gsd,
    bytes_per_pixel,
    compute_crop_region,
    crop_filename,
    estimate_output_dims,
    group_dirname,
    mask_filename,
    mask_profile,
    native_crop_grid,
    rasterize_aoi,
    source_crop_grid,
)
from earthx.catalog.registry import AcquisitionYears, Attributable, DatasetConfig, acquisition_years
from earthx.readers.cog import AssetPath
from earthx.readers.zarr_reader import ZarrAsset

LOGGER = logging.getLogger("earthx.access.download")

__all__ = [
    "AOI_FILENAME",
    "CITATION_FILENAME",
    "LARGE_DOWNLOAD_THRESHOLD_BYTES",
    "MAX_DOWNLOAD_ITEMS",
    "MAX_OUTPUT_SIDE_PX",
    "MAX_TOTAL_OUTPUT_BYTES",
    "AoiOutsideItems",
    "AoiTooLarge",
    "AssetCropBytes",
    "InvalidAoi",
    "NOTICE_FILENAME",
    "PlannedOutput",
    "RECIPE_FILENAME",
    "asset_gsd",
    "attribution_names_year",
    "attribution_text",
    "attribution_years",
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
    "group_dirname",
    "GroupCrop",
    "mask_filename",
    "parse_aoi_geometry",
    "plan_outputs",
]


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


# A guard against abuse, not a limit of the subject (adr/0032 §10.3, F13, Otto 11.11.2026): the
# fixed 25 scenes of F4 (M3-18) are gone, because what a crop may cost is decided by its estimated
# duration and size (`api.tiler`, `MAX_CROP_SECONDS`). `crop_asset`'s `threads=1` mosaic read
# stops as soon as the AOI is fully covered (measured, plan §3), so the number of scenes bounds
# runtime, not memory; this only keeps a request from naming an absurd number of them.
MAX_DOWNLOAD_ITEMS = 2000


# What the notice may name as the reason `recipe.json` is missing: a code, not a message.
_CAUSE_CODE = re.compile(r"[a-z_]{1,32}")

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


class AoiTooLarge(ValueError):
    """The request could not fit under the size cap, found before any asset was read."""


class CorruptOutput(RuntimeError):
    """A file this module just wrote did not read back cleanly (M3-22).

    Deliberately not a ``RasterioError``: the route's handlers would report
    one as a source read failure (502) or a processing error, and this is
    neither — it is our own output failing its check before delivery.
    """


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


def check_item_count_cap(item_count: int, *, max_items: int = MAX_DOWNLOAD_ITEMS) -> None:
    """Refuse a mosaic that would have to touch more than ``max_items`` scenes (F4, M3-18)."""
    if item_count <= 0:
        raise AoiTooLarge("no item survived the AOI filter")
    if item_count > max_items:
        raise AoiTooLarge(
            f"This download covers {item_count} scenes; at most {max_items} fit in one download. "
            "Select fewer scenes or draw a smaller area."
        )


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
        return bytes_per_pixel([band.get("data_type") if isinstance(band, Mapping) else None for band in bands], asset)
    return bytes_per_pixel(None, asset)


def plan_outputs(
    items: Sequence[Mapping[str, Any]],
    assets: Sequence[str],
    region: BaseGeometry,
    *,
    pixel_size: float | None = None,
) -> list[PlannedOutput]:
    """The worst-case size of every file :func:`build_download_zip` will write, one per asset.

    ``pixel_size`` (NM4-75): the common resolution in metres of one multi-band file; every asset is then
    planned at that pixel size instead of its own.

    A mosaic across ``items`` is still one file per asset (M2-06; M3-17 keeps
    that shape, one call per group), so the size that matters is the single
    worst-case output, not a sum over items: the finest (smallest) resolution
    any item advertises for the asset and the largest bytes-per-pixel
    any item advertises, in case sources ever disagree with each other.

    ``region`` (M3-18 §13) should be the crop's own extent — AOI ∩ this
    group's own footprints (:func:`compute_crop_region`) — not the AOI's own
    full bounding box, so the estimate the size cap checks is not inflated by
    an AOI corner none of the items actually reach.
    """
    planned = []
    for asset in assets:
        gsds = [gsd for gsd in (asset_gsd(item, asset) for item in items) if gsd is not None]
        if pixel_size is not None:
            height, width = estimate_output_dims(region, pixel_size)
        elif gsds:
            height, width = estimate_output_dims(region, min(gsds))
        else:
            # Nothing on any item says how fine this asset is — the same
            # conservative upper bound M2-06 used for the whole request
            # (F1 option 1).
            height = width = MAX_OUTPUT_SIDE_PX
        bytes_per_pixel = max(
            (_asset_bytes_per_pixel(item, asset) for item in items),
            default=FALLBACK_BYTES_PER_PIXEL,
        )
        planned.append(PlannedOutput(label=asset, width=width, height=height, bytes_per_pixel=bytes_per_pixel))
    return planned


def check_output_size_cap(planned: Sequence[PlannedOutput], *, max_bytes: int = MAX_TOTAL_OUTPUT_BYTES) -> None:
    """Refuse a request whose planned output cannot fit, before any reader opens anything (M3-18).

    Replaces M2-06's item-count x asset-count worst case, which rejected any
    crop of three or more items regardless of what they actually mosaic into
    (plan §2) — the estimate here is per output file, built by
    :func:`plan_outputs` from the AOI and the items' own metadata, not from
    how many items or assets were asked for.

    **Never shrinks the request (Otto, 23.09.2026, M3-18 §10).** Over the cap,
    this always raises rather than silently choosing a coarser resolution; there is no coarser
    factor to offer any more (Otto, 03.11.2026, NM4-75), only a smaller area, fewer bands or a coarser
    common resolution of one multi-band file.
    """
    if not planned:
        raise AoiTooLarge("no output was planned for this request")
    total = sum(output.total_bytes for output in planned)
    if total <= max_bytes:
        return
    raise AoiTooLarge(
        f"This download would be about {total / 1_000_000:.0f} MB, more than the "
        f"{max_bytes / 1_000_000:.0f} MB limit. Draw a smaller area, choose fewer bands, or a coarser "
        "common resolution for one multi-band file."
    )


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
    when it groups a mosaic's scenes into one step of the time line. ``asset_paths`` are read in
    the order given, so the caller passes them in
    :func:`~earthx.access.crop_rules.mosaic_order` (NM4-02), the order of the mosaic job.

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


@dataclass(frozen=True)
class AssetCropBytes:
    """The finished bytes for one asset's crop: the data COG and its companion mask (M3-18 §3)."""

    data: bytes
    mask: bytes


def _write_native_windowed_cog(
    dataset: rasterio.DatasetReader,
    region: BaseGeometry,
    mask_geometry: BaseGeometry | None = None,
    *,
    dst_crs: rasterio.crs.CRS = WGS84_CRS,
    block_size: int = 1024,
    meta: BandMeta | None = None,
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
    crop_transform, width, height = native_crop_grid(dataset, region, dst_crs=dst_crs)
    any_valid_in_aoi = False
    with WarpedVRT(
        dataset, crs=dst_crs, transform=crop_transform, width=width, height=height,
        resampling=Resampling.nearest,
    ) as vrt:
        nodata = kept_nodata(vrt.dtypes[0], vrt.nodata)
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
        aoi_mask_profile = mask_profile(height=height, width=width, crs=dst_crs, transform=crop_transform)
        with MemoryFile() as plain_mem, MemoryFile() as aoi_mask_mem:
            with plain_mem.open(**profile) as dst, aoi_mask_mem.open(**aoi_mask_profile) as mask_dst:
                if meta is not None and vrt.count == 1:
                    apply_band_tags(dst, [meta])
                for row0 in range(0, height, block_size):
                    block_height = min(block_size, height - row0)
                    for col0 in range(0, width, block_size):
                        block_width = min(block_size, width - col0)
                        window = Window(col0, row0, block_width, block_height)
                        block = vrt.read(window=window, masked=True)
                        block_transform = window_transform(window, crop_transform)
                        inside = rasterize_aoi(
                            mask_geometry, height=block_height, width=block_width, transform=block_transform
                        )
                        # "Has real data" for the AoiOutsideItems check below only
                        # (never for the data file itself, module docstring): a
                        # pixel counts once *any* band is valid there, not only
                        # when every band is — the same criterion a mosaic's
                        # FirstMethod already uses to call a pixel "filled".
                        any_band_valid = ~numpy.ma.getmaskarray(block).all(axis=0)
                        if (inside.astype(bool) & any_band_valid).any():
                            any_valid_in_aoi = True
                        dst.write(numpy.ma.filled(block, nodata), window=window)
                        mask_dst.write(inside, 1, window=window)
            if not any_valid_in_aoi:
                raise AoiOutsideItems("the AOI does not cover any valid pixel of this item")
            with plain_mem.open() as plain_ds, MemoryFile() as cog_mem:
                cog_translate(
                    plain_ds,
                    cog_mem.name,
                    COG_PROFILE,
                    in_memory=True,
                    quiet=True,
                )
                data_bytes = cog_mem.read()
            mask_bytes = aoi_mask_mem.read()
    return AssetCropBytes(data=data_bytes, mask=mask_bytes)


def _write_mask_tif_bytes(inside: numpy.ndarray, *, transform: rasterio.Affine, crs: Any) -> bytes:
    height, width = inside.shape
    profile = mask_profile(height=height, width=width, crs=crs, transform=transform)
    with MemoryFile() as mem:
        with mem.open(**profile) as dst:
            dst.write(inside, 1)
        return mem.read()


def _image_to_asset_crop_bytes(
    image: ImageData, mask_geometry: BaseGeometry, meta: BandMeta | None = None
) -> AssetCropBytes:
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
    inside = rasterize_aoi(mask_geometry, height=height, width=width, transform=image.transform)
    any_band_valid = ~numpy.ma.getmaskarray(image.array).all(axis=0)
    if not (inside.astype(bool) & any_band_valid).any():
        raise AoiOutsideItems("the AOI does not cover any valid pixel of this item")
    data_bytes = _masked_array_to_cog_bytes(image.array, image.transform, image.crs, image.nodata, meta)
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
    meta: BandMeta | None = None,
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
                    return _write_native_windowed_cog(dataset, region, mask_shape, meta=meta)
                image = reader.part(region.bounds, width=None, height=None)
        except _AOI_MISSES_THE_DATA as error:
            raise AoiOutsideItems(str(error)) from None
        return _image_to_asset_crop_bytes(image, mask_shape, meta)

    image = crop_asset(open_reader, asset_paths, region_geometry, width=width, height=height)
    return _image_to_asset_crop_bytes(image, mask_shape, meta)


def _masked_array_to_cog_bytes(
    array: numpy.ma.MaskedArray,
    transform: rasterio.Affine,
    crs: rasterio.crs.CRS | None,
    nodata: float | None = None,
    meta: BandMeta | None = None,
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
    nodata = kept_nodata(array.dtype.name, nodata)
    filled = numpy.ma.filled(array, nodata)

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
            if meta is not None and count == 1:
                apply_band_tags(dst, [meta])
        with plain_mem.open() as plain_ds, MemoryFile() as cog_mem:
            cog_translate(
                plain_ds,
                cog_mem.name,
                COG_PROFILE,
                in_memory=True,
                quiet=True,
            )
            return cog_mem.read()


def _read_every_block(dataset: rasterio.DatasetReader) -> Any:
    """Decode every block of every band; the largest value seen, for the mask's 0/1 check."""
    peak = None
    for _, window in dataset.block_windows(1):
        block_peak = dataset.read(window=window).max()
        peak = block_peak if peak is None else max(peak, block_peak)
    return peak


def _verify_asset_crop(crop: AssetCropBytes) -> None:
    """Read both files of one crop back completely before they are delivered (M3-22, F1).

    Header first — both are GeoTIFFs, the mask is one uint8 band of 0/1 on
    exactly the data file's grid — then every block of every band, and for
    the data file every overview level too. ``cog_validate`` alone would not
    do: it checks the IFD layout but decodes no tile. Each file is opened with
    its ``MemoryFile`` held by the ``with``: a ``MemoryFile`` over bytes does
    not own them, and one collected while its dataset is still open reads
    freed memory — the cause of every "corrupt download" seen so far (plan
    m3-22 §3).
    """
    if not crop.data or not crop.mask:
        raise CorruptOutput("a generated file is empty")
    try:
        with (
            MemoryFile(crop.data) as data_mem,
            data_mem.open() as data_ds,
            MemoryFile(crop.mask) as mask_mem,
            mask_mem.open() as mask_ds,
        ):
            if data_ds.driver != "GTiff" or mask_ds.driver != "GTiff":
                raise CorruptOutput("a generated file is not a GeoTIFF")
            if mask_ds.count != 1 or mask_ds.dtypes[0] != "uint8":
                raise CorruptOutput("the mask file is not a single uint8 band")
            if (data_ds.width, data_ds.height, data_ds.transform, data_ds.crs) != (
                mask_ds.width, mask_ds.height, mask_ds.transform, mask_ds.crs
            ):
                raise CorruptOutput("the data file and its mask are not on the same grid")
            _read_every_block(data_ds)
            if _read_every_block(mask_ds) > 1:
                raise CorruptOutput("the mask file holds values other than 0 and 1")
            overview_count = len(data_ds.overviews(1))
        for level in range(overview_count):
            with MemoryFile(crop.data) as data_mem, data_mem.open(overview_level=level) as overview:
                _read_every_block(overview)
    except RasterioError as error:
        raise CorruptOutput(f"a generated file does not read back: {error}") from error


def _checked(write: Callable[[], AssetCropBytes], label: str) -> AssetCropBytes:
    """``write()``, checked, and written once more if the check fails (M3-22, F1).

    The retry repeats the whole write, reads included: the windowed path interleaves reading and
    writing, and a failure here is not expected to happen at all (plan m3-22 §3). A second failure
    raises :class:`CorruptOutput` — never a file nobody could open.
    """
    crop = write()
    try:
        _verify_asset_crop(crop)
        return crop
    except CorruptOutput as error:
        LOGGER.warning("the crop of asset %r did not read back, writing it once more: %s", label, error)
    crop = write()
    _verify_asset_crop(crop)
    return crop


def _verified_crop(
    open_reader: Callable[..., BaseReader],
    asset_paths: Sequence[AssetPath | ZarrAsset],
    region_geometry: Mapping[str, Any],
    *,
    asset: str,
    mask_geometry: Mapping[str, Any],
    meta: BandMeta | None = None,
) -> AssetCropBytes:
    """:func:`crop_asset_to_cog_bytes`, checked (:func:`_checked`)."""
    return _checked(
        lambda: crop_asset_to_cog_bytes(
            open_reader, asset_paths, region_geometry, mask_geometry=mask_geometry, meta=meta,
        ),
        asset,
    )


class NoRasterToRead(ExportPlanError):
    """The reader offers no raster dataset to lay a grid on (a Zarr store, or a double in a test)."""


def _laid_out_crop_bytes(
    open_reader: Callable[..., BaseReader],
    plan: FilePlan,
    metas: Sequence[BandMeta],
    crops: Sequence[AssetCrop],
    region_geometry: Mapping[str, Any],
    mask_geometry: Mapping[str, Any],
    *,
    form: str,
) -> AssetCropBytes:
    """One file of a layout (one band, several bands of a resolution, or all) and its mask, written block by block in memory.

    On the grid of the source (CRS, pixel size and lattice of the scenes, :func:`source_crop_grid`) and only
    resampled where the form asks for it (:func:`resampling_for`) or a scene lies in another CRS (NM4-75).
    """
    region = shapely_shape(region_geometry)
    if form == FORM_MULTI_BAND:
        methods = [resampling_for(meta, plan.resolution_m) for meta in metas]
    else:
        methods = ["none"] * len(metas)
    # The grid is laid from the finest band of the file; a common resolution scales its pixels.
    finest = min(range(len(metas)), key=lambda index: metas[index].resolution_m or math.inf)
    scale = 1.0
    if form == FORM_MULTI_BAND:
        assert plan.resolution_m is not None and metas[finest].resolution_m is not None
        scale = plan.resolution_m / metas[finest].resolution_m

    def write() -> AssetCropBytes:
        with ExitStack() as stack:
            datasets = []
            for crop in crops:
                opened = [stack.enter_context(open_reader(path)) for path in crop.paths]
                if any(getattr(reader, "dataset", None) is None for reader in opened):
                    raise NoRasterToRead("these bands cannot be laid out: the source has no raster to read")
                datasets.append([reader.dataset for reader in opened])
            if form != FORM_PER_BAND and any(ds.count != 1 for group in datasets for ds in group):
                raise ExportPlanError("a band of a stacked file has exactly one band in its source")
            crs, transform, width, height = source_crop_grid(datasets[finest][0], region, pixel_scale=scale)
            reader = StackReader(datasets, methods, crs, transform, width, height, stack)
            profile = file_profile(reader, block_size=BLOCK_SIZE)
            aoi = aoi_on_grid(mask_geometry, crs)
            with MemoryFile() as plain_mem, MemoryFile() as mask_mem, MemoryFile() as cog_mem:
                with (
                    plain_mem.open(**profile) as dst,
                    mask_mem.open(**mask_profile(height=height, width=width, crs=crs, transform=transform)) as mask_dst,
                ):
                    if reader.count == len(metas):
                        apply_band_tags(dst, metas)
                    if not write_blocks(reader, dst, mask_dst, aoi, block_size=BLOCK_SIZE):
                        raise AoiOutsideItems("the AOI does not cover any valid pixel of these bands")
                with plain_mem.open() as plain_ds:
                    cog_translate(plain_ds, cog_mem.name, COG_PROFILE, in_memory=True, quiet=True)
                return AssetCropBytes(data=cog_mem.read(), mask=mask_mem.read())

    return _checked(write, plan.name)


def _verify_zip(buffer: BytesIO) -> None:
    """Check the CRC of every ZIP entry (M3-22, F1). No retry: the ZIP is written by Python alone."""
    try:
        with zipfile.ZipFile(buffer) as archive:
            broken = archive.testzip()
    except (zipfile.BadZipFile, zlib.error, EOFError) as error:
        raise CorruptOutput(f"the ZIP archive does not read back: {error}") from error
    if broken is not None:
        raise CorruptOutput(f"the ZIP entry {broken!r} fails its CRC check")


# M3-07b, review by Otto (26.09.2026): a place-search AOI carries its own
# provenance in `properties` on the geometry dict (never a `Feature` —
# `parse_aoi_geometry`/`api.tiler`'s request model both treat the AOI as a bare
# geometry); the notice now names it, in words the caller supplied, not a
# string this module would have to hardcode ("Nominatim" is one possible
# `source` value, not the only one a future geocoder could send). The AOI
# comes in as a plain ``dict[str, Any]`` on the request body, so nothing here
# is implicitly trusted: only these three field *names* are read, only a
# string value is used, and it is capped and flattened to one line before it
# can reach the plain-text notice file.
_AOI_PROVENANCE_MAX_FIELD_CHARS = 200


def _aoi_provenance_field(properties: Mapping[str, Any], name: str) -> str | None:
    value = properties.get(name)
    if not isinstance(value, str):
        return None
    # First line only, trimmed: a value with an embedded newline could
    # otherwise smuggle extra "lines" into the notice; capped in length so an
    # oversized field cannot bloat it either.
    first_line = value.splitlines()[0].strip() if value.strip() else ""
    return first_line[:_AOI_PROVENANCE_MAX_FIELD_CHARS] or None


def _aoi_provenance_line(aoi_geometry: Mapping[str, Any]) -> str | None:
    """``None`` for the common case: a drawn or uploaded AOI carries no
    ``properties`` at all, so the notice stays exactly as it was before this
    field existed."""
    properties = aoi_geometry.get("properties")
    if not isinstance(properties, Mapping):
        return None
    attribution = _aoi_provenance_field(properties, "attribution")
    license_ = _aoi_provenance_field(properties, "license")
    parts = [part for part in (attribution, license_) if part]
    if not parts:
        return None
    line = "AOI geometry: " + ", ".join(parts)
    source = _aoi_provenance_field(properties, "source")
    if source:
        line += f" (via {source})"
    return line


def attribution_text(config: Attributable, *, years: AcquisitionYears | None) -> str | None:
    """The attribution a crop carries: the conservative "modified" text, else the plain one.

    The one place the text is made (NM4-01): from the registry's template, with ``{year}`` taken from
    the years the scenes were acquired in, never from the clock. A template without the placeholder
    (the DEM's fixed wording) needs no years; one with it and no ``years`` is a caller's mistake.
    """
    text = config.license.attribution_modified or config.license.attribution_unmodified
    if not text:
        return None
    if attribution_names_year(config) and years is None:
        raise ValueError("this attribution names the year of acquisition; the caller must give the years")
    return text.format(year=years)


def attribution_years(config: DatasetConfig, items: Iterable[Mapping[str, Any]]) -> AcquisitionYears | None:
    """The years ``items`` were acquired in, where the dataset's attribution names a year, else ``None``.

    The one place a caller learns the years (NM4-01), before anything is run or downloaded. Raises
    :class:`~earthx.catalog.registry.AcquisitionYearMissing` where the attribution needs a year and
    an item has no acquisition date: the order is refused, not given a year from the clock.
    """
    return acquisition_years(items) if attribution_names_year(config) else None


def attribution_names_year(config: Attributable) -> bool:
    """Whether the dataset's attribution has the year of acquisition in it (the DEM's fixed wording has none)."""
    text = config.license.attribution_modified or config.license.attribution_unmodified
    return bool(text) and "{year}" in text


def build_notice_text(
    config: Attributable,
    *,
    item_ids: Sequence[str],
    assets: Sequence[str] = (),
    group_item_ids: Sequence[Sequence[str]] | None = None,
    skipped_item_ids: Sequence[str] = (),
    aoi_geometry: Mapping[str, Any] | None = None,
    recipe_omitted_cause: str | None = None,
    years: AcquisitionYears | None = None,
    at: datetime | None = None,
    raster_result: bool = False,
    file_names: Mapping[str, tuple[str, str]] | None = None,
    common_resolution: float | None = None,
    group_prefix: str = "",
) -> str:
    """Attribution, the source's terms and a citation, as one plain-text file.

    Registry.py's own rule stays intact: attribution and the terms notice are
    two separate texts, never merged into one sentence, so that an unmodified
    notice can never end up implying the data were modified. A crop is treated
    as modified data throughout — cropping changes what bytes reach the user
    even where it resamples nothing, and the conservative attribution text is
    the one that cannot under-claim what happened to the pixels.

    Always English (Otto, 22.09.2026): the platform offers no language choice.

    ``group_item_ids`` (M3-17): with more than one group, the flat "Items:"
    line ``item_ids`` alone would give is replaced by one "Group N:" line per
    group, matching the ``group-NN/`` folders :func:`build_download_zip`
    writes for the same request. ``None`` or a single group keeps the
    previous flat line unchanged.

    ``skipped_item_ids`` (M3-17): a whole group dropped before any asset was
    opened because it did not touch the AOI (`api.tiler`'s ``download_crop``)
    — named here so the ZIP itself says why fewer scenes are in it than were
    requested, rather than the caller having to notice a shorter list.

    ``aoi_geometry`` (M3-07b, Otto's review 26.09.2026): when it carries a
    recognised provenance field in ``properties`` (a place-search AOI does,
    plan §9's finding otherwise left unaddressed — a drawn or uploaded one
    never does), one more line names it, so the notice — not only
    ``aoi.geojson`` — says the AOI's own shape came from somewhere requiring
    attribution. ``None`` (the previous behaviour, still every other caller's
    default) and an AOI with no such field both leave the notice unchanged.

    ``recipe_omitted_cause`` (M4-14, Otto 07.10.2026): the ZIP has no ``recipe.json``
    because `api` could not build one; one sentence says so and names the cause by its
    fixed code (a lower-case word such as ``bands``), never by anything the request or
    the item contained — no AOI, address or query. Anything else than such a code is
    refused rather than written into the file.

    ``years`` (NM4-01): the years the scenes were acquired in, which the attribution names; required
    where the dataset's attribution has a year in it. ``at`` (M4-30): the moment the notice is
    "generated". Left out it is now, as it always was. A file that must be the same bytes each
    time it is asked for — the notice in the ZIP of a job, whose ETag is built from it —
    passes the end of the job.

    ``raster_result`` (M4-30): the notice is for the ZIP of a processing job, whose rasters
    are ``result.tif`` and ``mask.tif``. The lines that describe a crop's own files (its
    assets, the native resolution, the mask beside each data file) are left out, as they
    would describe files that are not in it; a job's steps can change the resolution.

    ``file_names`` (NM4-75): the data file and the mask file each asset ended up in, where the names are not the
    cleaned asset keys (a stacked file holds several assets). ``common_resolution``: the pixel size, in metres, of
    a file made at one resolution. ``group_prefix``: the folder the ``group-NN/`` folders lie in (``exports/``).
    """
    if recipe_omitted_cause is not None and not _CAUSE_CODE.fullmatch(recipe_omitted_cause):
        raise ValueError("recipe_omitted_cause is a short lower-case code")
    license_ = config.license
    moment = at if at is not None else datetime.now(timezone.utc)
    lines = [config.title]

    attribution = attribution_text(config, years=years)
    if attribution:
        lines.append(attribution)

    if license_.terms is not None:
        text = license_.terms.notice["en"]
        lines.append(text.format(terms_url=license_.terms.url))
        lines.append(license_.terms.url)

    if config.citation:
        lines.append(config.citation)

    # DS-04 plan §4.4: what a user should know about the values, as the viewer shows it beside the data.
    lines.extend(f"{notice.label}: {notice.tooltip}" for notice in config.notices)

    # Otto, 13.11.2026: what the data cannot do, as its own section for every dataset that has limitations.
    if config.limitations:
        lines.append("\n".join(["Limitations:", *(f"- {text}" for text in config.limitations)]))

    if group_item_ids is not None and len(group_item_ids) > 1:
        for index, ids in enumerate(group_item_ids, start=1):
            lines.append(f"Group {index} ({group_prefix}{group_dirname(index - 1, len(group_item_ids))}): " + ", ".join(ids))
    else:
        lines.append("Items: " + ", ".join(item_ids))
    if skipped_item_ids:
        lines.append("Not covered by the AOI, left out: " + ", ".join(skipped_item_ids))
    if assets and not raster_result:
        # The file names in the archive are cleaned (`crop_filename`), so the keys
        # they came from are written out here — otherwise a Zarr crop's bands
        # could not be traced back to what was asked for.
        lines.append(
            "Assets: "
            + ", ".join(
                f"{asset} ({names[0]}, mask: {names[1]})"
                for asset in assets
                for names in [
                    (file_names or {}).get(asset)
                    or (crop_filename(asset), mask_filename(asset))
                ]
            )
        )
    if raster_result:
        lines.append(f"Mask: {AOI_FILENAME} carries the area; mask.tif is 1 inside it, 0 outside.")
    else:
        if common_resolution is not None:
            lines.append(f"Resolution: {common_resolution:g} m for all bands (chosen explicitly); see exports/BANDS.txt")
        else:
            lines.append("Resolution: native")
        # Mask instead of nodata (Otto, 23.09.2026, M3-18 §3): every pixel in a data
        # file keeps its bounding-box value regardless of the AOI polygon's shape;
        # each asset's own mask file (above) is where the polygon actually lives —
        # `AOI_FILENAME` is the polygon itself, once per ZIP, so the mask files need
        # no further explanation than a pointer to it.
        lines.append(
            f"Mask: {AOI_FILENAME} carries the requested area; each asset's own mask "
            "file is 1 inside it, 0 outside — the data files are not cropped to it."
        )
    if aoi_geometry is not None:
        provenance_line = _aoi_provenance_line(aoi_geometry)
        if provenance_line:
            lines.append(provenance_line)
    if recipe_omitted_cause is not None:
        lines.append(
            f"{RECIPE_FILENAME} is not included: the recipe could not be built from the "
            f"source's item metadata (cause: {recipe_omitted_cause})."
        )
    lines.append("Generated: " + moment.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"))
    return "\n\n".join(lines) + "\n"


@dataclass(frozen=True)
class AssetCrop:
    """One asset's already-resolved read candidates — one path per surviving item."""

    asset: str
    paths: tuple[AssetPath | ZarrAsset, ...]


@dataclass(frozen=True)
class GroupCrop:
    """A second (or third, ...) group in the same ZIP as the caller's first,
    explicit group (M3-17: "verschiedene Gruppen als getrennte Dateien im
    selben ZIP").

    ``region_geometry`` is that group's own crop extent — AOI ∩ *this
    group's* footprints (:func:`compute_crop_region`), not the request's AOI
    padded out to a shared bounding box: a group whose scenes only partly
    cover the AOI still crops (and masks) only as far as its own scenes
    reach, exactly as a single-group request already does.
    """

    item_ids: Sequence[str]
    crops: Sequence[AssetCrop]
    region_geometry: Mapping[str, Any]


def build_download_zip(
    *,
    config: DatasetConfig,
    open_reader: Callable[..., BaseReader],
    crops: Sequence[AssetCrop],
    aoi_geometry: Mapping[str, Any],
    item_ids: Sequence[str],
    region_geometry: Mapping[str, Any] | None = None,
    additional_groups: Sequence[GroupCrop] = (),
    skipped_item_ids: Sequence[str] = (),
    gdal_env: Mapping[str, str] | None = None,
    recipe_json: bytes | None = None,
    citation_bib: bytes | None = None,
    recipe_omitted_cause: str | None = None,
    years: AcquisitionYears | None = None,
    form: str = FORM_PER_BAND,
    common_resolution: float | None = None,
    band_metas: Mapping[str, BandMeta] | None = None,
    bands_notes: Sequence[str] = (),
) -> bytes:
    """The finished ZIP: the data files of the chosen form and their masks in ``exports/``, ``exports/BANDS.txt``,
    the AOI as GeoJSON, plus :data:`NOTICE_FILENAME`.

    Built entirely in memory (a ``BytesIO`` buffer, never a temp file) so the
    caller can stream the result without anything having touched disk.

    ``form`` and ``common_resolution`` (NM4-75): one file per band (the default), one per resolution, or one
    multi-band file at ``common_resolution`` (:mod:`earthx.access.band_export`). ``band_metas`` describes the
    assets as the items do, by asset key; an asset without an entry is described by its key alone. A band is
    always in the resolution of its source, or in ``common_resolution`` (no coarser factor is offered any more,
    Otto, 03.11.2026). ``bands_notes`` are lines for the head of ``BANDS.txt``.

    ``aoi_geometry`` is always the *original* AOI, exactly as drawn or
    uploaded (Otto, 23.09.2026, M3-18 §13): it is what ``aoi.geojson`` carries
    and what each mask's ``1``/``0`` values are rasterised from, never
    narrowed down to what the items actually cover. ``region_geometry`` — AOI
    ∩ this group's own footprints, :func:`compute_crop_region`, defaulting to
    ``aoi_geometry`` when not given — is what actually sizes the data and
    mask files' grid: a scene that only partly covers the AOI crops (and
    masks) only as far as that scene reaches, never padded out to the AOI's
    own full bounding box.

    ``gdal_env`` (F7, M3-18): the GDAL/VSI settings `gateway` builds for
    the crop (``earthx.gateway.gdal.crop_gdal_options``, NM4-26) — those of the
    tile path (timeouts, the read cache, no directory listings on open) but
    with parallel range reads. `access` may not import `gateway`
    (architekturplan.md 3.1), so the caller in `api` resolves it and hands the
    plain dict in. ``rasterio.Env`` is thread-local: the caller runs this whole
    function through ``run_in_threadpool``, so the context has to be entered
    here, on the worker thread that actually reads, not around the ``await``.

    ``additional_groups`` (M3-17, P19: "verschiedene Gruppen als getrennte
    Dateien im selben ZIP"): ``crops``/``region_geometry``/``item_ids`` above
    describe this call's *first* group, exactly as before M3-17 — a caller
    with only one group passes nothing here and gets the files directly in ``exports/``. A
    caller with more than one group also fills this in, one entry per further
    group; every group, first or additional, then writes into its own
    ``exports/group-NN/`` folder (:func:`group_dirname`).
    ``skipped_item_ids`` names items whose whole group was dropped upstream
    (`api.tiler`) for not touching the AOI at all — recorded in the notice
    only, never given a folder.

    ``recipe_json`` and ``citation_bib`` (adr/0014 §10, M4-14): finished files from
    `api`, written once at the root as :data:`RECIPE_FILENAME` and
    :data:`CITATION_FILENAME` regardless of the group count, as ``aoi.geojson`` is.
    The methods text (M4-19a) lies in ``recipe_json`` as ``provenance.methods`` (NM4-08); it comes and goes with it.
    This function does not look inside them (`access` may not import `processing`);
    ``None`` leaves the file out; ``recipe_omitted_cause`` then says so in the notice
    (:func:`build_notice_text`).
    """
    region_geometry = region_geometry if region_geometry is not None else aoi_geometry
    groups = [GroupCrop(item_ids=item_ids, crops=crops, region_geometry=region_geometry), *additional_groups]
    group_count = len(groups)
    given = band_metas or {}
    metas = {crop.asset: given.get(crop.asset) or band_meta({}, crop.asset) for crop in groups[0].crops}
    plans = plan_files(form, [metas[crop.asset] for crop in groups[0].crops], common_resolution)
    with rasterio.Env(**(gdal_env or {})):
        buffer = BytesIO()
        with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
            listed: list[BandsFile] = []
            for index, group in enumerate(groups):
                folder = EXPORTS_DIR + group_dirname(index, group_count)
                crops_by_asset = {crop.asset: crop for crop in group.crops}
                for plan in plans:
                    members = [metas[asset] for asset in plan.assets]
                    crop_bytes = None
                    if form == FORM_PER_BAND:
                        crop = crops_by_asset[plan.assets[0]]
                        if not isinstance(crop.paths[0], ZarrAsset):
                            try:
                                crop_bytes = _laid_out_crop_bytes(
                                    open_reader, plan, members, [crop], group.region_geometry, aoi_geometry,
                                    form=form,
                                )  # fmt: skip
                            except NoRasterToRead:
                                crop_bytes = None
                        if crop_bytes is None:  # a store with no raster dataset: the read of the reader itself, in WGS84
                            crop_bytes = _verified_crop(
                                open_reader, crop.paths, group.region_geometry,
                                asset=crop.asset, mask_geometry=aoi_geometry,
                                meta=metas[crop.asset],
                            )  # fmt: skip
                        methods = ["none"]
                        exports = [plan.resolution_m]
                        written = None
                    else:
                        crop_bytes = _laid_out_crop_bytes(
                            open_reader, plan, members, [crops_by_asset[asset] for asset in plan.assets],
                            group.region_geometry, aoi_geometry, form=form,
                        )  # fmt: skip
                        target = plan.resolution_m if form == FORM_MULTI_BAND else None
                        methods = [resampling_for(meta, target) for meta in members]
                        exports = [plan.resolution_m if form == FORM_MULTI_BAND else meta.resolution_m for meta in members]
                        with MemoryFile(crop_bytes.data) as written_mem, written_mem.open() as written_ds:
                            written = written_ds.dtypes[0]
                    archive.writestr(folder + plan.name, crop_bytes.data)
                    archive.writestr(folder + plan.mask_name, crop_bytes.mask)
                    listed.append(BandsFile(folder + plan.name, members, methods, exports, written))
            archive.writestr(
                EXPORTS_DIR + BANDS_FILENAME,
                bands_text(
                    title=config.title, form=form, files=listed, common_resolution=common_resolution, notes=bands_notes
                ),
            )
            # The original AOI, unclipped (Otto, 23.09.2026, M3-18 §13) — never
            # a group's own region, whatever its items actually cover. Once per
            # ZIP regardless of the group count, at the root.
            archive.writestr(AOI_FILENAME, json.dumps(dict(aoi_geometry)))
            if recipe_json is not None:
                archive.writestr(RECIPE_FILENAME, recipe_json)
            if citation_bib is not None:
                archive.writestr(CITATION_FILENAME, citation_bib)
            archive.writestr(
                NOTICE_FILENAME,
                build_notice_text(
                    config,
                    item_ids=[item_id for group in groups for item_id in group.item_ids],
                    assets=list(metas),
                    group_item_ids=[list(group.item_ids) for group in groups] if group_count > 1 else None,
                    skipped_item_ids=skipped_item_ids,
                    aoi_geometry=aoi_geometry,
                    recipe_omitted_cause=recipe_omitted_cause,
                    years=years,
                    file_names={
                        asset: (plan.name, plan.mask_name) for plan in plans for asset in plan.assets
                    },
                    common_resolution=common_resolution,
                    group_prefix=EXPORTS_DIR,
                ),
            )
        _verify_zip(buffer)
        return buffer.getvalue()

