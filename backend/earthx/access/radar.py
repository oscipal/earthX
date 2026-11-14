"""A file placed by ground control points, delivered in its own pixel grid (DS-04d, adr/0018 §9.5).

Sentinel-1 GRD is never delivered georeferenced before calibration and terrain correction (Otto, 11.11.2026). Crop,
export and job keep the file's rows and columns: no CRS, no geotransform, no flip. What places the pixels on the
ground are the GCPs of the source, written into every output shifted onto its window. The rules for that live here,
pure apart from reading the GCPs of an open dataset, so the synchronous crop of `access` and the export and job of
`processing` share them:

* :class:`RadarGrid` is the grid: its size and its GCPs, in its own pixel/line coordinates (GDAL's, a pixel ``i``
  spans ``[i, i + 1)``). :meth:`RadarGrid.window` is the pixel window around the AOI, through the thin-plate spline of
  the GCPs (the placing of the map, adr/0018 F1); :meth:`RadarGrid.mask` the AOI's shape on it, with the rule of
  ``mask.tif`` (all touched). The AOI is densified first, so its edges follow the spline between its corners.
* :meth:`RadarGrid.cut` keeps **all** GCPs, shifted by the window: a window often holds fewer than the three a spline
  needs, and with all of them the spline of the output is the spline of the source (plan §2, measured).
* :func:`join_slices` hangs the slices of one pass one under the other: the offset of a slice in lines comes from the
  times of its first and last line (the registry's ``line_times``, F2), and every seam is checked (§4.6). Slices that
  do not join split into runs; the download writes one group per run, the job refuses (F4).
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import numpy
import shapely
from rasterio.control import GroundControlPoint
from rasterio.crs import CRS
from rasterio.features import rasterize
from rasterio.transform import Affine, GCPTransformer
from rasterio.warp import transform_geom
from rasterio.windows import Window
from shapely.geometry import shape as shapely_shape
from shapely.geometry.base import BaseGeometry

from earthx.access.crop_rules import AoiOutsideItems

__all__ = [
    "DENSIFY_DEGREES",
    "JoinedPass",
    "RadarGrid",
    "RadarGridError",
    "Slice",
    "SlicesDoNotJoin",
    "join_slices",
    "line_time",
]

#: The longest edge of the AOI between two points mapped through the spline, in degrees (about 100 m).
DENSIFY_DEGREES = 0.001

#: The fewest GCPs a thin-plate spline is laid through.
MIN_GCPS = 3

#: Two slices join when the second starts this close (in lines) to a whole line after the first.
LINE_TOLERANCE = 0.05

#: The line intervals of two slices that join agree to this relative difference (measured: below 2e-8).
INTERVAL_TOLERANCE = 1e-6

#: How far (in pixel spacings) the first GCP of a slice may lie from where the line after the last one of its
#: predecessor is: the columns of both slices begin at the same ground range (measured 10.1-10.2 m for 10 m pixels).
SEAM_TOLERANCE_PIXELS = 2.0

_EARTH_RADIUS_M = 6_371_008.8


class RadarGridError(ValueError):
    """The file cannot be delivered in its own grid: it lacks GCPs, or they place nothing."""


class SlicesDoNotJoin(ValueError):
    """The slices of a pass do not hang one under the other; the text says which check failed, never a place."""


@dataclass(frozen=True)
class RadarGrid:
    """A grid in pixels and lines, placed by its GCPs (the pixel/line coordinates of this grid)."""

    width: int
    height: int
    gcps: tuple[GroundControlPoint, ...]
    gcp_crs: str

    def __post_init__(self) -> None:
        if self.width < 1 or self.height < 1:
            raise RadarGridError("a radar grid has at least one pixel")
        if len(self.gcps) < MIN_GCPS:
            raise RadarGridError(f"a file placed by its GCPs needs at least {MIN_GCPS} of them")

    @classmethod
    def of(cls, dataset: Any) -> RadarGrid:
        """The grid of an open dataset in its own pixels; :class:`RadarGridError` without GCPs and their CRS."""
        gcps, crs = dataset.gcps
        if not gcps or crs is None:
            raise RadarGridError("the file carries no GCPs with a CRS")
        return cls(int(dataset.width), int(dataset.height), tuple(gcps), CRS.from_user_input(crs).to_string())

    def _transformer(self) -> GCPTransformer:
        return GCPTransformer(list(self.gcps), tps=True)

    def pixel_geometry(self, aoi: Mapping[str, Any] | BaseGeometry) -> BaseGeometry:
        """``aoi`` (GeoJSON or shapely in EPSG:4326) in this grid's pixel/line coordinates, x the column, y the line."""
        geometry = aoi if isinstance(aoi, BaseGeometry) else shapely_shape(aoi)
        geometry = shapely.segmentize(geometry, DENSIFY_DEGREES)
        if CRS.from_user_input(self.gcp_crs) != CRS.from_epsg(4326):
            geometry = shapely_shape(transform_geom("EPSG:4326", self.gcp_crs, shapely.geometry.mapping(geometry)))
        transformer = self._transformer()

        def to_pixels(coordinates: numpy.ndarray) -> numpy.ndarray:
            lines, pixels = transformer.rowcol(coordinates[:, 0], coordinates[:, 1], op=lambda value: value)
            return numpy.column_stack([numpy.asarray(pixels, float), numpy.asarray(lines, float)])

        placed = shapely.transform(geometry, to_pixels)
        if not numpy.isfinite(shapely.get_coordinates(placed)).all():
            raise RadarGridError("the GCPs place no part of the AOI")
        return placed

    def window(self, aoi: Mapping[str, Any] | BaseGeometry) -> Window:
        """The pixel window around ``aoi``, whole pixels, inside the grid; :class:`AoiOutsideItems` where it misses."""
        minx, miny, maxx, maxy = self.pixel_geometry(aoi).bounds
        col0, row0 = max(0, math.floor(minx)), max(0, math.floor(miny))
        col1, row1 = min(self.width, math.ceil(maxx)), min(self.height, math.ceil(maxy))
        col1, row1 = max(col1, min(col0 + 1, self.width)), max(row1, min(row0 + 1, self.height))
        if col0 >= self.width or row0 >= self.height or col1 <= 0 or row1 <= 0 or col1 <= col0 or row1 <= row0:
            raise AoiOutsideItems("the AOI does not cover the scene")
        return Window(col0, row0, col1 - col0, row1 - row0)

    def mask(self, aoi: Mapping[str, Any] | BaseGeometry, window: Window) -> numpy.ndarray:
        """``1`` where a pixel of ``window`` touches the AOI, else ``0`` (``uint8``, the rule of ``mask.tif``)."""
        return rasterize(
            [self.pixel_geometry(aoi)],
            out_shape=(int(window.height), int(window.width)),
            transform=Affine.translation(window.col_off, window.row_off),
            all_touched=True,
            default_value=1,
            fill=0,
            dtype="uint8",
        )

    def cut(self, window: Window) -> RadarGrid:
        """The grid of ``window``: its size, and every GCP shifted by its offset (all of them, see the module)."""
        col0, row0 = int(window.col_off), int(window.row_off)
        shifted = tuple(
            GroundControlPoint(row=point.row - row0, col=point.col - col0, x=point.x, y=point.y, z=point.z)
            for point in self.gcps
        )
        return RadarGrid(int(window.width), int(window.height), shifted, self.gcp_crs)

    def profile(self) -> dict[str, Any]:
        """What a rasterio profile needs to write this grid: the GCPs and their CRS, no geotransform."""
        return {"gcps": list(self.gcps), "crs": CRS.from_user_input(self.gcp_crs)}


