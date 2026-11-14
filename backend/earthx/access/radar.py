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
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import numpy
import rasterio
import rasterio.shutil
import shapely
from rasterio.control import GroundControlPoint
from rasterio.crs import CRS
from rasterio.features import rasterize
from rasterio.transform import Affine, GCPTransformer
from rasterio.warp import transform_geom
from rasterio.windows import Window
from shapely.geometry import shape as shapely_shape
from shapely.geometry.base import BaseGeometry

from earthx.access.band_export import ExportPlanError, kept_nodata
from earthx.access.crop_rules import AoiOutsideItems, group_lines, mask_profile

__all__ = [
    "DENSIFY_DEGREES",
    "RADAR_GRID_LINE",
    "SCENE_LINE",
    "SEAM_REASONS",
    "JoinedPass",
    "RadarGrid",
    "RadarGridError",
    "RadarStackReader",
    "Slice",
    "SlicesDoNotJoin",
    "check_seam",
    "join_slices",
    "copy_to_cog",
    "gcp_key",
    "item_line_times",
    "line_time",
    "notice_with_groups",
    "notice_with_scenes",
    "pass_runs",
    "radar_profiles",
    "read_joined",
    "scene_lines",
]

#: The longest edge of the AOI between two points mapped through the spline, in degrees (about 100 m).
DENSIFY_DEGREES = 0.001

#: The fewest GCPs a thin-plate spline is laid through.
MIN_GCPS = 3

#: Two slices join when the second starts this close (in lines) to a whole line after the first. Measured on 26 pairs
#: of real slices (2019-2026): at most 0.021 lines; a quarter of a line is 2.5 m at 10 m pixels.
LINE_TOLERANCE = 0.25

#: The line intervals of two slices that join agree to this relative difference (measured: below 2e-8).
INTERVAL_TOLERANCE = 1e-6

#: How far (in pixel spacings) the first GCP of a slice may lie from where the line after the last one of its
#: predecessor is: the columns of both slices begin at the same ground range (measured 10.1-10.2 m for 10 m pixels).
SEAM_TOLERANCE_PIXELS = 2.0

_EARTH_RADIUS_M = 6_371_008.8


class RadarGridError(ValueError):
    """The file cannot be delivered in its own grid: it lacks GCPs, or they place nothing."""


#: Why slices do not join, in the words a job reports (`processing.failure_kind`): a slice between them is missing,
#: two overlap (a datatake can hold two versions of the same stretch, NRT-3h and Fast-24h, measured 2019), their
#: rows or columns do not line up, or their items give no times of their lines.
SEAM_REASONS = ("slice_missing", "slices_overlap", "slices_misaligned", "no_line_times")


class SlicesDoNotJoin(ValueError):
    """The slices of a pass do not hang one under the other; the text says which check failed, never a place.

    ``reason`` is one of :data:`SEAM_REASONS`.
    """

    def __init__(self, message: str, reason: str = "slices_misaligned") -> None:
        if reason not in SEAM_REASONS:
            raise ValueError(f"reason is one of {SEAM_REASONS}")
        super().__init__(message)
        self.reason = reason


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
        # Beside the grid on any side, a point on its edge included: checked before anything is clamped.
        if maxx < 0 or maxy < 0 or minx >= self.width or miny >= self.height:
            raise AoiOutsideItems("the AOI does not cover the scene")
        col0, row0 = max(0, math.floor(minx)), max(0, math.floor(miny))
        col1, row1 = min(self.width, math.ceil(maxx)), min(self.height, math.ceil(maxy))
        # A point or a line still has a pixel.
        col1, row1 = max(col1, col0 + 1), max(row1, row0 + 1)
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

    def same_place(self, other: RadarGrid) -> bool:
        """Whether two grids are the same size and placed by the same GCPs."""
        def key(grid: RadarGrid) -> tuple[Any, ...]:
            return (grid.width, grid.height, grid.gcp_crs, tuple((p.row, p.col, p.x, p.y, p.z) for p in grid.gcps))

        return key(self) == key(other)

    def profile(self) -> dict[str, Any]:
        """What a rasterio profile needs to write this grid: the GCPs and their CRS, no geotransform."""
        return {"gcps": list(self.gcps), "crs": CRS.from_user_input(self.gcp_crs)}


