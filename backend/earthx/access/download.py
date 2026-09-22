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

**The size cap is checked before any asset is opened, not after.** Rather than
guess a source's bytes-on-the-wire (adr/0006 §3.4 measured that this depends on
the COG's block layout, not the AOI), every read is bounded structurally by
``max_size`` — no reader call here ever produces more than
:data:`MAX_OUTPUT_SIDE_PX` pixels per side — and the byte cap is a worst-case
arithmetic bound computed from the request shape (how many items, how many
assets) before a single reader is opened. A request that could not possibly
fit under the cap, even in the best case for a single asset, never reaches
`gateway` or GDAL.

**Mosaicking (D11, adr/0006 §3.5, §4.2 Option M1):** only the crop mosaics
across items in M2, never the tile path. The item list is filtered to the
ones whose own STAC bbox actually touches the AOI before any read — the
"Vorfilter" adr/0006 §3.5 measured saves a quarter of the requests against
reading every candidate's header — and ``rio_tiler.mosaic.mosaic_reader``
merges the survivors with `FirstMethod` (first valid pixel wins), exactly the
rule the client already knows from the time line grouping (F5, F11).
"""

from __future__ import annotations

import zipfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
from typing import Any

from rasterio.io import MemoryFile
from rio_cogeo.cogeo import cog_translate
from rio_cogeo.profiles import cog_profiles
from rio_tiler.errors import EmptyMosaicError, PointOutsideBounds, TileOutsideBounds
from rio_tiler.io import BaseReader
from rio_tiler.models import ImageData
from rio_tiler.mosaic import mosaic_reader
from shapely.errors import ShapelyError
from shapely.geometry import box
from shapely.geometry import shape as shapely_shape
from shapely.geometry.base import BaseGeometry

from earthx.catalog.registry import DatasetConfig
from earthx.readers.cog import AssetPath
from earthx.readers.zarr_reader import ZarrAsset

__all__ = [
    "MAX_OUTPUT_SIDE_PX",
    "MAX_TOTAL_OUTPUT_BYTES",
    "AoiOutsideItems",
    "AoiTooLarge",
    "InvalidAoi",
    "NOTICE_FILENAME",
    "build_download_zip",
    "build_notice_text",
    "check_size_cap",
    "crop_asset",
    "filter_items_intersecting_aoi",
    "parse_aoi_geometry",
]

# Recommendation confirmed by Otto in the plan step of M2-06 (2026-09-20): a
# starting point, not a measurement — adr/0006 §3.4 has no cost curve for a
# crop this large yet. 4096 px per side keeps one asset's raw array at or
# below 4096*4096*4 bytes (~64 MB), and the combination with the byte cap below
# is what actually limits a mosaic of many items or many assets.
MAX_OUTPUT_SIDE_PX = 4096

# 200 MB total across every asset and every item a request touches (Otto,
# 2026-09-20). A single asset never reaches this on its own — the pixel cap
# above already holds it near 64 MB — so this cap mostly bites when a mosaic or
# a long asset list is requested at once.
MAX_TOTAL_OUTPUT_BYTES = 200_000_000

# The conservative per-pixel byte estimate the pre-read cap is built from:
# worst case for the dtypes GDAL reads for imagery (uint8 up to float32), one
# band. Real reads are almost always smaller once compressed and cropped to
# valid data, which is the point — the estimate must never be an
# underestimate, or the cap would let a request through that then blows memory.
_BYTES_PER_PIXEL_WORST_CASE = 4

NOTICE_FILENAME = "ATTRIBUTION.txt"

_ALLOWED_MOSAIC_EXCEPTIONS = (TileOutsideBounds, PointOutsideBounds)


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


def check_size_cap(
    *,
    item_count: int,
    asset_count: int,
    max_side: int = MAX_OUTPUT_SIDE_PX,
    max_bytes: int = MAX_TOTAL_OUTPUT_BYTES,
) -> None:
    """Refuse a request whose worst case cannot fit, before any reader opens anything.

    The worst case assumes every item contributes a full ``max_side`` x
    ``max_side`` raster for every requested asset — an upper bound a mosaic
    read can only ever come in under, never exceed, because ``max_size`` on the
    reader call enforces it structurally (§module docstring).
    """
    if item_count <= 0:
        raise AoiTooLarge("no item survived the AOI filter")
    worst_case = item_count * asset_count * max_side * max_side * _BYTES_PER_PIXEL_WORST_CASE
    if worst_case > max_bytes:
        raise AoiTooLarge(
            f"{item_count} item(s) x {asset_count} asset(s) at up to {max_side}x{max_side} px "
            f"could reach {worst_case} bytes, over the {max_bytes} byte cap"
        )


def crop_asset(
    open_reader: Callable[..., BaseReader],
    asset_paths: Sequence[AssetPath | ZarrAsset],
    aoi_geometry: Mapping[str, Any],
    *,
    max_size: int = MAX_OUTPUT_SIDE_PX,
) -> ImageData:
    """The cropped, optionally mosaicked image for one asset across its item(s).

    A single path reads directly; more than one goes through
    ``rio_tiler.mosaic.mosaic_reader`` with the default `FirstMethod` (first
    valid pixel wins, adr/0006 §3.5) — the same rule a viewer already applies
    when it groups a mosaic's scenes into one step of the time line.
    """

    def _read(path: AssetPath | ZarrAsset) -> ImageData:
        with open_reader(path) as reader:
            return reader.feature(dict(aoi_geometry), max_size=max_size)

    if len(asset_paths) == 1:
        try:
            return _read(asset_paths[0])
        except _ALLOWED_MOSAIC_EXCEPTIONS as error:
            raise AoiOutsideItems(str(error)) from None

    try:
        image, _used = mosaic_reader(
            list(asset_paths), _read, allowed_exceptions=_ALLOWED_MOSAIC_EXCEPTIONS
        )
    except EmptyMosaicError as error:
        raise AoiOutsideItems(str(error)) from None
    return image


def _image_to_cog_bytes(image: ImageData) -> bytes:
    """A real COG (internal tiling and overviews), built without touching disk.

    Two in-memory GDAL datasets, never a filesystem path: ``ImageData.to_raster``
    needs somewhere to write the plain GeoTIFF it knows how to build, and
    ``cog_translate`` needs somewhere to write the COG it turns that into.
    ``MemoryFile.name`` is a ``/vsimem/...`` path — GDAL's own virtual
    filesystem — so both writes stay in the process's RAM (D3: "nichts wird auf
    Platte geschrieben").
    """
    with MemoryFile() as plain_mem:
        image.to_raster(plain_mem.name)
        with plain_mem.open() as plain_ds, MemoryFile() as cog_mem:
            cog_translate(
                plain_ds,
                cog_mem.name,
                cog_profiles.get("deflate"),
                in_memory=True,
                quiet=True,
            )
            return cog_mem.read()


def build_notice_text(
    config: DatasetConfig, *, item_ids: Sequence[str], language: str = "en"
) -> str:
    """Attribution, the source's terms and a citation, as one plain-text file.

    Registry.py's own rule stays intact: attribution and the terms notice are
    two separate texts, never merged into one sentence, so that an unmodified
    notice can never end up implying the data were modified. A crop is treated
    as modified data throughout — cropping changes what bytes reach the user
    even where it resamples nothing, and the conservative attribution text is
    the one that cannot under-claim what happened to the pixels.
    """
    license_ = config.license
    year = datetime.now(timezone.utc).year
    lines = [config.title]

    attribution = license_.attribution_modified or license_.attribution_unmodified
    if attribution:
        lines.append(attribution.format(year=year))

    if license_.terms is not None:
        text = license_.terms.notice.get(language) or license_.terms.notice["en"]
        lines.append(text.format(terms_url=license_.terms.url))
        lines.append(license_.terms.url)

    if config.citation:
        lines.append(config.citation)

    lines.append("Items: " + ", ".join(item_ids))
    lines.append("Generated: " + datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
    return "\n\n".join(lines) + "\n"


@dataclass(frozen=True)
class AssetCrop:
    """One asset's already-resolved read candidates — one path per surviving item."""

    asset: str
    paths: tuple[AssetPath | ZarrAsset, ...]


def build_download_zip(
    *,
    config: DatasetConfig,
    open_reader: Callable[..., BaseReader],
    crops: Sequence[AssetCrop],
    aoi_geometry: Mapping[str, Any],
    item_ids: Sequence[str],
    language: str = "en",
    max_size: int = MAX_OUTPUT_SIDE_PX,
) -> bytes:
    """The finished ZIP: one COG per requested asset, plus :data:`NOTICE_FILENAME`.

    Built entirely in memory (a ``BytesIO`` buffer, never a temp file) so the
    caller can stream the result without anything having touched disk.
    """
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for crop in crops:
            image = crop_asset(open_reader, crop.paths, aoi_geometry, max_size=max_size)
            archive.writestr(f"{crop.asset}.tif", _image_to_cog_bytes(image))
        archive.writestr(
            NOTICE_FILENAME, build_notice_text(config, item_ids=item_ids, language=language)
        )
    return buffer.getvalue()