@dataclass(frozen=True)
class Slice:
    """One scene of a pass: its grid and the times of its first and last line."""

    item_id: str
    grid: RadarGrid
    first_line: datetime
    last_line: datetime

    @property
    def interval(self) -> float:
        """Seconds from one line to the next."""
        if self.grid.height < 2:
            raise SlicesDoNotJoin("a slice of one line has no line interval")
        return (self.last_line - self.first_line).total_seconds() / (self.grid.height - 1)


def line_time(item: Mapping[str, Any], name: str) -> datetime:
    """The time an item's property ``name`` gives, or :class:`SlicesDoNotJoin` where it has none."""
    value = (item.get("properties") or {}).get(name)
    if not isinstance(value, str):
        raise SlicesDoNotJoin(f"a slice lacks the time of a line ({name})")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise SlicesDoNotJoin(f"a slice gives no readable time of a line ({name})") from None
    if parsed.tzinfo is None:
        raise SlicesDoNotJoin(f"a slice gives a time of a line without a time zone ({name})")
    return parsed


def _distance(a: GroundControlPoint, b: GroundControlPoint, crs: str) -> float:
    """Metres between two GCPs on a sphere, or in the units of a projected CRS."""
    if not CRS.from_user_input(crs).is_geographic:
        return math.hypot(a.x - b.x, a.y - b.y)
    p1, p2 = math.radians(a.y), math.radians(b.y)
    dp, dl = p2 - p1, math.radians(b.x - a.x)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * _EARTH_RADIUS_M * math.asin(math.sqrt(h))


