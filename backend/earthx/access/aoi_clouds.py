"""The cloud share inside an AOI, counted on one scene's classification raster (DS-03 plan §6.4, §6.7, §6.9).

A scene's classification (Sentinel-2's SCL) is a COG with overviews built by ``MODE`` resampling, so a coarser
level still holds real classes. :func:`measure_aoi_clouds` picks the coarsest level on which the AOI keeps at
least :data:`MIN_AOI_PIXELS` pixels (:func:`overview_factor`), reads only the AOI's window there and counts
the pixels whose centre lies inside the AOI. Nothing here opens a network connection of its own, sets a GDAL
environment or writes a log: the caller enters ``rasterio.Env`` with the options of `readers`, as
``processing.core.area_statistics`` is called, and decides what to log (never the AOI, DS-03 plan §6.9 KE3).
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy
import rasterio
import rasterio.windows
from rasterio.features import geometry_mask
from rasterio.warp import transform_geom
from rasterio.windows import Window
from shapely.geometry import box, mapping, shape
from shapely.geometry.base import BaseGeometry
from shapely.prepared import prep

import earthx
from earthx.readers.cog import AssetPath

#: The coarsest level read keeps at least this many pixels of the AOI (DS-03 plan §6.4, Otto's decision 1).
#: At 10 000 pixels the 95th percentile of the error at mixed sky is 1.1 points, the maximum 1.9 (plan §6.2.4).
MIN_AOI_PIXELS = 10_000

_AREA_TYPES = frozenset({"Polygon", "MultiPolygon"})

# How many lists lie above the numbers: Polygon rings, positions, numbers; a MultiPolygon one more.
_NUMBER_DEPTH = {"Polygon": 3, "MultiPolygon": 4}


@dataclass(frozen=True, slots=True)
class AoiClouds:
    """Pixel counts of one scene inside one AOI, on the level that was read.

    ``aoi_pixels`` are all pixels of the AOI, those past the edge of the raster included; ``data_pixels`` those
    inside the raster that are not ``nodata``; ``cloud_pixels`` those of them in a cloud class. ``resolution`` is
    the size of a pixel of the level read, in the units of the scene's CRS (metres for UTM).
    """

    cloud_pixels: int
    data_pixels: int
    aoi_pixels: int
    resolution: float

    @property
    def cloud_percent(self) -> float | None:
        """Clouds in percent of the valid pixels, one decimal; ``None`` without a valid pixel (plan §6.7)."""
        if self.data_pixels == 0:
            return None
        return round(100 * self.cloud_pixels / self.data_pixels, 1)

    @property
    def data_percent(self) -> float:
        """Valid pixels in percent of the AOI, one decimal; the part of the AOI past the raster counts as none."""
        if self.aoi_pixels == 0:
            return 0.0
        return round(100 * self.data_pixels / self.aoi_pixels, 1)

    def as_measure(self) -> dict[str, Any]:
        """The numbers of ``earthx:aoi_measure`` (plan §6.5), which is also all that is cached (§6.9 F2e)."""
        return {
            "data_percent": self.data_percent,
            "cloud_pixels": self.cloud_pixels,
            "data_pixels": self.data_pixels,
            "resolution": self.resolution,
        }


def overview_factor(aoi_native_pixels: float, factors: Sequence[int], min_pixels: int = MIN_AOI_PIXELS) -> int:
    """The largest decimation among ``factors`` that leaves the AOI at least ``min_pixels`` pixels, else 1.

    ``aoi_native_pixels`` is the AOI's area in pixels of the full-resolution grid; a level decimated by ``f``
    holds ``aoi_native_pixels / f**2`` of them. ``factors`` are the file's overviews (``[2, 4, 8, 16]``); 1 is
    the file itself. The result is one of them, so no level is invented (the rule of
    ``processing.core.area_factor``, rounded down to the levels that exist).
    """
    if min_pixels < 1:
        raise ValueError("min_pixels is at least 1")
    fitting = [factor for factor in factors if factor > 1 and aoi_native_pixels / factor**2 >= min_pixels]
    return max(fitting, default=1)


def measure_aoi_clouds(path: AssetPath, aoi: Mapping[str, Any], cloud_classes: frozenset[int]) -> AoiClouds:
    """Count the cloud and valid pixels of the classification raster at ``path`` inside ``aoi``.

    ``path`` is an :class:`~earthx.readers.cog.AssetPath`, a path the gateway cleared; a plain string is a
    ``TypeError`` (KLAERUNGEN B8), as in ``access.mosaic_tiles``. ``aoi`` is GeoJSON in EPSG:4326, a valid
    ``Polygon`` or ``MultiPolygon``; anything else is a ``ValueError`` whose text names no coordinate. The AOI is
    not simplified: the mask over 20 000 positions costs at most 50 ms (plan §6.9 KE1, §6.2.6). A pixel belongs
    to the AOI if its centre lies inside it. A pixel equal to the file's ``nodata`` has no data; class 1 and
    every other valid class that is not in ``cloud_classes`` stay in the denominator (plan §6.7). The level
    follows :data:`MIN_AOI_PIXELS` alone, a constant (KE2), so a cached measure always means the same level.

    Only the part of the AOI that lies on the raster decides the level and is counted pixel by pixel, block by
    block of the file, and only the blocks it touches are read: a thin strip across the scene or two corners far
    apart cost what they cover, not the box around them. The part past the raster's edge has no data and joins
    ``aoi_pixels`` by its area, computed in the scene's CRS; for a part far outside the scene's UTM zone that
    area is distorted, which touches ``data_percent`` only. An AOI much larger than the scene (a country against
    one tile of 110 km) therefore costs no more than the tile, and a small overlap with a tile is still read
    fine enough.
    """
    if not isinstance(path, AssetPath):
        raise TypeError("the cloud share reads a path the gateway cleared, not a plain string (KLAERUNGEN B8)")
    if not isinstance(aoi, Mapping) or aoi.get("type") not in _AREA_TYPES:
        raise ValueError("the AOI must be a Polygon or MultiPolygon")
    classes = sorted(cloud_classes)
    with rasterio.open(path) as full:
        whole, on_raster = _geometry_in(full, aoi)
        native_pixels = on_raster.area / abs(full.transform.determinant)
        factors = full.overviews(1)
        factor = overview_factor(native_pixels, factors)
        off_raster_area = whole.area - on_raster.area
        if factor == 1:
            return _count(full, on_raster, off_raster_area, classes)
        with rasterio.open(path, overview_level=factors.index(factor)) as level:
            return _count(level, on_raster, off_raster_area, classes)


def aoi_clouds_cache_key(
    dataset_id: str, item_id: str, asset: str, cloud_classes: frozenset[int], aoi: Mapping[str, Any]
) -> str:
    """The key of one measure: the scene, the classes and the AOI (DS-03 plan §6.9 F2e).

    SHA-256 over canonical JSON. The AOI goes in as its own normalised text (sorted keys, no whitespace,
    every coordinate a float), so the same AOI written with ``47`` or ``47.0`` or in another key order is one
    key, as ``search_fingerprint`` treats a search. The key can be recomputed from the AOI, so it counts as
    personal data: it is never logged, never in a URL and never in an answer, and the entry lives at most
    7 days. The caller stores it; this function only builds it.
    """
    payload = json.dumps(
        {
            "kind": "aoi-clouds/v1",
            "earthx": earthx.__version__,
            "dataset": dataset_id,
            "item": item_id,
            "asset": asset,
            "classes": sorted(cloud_classes),
            "aoi": _canonical_aoi(aoi),
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _canonical_aoi(aoi: Mapping[str, Any]) -> str:
    """The AOI's type and coordinates as normalised JSON text; nothing else of the document is measured."""
    if not isinstance(aoi, Mapping) or aoi.get("type") not in _AREA_TYPES or "coordinates" not in aoi:
        raise ValueError("the AOI must be a Polygon or MultiPolygon")
    try:
        coordinates = _floats(aoi["coordinates"], _NUMBER_DEPTH[aoi["type"]])
        return json.dumps(
            {"type": aoi["type"], "coordinates": coordinates}, separators=(",", ":"), sort_keys=True, allow_nan=False
        )
    except (TypeError, ValueError, OverflowError):
        raise ValueError("the AOI's coordinates are not finite numbers in the shape of its type") from None