@dataclass(frozen=True)
class Slice:
    """One scene of a pass: its grid and the times of its first and last line."""

    item_id: str
    grid: RadarGrid
    first_line: datetime | None
    last_line: datetime | None

    @property
    def interval(self) -> float:
        """Seconds from one line to the next."""
        if self.first_line is None or self.last_line is None:
            raise SlicesDoNotJoin("the dataset names no times of the lines of its scenes", "no_line_times")
        if self.grid.height < 2:
            raise SlicesDoNotJoin("a slice of one line has no line interval")
        return (self.last_line - self.first_line).total_seconds() / (self.grid.height - 1)


def line_time(item: Mapping[str, Any], name: str) -> datetime:
    """The time an item's property ``name`` gives, or :class:`SlicesDoNotJoin` where it has none."""
    value = (item.get("properties") or {}).get(name)
    if not isinstance(value, str):
        raise SlicesDoNotJoin(f"a slice lacks the time of a line ({name})", "no_line_times")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise SlicesDoNotJoin(f"a slice gives no readable time of a line ({name})", "no_line_times") from None
    if parsed.tzinfo is None:
        raise SlicesDoNotJoin(f"a slice gives a time of a line without a time zone ({name})", "no_line_times")
    return parsed


def item_line_times(item: Mapping[str, Any], first: str, last: str) -> tuple[datetime, datetime] | None:
    """The times of the first and last line an item gives under ``first`` and ``last``, or ``None``."""
    try:
        start, end = line_time(item, first), line_time(item, last)
    except SlicesDoNotJoin:
        return None
    return None if end < start else (start, end)


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


def check_seam(upper: Slice, lower: Slice) -> None:
    """:class:`SlicesDoNotJoin` unless ``lower`` begins on the line after the last one of ``upper``."""
    interval = upper.interval
    assert lower.first_line is not None and upper.last_line is not None  # checked by `interval`
    # First what a person can act on: an overlap or a gap shows in the times alone, whatever the intervals.
    step = (lower.first_line - upper.last_line).total_seconds() / interval
    if step < 0.5:
        raise SlicesDoNotJoin("two slices of the pass overlap", "slices_overlap")
    if step > 1.5:
        raise SlicesDoNotJoin("a slice of the pass is missing", "slice_missing")
    if not math.isclose(lower.interval, interval, rel_tol=INTERVAL_TOLERANCE):
        raise SlicesDoNotJoin("two slices of the pass differ in their line interval")
    assert upper.first_line is not None
    offset = (lower.first_line - upper.first_line).total_seconds() / interval
    if abs(offset - round(offset)) > LINE_TOLERANCE or round(offset) != upper.grid.height:
        raise SlicesDoNotJoin("a slice does not begin on the line after the last one of the slice before")
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
    :func:`check_seam` starts a new run; the reason is that check's text.
    """
    if not slices:
        raise SlicesDoNotJoin("a pass has at least one slice")
    if len({piece.grid.gcp_crs for piece in slices}) != 1:
        raise SlicesDoNotJoin("the slices of a pass name their GCPs in different CRS")
    ordered = sorted(slices, key=lambda piece: (piece.first_line is None, piece.first_line or 0, piece.item_id))
    runs: list[list[Slice]] = [[ordered[0]]]
    reasons: list[str] = []
    for upper, lower in zip(ordered, ordered[1:], strict=False):
        try:
            check_seam(upper, lower)
        except SlicesDoNotJoin as error:
            reasons.append(str(error))
            runs.append([lower])
        else:
            runs[-1].append(lower)
    return [_joined(run) for run in runs], reasons


def pass_runs(
    slices: Sequence[Slice], region: BaseGeometry
) -> tuple[list[tuple[JoinedPass, Window]], list[str], list[str]]:
    """The runs of a group's slices with each one's window around ``region``, why the group split, and the items
    of runs ``region`` does not reach (DS-04d F4). A group with no times of its lines is one run per scene."""
    try:
        runs, reasons = join_slices(slices)
    except SlicesDoNotJoin as error:
        runs, reasons = [join_slices([piece])[0][0] for piece in slices], [str(error)]
    placed, missed = [], []
    for joined in runs:
        try:
            placed.append((joined, joined.grid.window(region)))
        except (AoiOutsideItems, RadarGridError):
            missed.extend(piece.item_id for piece in joined.slices)
    return placed, reasons, missed


#: How the text file of a download names the part of a scene in a file (DS-04d, plan §4.9, A4).
SCENE_LINE = "Scene {item}: rows {row0}-{row1}, columns {col0}-{col1} (0-based, inclusive)"


def scene_lines(joined: JoinedPass, window: Window) -> list[str]:
    """One :data:`SCENE_LINE` per slice the window reaches, in the slice's own rows and columns."""
    lines = []
    row0, row1 = int(window.row_off), int(window.row_off + window.height)
    col0, col1 = int(window.col_off), int(window.col_off + window.width)
    for piece, offset in zip(joined.slices, joined.offsets, strict=True):
        top, bottom = max(row0, offset), min(row1, offset + piece.grid.height)
        right = min(col1, piece.grid.width)
        if bottom <= top or right <= col0:
            continue
        lines.append(
            SCENE_LINE.format(item=piece.item_id, row0=top - offset, row1=bottom - offset - 1, col0=col0, col1=right - 1)
        )
    return lines