def _first_column(points: Sequence[GroundControlPoint]) -> list[GroundControlPoint]:
    """The GCPs of the first column of GCPs, top to bottom."""
    column = min(point.col for point in points)
    return sorted((point for point in points if abs(point.col - column) < 0.5), key=lambda point: point.row)


def _check_seam(upper: Slice, lower: Slice) -> None:
    """:class:`SlicesDoNotJoin` unless ``lower`` begins on the line after the last one of ``upper``."""
    interval = upper.interval
    if not math.isclose(lower.interval, interval, rel_tol=INTERVAL_TOLERANCE):
        raise SlicesDoNotJoin("two slices of the pass differ in their line interval")
    offset = (lower.first_line - upper.first_line).total_seconds() / interval
    if abs(offset - round(offset)) > LINE_TOLERANCE:
        raise SlicesDoNotJoin("a slice does not begin on a whole line of the one before")
    if round(offset) < upper.grid.height:
        raise SlicesDoNotJoin("two slices of the pass overlap")
    if round(offset) > upper.grid.height:
        raise SlicesDoNotJoin("a slice of the pass is missing")
    above, below = _first_column(upper.grid.gcps), _first_column(lower.grid.gcps)
    if len(above) < 2 or not below or abs(above[-1].col - below[0].col) >= 0.5:
        raise SlicesDoNotJoin("the GCPs of two slices do not show where their columns begin")
    last, first = above[-1], below[0]
    spacing = _distance(above[-2], last, upper.grid.gcp_crs) / max(last.row - above[-2].row, 1e-9)
    expected = (upper.grid.height + first.row - last.row) * spacing
    if abs(_distance(last, first, upper.grid.gcp_crs) - expected) > SEAM_TOLERANCE_PIXELS * spacing:
        raise SlicesDoNotJoin("the columns of two slices do not begin at the same place")


@dataclass(frozen=True)
class JoinedPass:
    """Slices hung one under the other: each with its first line in the joined grid, and the joined grid."""

    slices: tuple[Slice, ...]
    offsets: tuple[int, ...]
    grid: RadarGrid


def _joined(slices: Sequence[Slice]) -> JoinedPass:
    offsets, row, points = [], 0, []
    for piece in slices:
        offsets.append(row)
        points += [
            GroundControlPoint(row=point.row + row, col=point.col, x=point.x, y=point.y, z=point.z)
            for point in piece.grid.gcps
        ]
        row += piece.grid.height
    width = max(piece.grid.width for piece in slices)
    return JoinedPass(tuple(slices), tuple(offsets), RadarGrid(width, row, tuple(points), slices[0].grid.gcp_crs))


def join_slices(slices: Sequence[Slice]) -> tuple[list[JoinedPass], list[str]]:
    """The runs of slices that join, in the order of their first lines, and why a run ended where it did.

    One run is one file: a narrower slice is filled with nodata on the right (§4.6). A seam that fails a check of
    :func:`_check_seam` starts a new run; the reason is that check's text.
    """
    if not slices:
        raise SlicesDoNotJoin("a pass has at least one slice")
    if len({piece.grid.gcp_crs for piece in slices}) != 1:
        raise SlicesDoNotJoin("the slices of a pass name their GCPs in different CRS")
    ordered = sorted(slices, key=lambda piece: (piece.first_line, piece.item_id))
    runs: list[list[Slice]] = [[ordered[0]]]
    reasons: list[str] = []
    for upper, lower in zip(ordered, ordered[1:], strict=False):
        try:
            _check_seam(upper, lower)
        except SlicesDoNotJoin as error:
            reasons.append(str(error))
            runs.append([lower])
        else:
            runs[-1].append(lower)
    return [_joined(run) for run in runs], reasons