def _floats(value: Any, depth: int) -> Any:
    """``value`` with every number a float, so ``47`` and ``47.0`` read alike; ``-0.0`` becomes ``0.0``.

    ``depth`` is how many lists still lie above the numbers: a ring of a Polygon is a list of positions, a
    position a list of numbers. A number or a list at another depth is a ``TypeError``.
    """
    if depth == 0:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError("not a number")
        return float(value) + 0.0
    if not isinstance(value, (list, tuple)) or not value:
        raise TypeError("not a non-empty list")
    return [_floats(item, depth - 1) for item in value]


def _geometry_in(dataset: rasterio.DatasetReader, aoi: Mapping[str, Any]) -> tuple[BaseGeometry, BaseGeometry]:
    """The AOI in the CRS of the file, whole and its part on the raster.

    An AOI that cannot be placed there, has no area or is not valid (a ring that crosses itself, parts that
    overlap) is a ``ValueError`` without its values: GEOS words a topology error with a position in it, so the
    intersection stays inside the ``try`` too.
    """
    if dataset.crs is None:
        raise ValueError("the raster has no CRS")
    try:
        whole = shape(transform_geom("EPSG:4326", dataset.crs, dict(aoi)))
        usable = whole.is_valid and whole.area > 0 and all(math.isfinite(value) for value in whole.bounds)
        on_raster = whole.intersection(box(*dataset.bounds)) if usable else None
    except Exception:  # GDAL, pyproj and GEOS word their errors with the coordinates in them
        usable = False
    if not usable:
        raise ValueError("the AOI is not a valid polygon that can be placed on the raster")
    return whole, on_raster