class RadarStackReader:
    """The bands of one file in radar geometry, read block by block from the slices of a joined pass (DS-04d).

    ``assets`` holds, per asset of the file, the raw datasets of the slices in the order of ``joined``; each
    lies at its offset in lines, nothing is resampled and nothing warped. ``window`` is the part of the joined grid
    the file holds. Pixels a slice does not reach (right of a narrower slice) are masked. ``transform`` is the window's
    place in the pixels of the joined grid, for laying the AOI in pixels (:meth:`RadarGrid.pixel_geometry`) on a block;
    it is never written into a file (:meth:`RadarGrid.profile`).
    """

    def __init__(self, assets: Sequence[Sequence[Any]], joined: JoinedPass, window: Window) -> None:
        self.joined = joined
        self.window = window
        self.width = int(window.width)
        self.height = int(window.height)
        self.transform = Affine.translation(window.col_off, window.row_off)
        self.grid = joined.grid.cut(window)
        self._assets = [list(datasets) for datasets in assets]
        for datasets in self._assets:
            if len(datasets) != len(joined.slices):
                raise ExportPlanError("every band of a radar file comes from every slice of its pass")
            if len({dataset.count for dataset in datasets}) != 1:
                raise ExportPlanError("the scenes of a mosaic differ in their bands")
            for dataset, piece in zip(datasets, joined.slices, strict=True):
                if (dataset.width, dataset.height) != (piece.grid.width, piece.grid.height):
                    raise ExportPlanError("the bands of a scene in radar geometry lie on different grids")
        first = [datasets[0] for datasets in self._assets]
        self.dtype = numpy.result_type(*[numpy.dtype(dataset.dtypes[0]) for dataset in first]).name
        self.band_nodata = [kept_nodata(self.dtype, dataset.nodata) for dataset in first for _ in range(dataset.count)]
        self.count = len(self.band_nodata)
        if len({"nan" if math.isnan(value) else value for value in self.band_nodata}) > 1:
            raise ExportPlanError("these bands differ in their nodata, and one GeoTIFF has one nodata for all its bands")
        self.nodata = self.band_nodata[0]

    def read(self, block: Window) -> numpy.ma.MaskedArray:
        """``block`` of this file's window: every band, masked where no slice has a value."""
        absolute = Window(self.window.col_off + block.col_off, self.window.row_off + block.row_off, block.width, block.height)
        planes = [read_joined(datasets, self.joined.offsets, absolute, self.dtype) for datasets in self._assets]
        return numpy.ma.concatenate(planes, axis=0)


def read_joined(datasets: Sequence[Any], offsets: Sequence[int], window: Window, dtype: str) -> numpy.ma.MaskedArray:
    """``window`` of a joined pass (in its pixels): each slice's rows at its offset, masked where none reaches.

    Nothing is resampled: a row of the result is a row of one slice. A window past the edge of the pass is masked
    there, so a block of a coarse grid may reach beyond it.
    """
    row0, col0 = int(window.row_off), int(window.col_off)
    height, width = int(window.height), int(window.width)
    count = datasets[0].count
    plane = numpy.ma.MaskedArray(numpy.zeros((count, height, width), dtype), mask=numpy.ones((count, height, width), bool))
    for dataset, offset in zip(datasets, offsets, strict=True):
        top, bottom = max(row0, offset), min(row0 + height, offset + dataset.height)
        left, right = max(col0, 0), min(col0 + width, dataset.width)
        if bottom <= top or right <= left:
            continue
        part = dataset.read(window=Window(left, top - offset, right - left, bottom - top), masked=True)
        rows, cols = slice(top - row0, bottom - row0), slice(left - col0, right - col0)
        plane.data[:, rows, cols] = numpy.ma.getdata(part)
        plane.mask[:, rows, cols] = numpy.ma.getmaskarray(part)
    return plane