def _count(
    level: rasterio.DatasetReader, on_raster: BaseGeometry, off_raster_area: float, classes: list[int]
) -> AoiClouds:
    """Pixels of the AOI on the grid of ``level``: all, valid, and cloud (plan §6.7).

    Block by block of the file within the AOI's bounds, reading only the blocks the AOI touches, so neither the
    read nor the mask grows past the blocks it covers. ``off_raster_area``, the part of the AOI past the raster in
    the CRS's units squared, has no data and joins ``aoi_pixels`` by its area in pixels of this level.
    """
    off_raster = round(off_raster_area / abs(level.transform.determinant))
    data_pixels = cloud_pixels = on_pixels = 0
    if not on_raster.is_empty:
        geometry = mapping(on_raster)
        prepared = prep(on_raster)
        for window in _blocks_over(level, on_raster.bounds):
            grid = level.window_transform(window)
            if not prepared.intersects(box(*rasterio.windows.bounds(window, level.transform))):
                continue
            inside = geometry_mask(
                [geometry], out_shape=(int(window.height), int(window.width)), transform=grid, invert=True
            )
            if not inside.any():
                continue
            values = level.read(1, window=window)
            valid = inside & ~_is_nodata(values, level.nodata)
            on_pixels += int(inside.sum())
            data_pixels += int(valid.sum())
            cloud_pixels += int((valid & numpy.isin(values, classes)).sum())
    return AoiClouds(
        cloud_pixels=cloud_pixels,
        data_pixels=data_pixels,
        aoi_pixels=on_pixels + off_raster,
        resolution=abs(level.transform.a),
    )


def _blocks_over(level: rasterio.DatasetReader, bounds: tuple[float, float, float, float]) -> Iterator[Window]:
    """The file's own blocks that overlap ``bounds``, each clipped to the raster."""
    block_height, block_width = level.block_shapes[0]
    inverse = ~level.transform
    minx, miny, maxx, maxy = bounds
    corners = [inverse * (x, y) for x in (minx, maxx) for y in (miny, maxy)]
    col0 = max(math.floor(min(c for c, _ in corners)), 0) // block_width * block_width
    row0 = max(math.floor(min(r for _, r in corners)), 0) // block_height * block_height
    col1 = min(math.ceil(max(c for c, _ in corners)), level.width)
    row1 = min(math.ceil(max(r for _, r in corners)), level.height)
    for row in range(row0, row1, block_height):
        for col in range(col0, col1, block_width):
            yield Window(col, row, min(block_width, level.width - col), min(block_height, level.height - row))


def _is_nodata(values: numpy.ndarray, nodata: float | None) -> numpy.ndarray:
    if nodata is None:
        return numpy.zeros(values.shape, dtype=bool)
    if math.isnan(nodata):
        return numpy.isnan(values)
    return values == nodata