#: The GDAL options of a data file in radar geometry: those of the crop's COG (`crop_rules.COG_PROFILE`, DEFLATE in
#: blocks of 512, nearest overviews). GDAL's own COG driver writes it, because rio-cogeo would place a file with GCPs
#: by an affine fit through them, and the file is delivered unplaced (DS-04d).
COG_OPTIONS = {"COMPRESS": "DEFLATE", "BLOCKSIZE": "512", "OVERVIEWS": "AUTO", "RESAMPLING": "NEAREST"}


def radar_profiles(reader: RadarStackReader, *, block_size: int) -> tuple[dict[str, Any], dict[str, Any]]:
    """The plain GeoTIFF profiles of a data file and its mask on ``reader``'s window: GCPs, no CRS, no geotransform."""
    placed = reader.grid.profile()
    data = {
        "driver": "GTiff", "dtype": reader.dtype, "count": reader.count, "height": reader.height, "width": reader.width,
        "tiled": True, "blockxsize": block_size, "blockysize": block_size, "nodata": reader.nodata, **placed,
    }  # fmt: skip
    mask = mask_profile(height=reader.height, width=reader.width, crs=None, transform=Affine.identity())
    del mask["transform"]
    return data, {**mask, **placed}


def copy_to_cog(dataset: Any, path: str) -> None:
    """``dataset`` as a COG at ``path``, its GCPs kept and nothing placed by them (:data:`COG_OPTIONS`)."""
    rasterio.shutil.copy(dataset, path, driver="COG", **COG_OPTIONS)


def gcp_key(dataset: Any) -> tuple[Any, ...]:
    """The GCPs of an open file as plain numbers, to compare two files."""
    points, crs = dataset.gcps
    return (str(crs), tuple((point.row, point.col, point.x, point.y, point.z) for point in points))


#: The line of the notice for files in radar geometry (DS-04d, plan §4.9), instead of "Resolution: native".
RADAR_GRID_LINE = (
    "Grid: radar geometry of the source scenes, not map-projected; each file keeps the scenes' ground control "
    "points, shifted to its window."
)


def notice_with_scenes(notice: str, lines: Sequence[str]) -> str:
    """``notice`` with ``lines`` after its :data:`RADAR_GRID_LINE`, as paragraphs like the notice's own lines.

    The export job learns the windows only while it runs, after `api` wrote the notice (DS-04d).
    """
    if not lines:
        return notice
    if RADAR_GRID_LINE not in notice:
        # An export accepted before DS-04d: its notice still says "Resolution: native"; the grid comes in front.
        return notice.rstrip("\n") + "\n\n" + "\n\n".join([RADAR_GRID_LINE, *lines]) + "\n"
    return notice.replace(RADAR_GRID_LINE, "\n\n".join([RADAR_GRID_LINE, *lines]), 1)


#: A paragraph of the notice that names the items of the ZIP (:func:`~earthx.access.crop_rules.group_lines`).
_GROUP_PARAGRAPH = re.compile(r"(Items: |Group \d+ \()")


def notice_with_groups(notice: str, groups: Sequence[Sequence[str]], prefix: str) -> str:
    """``notice`` with its lines of groups and items as the export wrote them, in their place (Otto, A15).

    `api` writes those lines for the groups of the recipe; a group whose slices do not join splits only while the
    export runs (F4), into more folders than the recipe had groups.
    """
    paragraphs = notice.rstrip("\n").split("\n\n")
    places = [index for index, paragraph in enumerate(paragraphs) if _GROUP_PARAGRAPH.match(paragraph)]
    if not places:
        return notice
    kept = [paragraph for index, paragraph in enumerate(paragraphs) if index not in places]
    kept[places[0] : places[0]] = group_lines(groups, prefix)
    return "\n\n".join(kept) + "\n"
