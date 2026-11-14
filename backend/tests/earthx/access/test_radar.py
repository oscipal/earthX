"""The radar grid of DS-04d: window, mask, GCPs shifted, and slices of a pass hung one under the other.

Synthetic files only (`mini_gcp`, `mini_pass`); nothing is read from a real source.
"""

from __future__ import annotations

import dataclasses
import warnings
from datetime import timedelta
from pathlib import Path

import numpy
import pytest
import rasterio
from rasterio.control import GroundControlPoint
from rasterio.errors import NotGeoreferencedWarning
from rasterio.transform import GCPTransformer
from rasterio.windows import Window

from earthx.access import radar
from earthx.access.crop_rules import AoiOutsideItems
from earthx.access.radar import RadarGrid, RadarGridError, Slice, SlicesDoNotJoin, join_slices, line_time, pass_runs
from earthx.readers.cog import AssetPath, CogReader
from tests.earthx.readers import mini_gcp, mini_pass


@pytest.fixture(scope="module")
def gcp_file(tmp_path_factory: pytest.TempPathFactory) -> Path:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", NotGeoreferencedWarning)
        return mini_gcp.build_mini_gcp(tmp_path_factory.mktemp("radar") / "gcp.tif")


@pytest.fixture(scope="module")
def grid(gcp_file: Path) -> RadarGrid:
    with rasterio.open(gcp_file) as dataset:
        return RadarGrid.of(dataset)


def polygon(corners: list[tuple[float, float]]) -> dict:
    """A polygon through the ground positions of pixel/line ``(row, col)`` corners of the mini file."""
    ring = [mini_gcp.position(row, col) for row, col in corners]
    return {"type": "Polygon", "coordinates": [[*ring, ring[0]]]}


def box_of(row0: float, col0: float, row1: float, col1: float) -> dict:
    return polygon([(row0, col0), (row0, col1), (row1, col1), (row1, col0)])


def tps(points: tuple[GroundControlPoint, ...], rows: numpy.ndarray, cols: numpy.ndarray) -> numpy.ndarray:
    x, y = GCPTransformer(list(points), tps=True).xy(rows, cols, offset="ul")
    return numpy.column_stack([x, y])


# --- the window -------------------------------------------------------------------------------------------------


def test_the_window_encloses_the_aoi_through_the_spline(grid: RadarGrid) -> None:
    window = grid.window(box_of(20, 30, 50, 60))
    # The spline goes through the GCPs, not through every position between them: about a pixel either way.
    assert 28 <= window.col_off <= 31 and 18 <= window.row_off <= 21
    assert 59 <= window.col_off + window.width <= 62 and 49 <= window.row_off + window.height <= 52


def test_a_window_at_the_edge_stays_inside_the_scene(grid: RadarGrid) -> None:
    window = grid.window(box_of(-20, -20, 10, 10))
    assert (window.col_off, window.row_off) == (0, 0)
    assert 0 < window.width <= 12 and 0 < window.height <= 12


def test_an_aoi_beside_the_scene_has_no_window(grid: RadarGrid) -> None:
    with pytest.raises(AoiOutsideItems):
        grid.window(box_of(200, 200, 260, 260))


@pytest.mark.parametrize(
    "corners", [(-60, 10, -20, 50), (10, -60, 50, -20)], ids=["above the first line", "left of the first column"]
)
def test_an_aoi_on_the_near_side_of_the_scene_has_no_window(grid: RadarGrid, corners: tuple) -> None:
    with pytest.raises(AoiOutsideItems):
        grid.window(box_of(*corners))


def test_a_point_has_a_window_of_one_pixel(grid: RadarGrid) -> None:
    lon, lat = mini_gcp.position(40.5, 40.5)
    window = grid.window({"type": "Point", "coordinates": [lon, lat]})
    assert (window.width, window.height) == (1, 1)


def test_a_multipolygon_takes_the_window_around_all_its_parts(grid: RadarGrid) -> None:
    first, second = box_of(10, 10, 20, 20), box_of(60, 60, 70, 70)
    multi = {"type": "MultiPolygon", "coordinates": [first["coordinates"], second["coordinates"]]}
    window = grid.window(multi)
    assert window.col_off <= 11 and window.col_off + window.width >= 69


def test_a_scene_does_not_flip(grid: RadarGrid) -> None:
    # Line 0 stays the first line: an AOI near the first lines has a window near row 0, whatever the direction.
    assert grid.window(box_of(2, 40, 6, 44)).row_off < 5


# --- the mask ---------------------------------------------------------------------------------------------------


def test_the_mask_marks_the_shape_and_not_the_whole_window(grid: RadarGrid) -> None:
    triangle = polygon([(20, 20), (20, 70), (70, 20)])
    window = grid.window(triangle)
    mask = grid.mask(triangle, window)
    assert mask.shape == (window.height, window.width) and mask.dtype == numpy.uint8
    assert mask[2, 2] == 1 and mask[-2, -2] == 0
    assert 0.3 < mask.mean() < 0.75


def test_the_mask_leaves_a_hole_out(grid: RadarGrid) -> None:
    outer, inner = box_of(10, 10, 80, 80), box_of(35, 35, 55, 55)
    ring = inner["coordinates"][0][::-1]
    with_hole = {"type": "Polygon", "coordinates": [outer["coordinates"][0], ring]}
    window = grid.window(with_hole)
    mask = grid.mask(with_hole, window)

    def at(row: int, col: int) -> int:
        return int(mask[row - int(window.row_off), col - int(window.col_off)])

    assert at(45, 45) == 0 and at(20, 20) == 1


def test_edges_follow_the_spline_between_the_corners(grid: RadarGrid, monkeypatch: pytest.MonkeyPatch) -> None:
    # The bend of the mini file bows a straight edge on the ground; only a densified edge follows it in pixels.
    aoi = box_of(5, 5, 90, 90)
    window = grid.window(aoi)
    densified = grid.mask(aoi, window)
    monkeypatch.setattr(radar, "DENSIFY_DEGREES", 10.0)
    corners_only = grid.mask(aoi, window)
    assert len(grid.pixel_geometry(aoi).exterior.coords) == 5
    assert (densified != corners_only).sum() > 20


# --- the GCPs ---------------------------------------------------------------------------------------------------


def test_a_cut_keeps_every_gcp_shifted_by_the_window(grid: RadarGrid) -> None:
    window = Window(30, 20, 31, 31)
    cut = grid.cut(window)
    assert (cut.width, cut.height) == (31, 31)
    assert len(cut.gcps) == len(grid.gcps)
    assert all(
        (after.row, after.col, after.x, after.y) == (before.row - 20, before.col - 30, before.x, before.y)
        for before, after in zip(grid.gcps, cut.gcps, strict=True)
    )


def test_the_spline_of_a_cut_is_the_spline_of_the_source(grid: RadarGrid) -> None:
    window = Window(30, 20, 31, 31)
    rows = numpy.linspace(0, 30, 13)
    cols = numpy.linspace(0, 30, 11)
    rows, cols = (array.ravel() for array in numpy.meshgrid(rows, cols))
    here = tps(grid.cut(window).gcps, rows, cols)
    there = tps(grid.gcps, rows + 20, cols + 30)
    assert numpy.abs(here - there).max() < 1e-9


def test_a_window_without_gcps_of_its_own_stays_placed(grid: RadarGrid) -> None:
    window = Window(40, 40, 4, 4)
    inside = [point for point in grid.gcps if 40 <= point.row < 44 and 40 <= point.col < 44]
    assert not inside
    assert len(grid.cut(window).gcps) == len(grid.gcps)


def test_the_profile_writes_gcps_and_no_crs(grid: RadarGrid, tmp_path: Path) -> None:
    cut = grid.cut(Window(10, 10, 20, 20))
    with warnings.catch_warnings():
        warnings.simplefilter("error", NotGeoreferencedWarning)
        with rasterio.open(
            tmp_path / "out.tif", "w", driver="GTiff", dtype="uint8", count=1, width=20, height=20, **cut.profile()
        ) as dst:
            dst.write(numpy.ones((1, 20, 20), "uint8"))
        with rasterio.open(tmp_path / "out.tif") as written:
            assert written.crs is None
            assert written.transform.is_identity
            assert len(written.gcps[0]) == len(grid.gcps)


def test_a_file_without_gcps_is_no_radar_grid(tmp_path: Path) -> None:
    from tests.earthx.readers.mini_cog import build_mini_cog

    path = build_mini_cog(tmp_path / "plain.tif")
    with rasterio.open(path) as dataset, pytest.raises(RadarGridError):
        RadarGrid.of(dataset)


def test_two_gcps_place_nothing() -> None:
    points = tuple(GroundControlPoint(row=r, col=c, x=c, y=-r) for r, c in ((0, 0), (5, 5)))
    with pytest.raises(RadarGridError):
        RadarGrid(10, 10, points, "EPSG:4326")


def test_an_empty_grid_is_refused(grid: RadarGrid) -> None:
    with pytest.raises(RadarGridError):
        RadarGrid(0, 5, grid.gcps, grid.gcp_crs)


# --- the reader -------------------------------------------------------------------------------------------------


def test_the_reader_keeps_the_raw_file_beside_the_spline(gcp_file: Path) -> None:
    path = AssetPath(str(gcp_file), dataset_id="d", item_id="i", asset="vv", georeferencing="gcp_tps")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", NotGeoreferencedWarning)
        with CogReader(path) as reader:
            assert reader.dataset.crs is not None
            assert reader.raw.crs is None
            assert (reader.raw.width, reader.raw.height) == (mini_gcp.SIZE, mini_gcp.SIZE)


def test_a_file_read_as_written_is_placed_by_its_gcps(gcp_file: Path) -> None:
    path = AssetPath(str(gcp_file), dataset_id="d", item_id="", asset="result.tif", georeferencing="as_written")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", NotGeoreferencedWarning)
        with CogReader(path) as reader:
            assert reader.dataset.crs == mini_gcp.GCP_CRS


def test_a_plain_file_read_as_written_keeps_its_geotransform(tmp_path: Path) -> None:
    from tests.earthx.readers.mini_cog import build_mini_cog

    local = build_mini_cog(tmp_path / "plain.tif")
    path = AssetPath(str(local), dataset_id="d", item_id="", asset="result.tif", georeferencing="as_written")
    with CogReader(path) as reader:
        assert reader.dataset is reader.raw


def test_an_unknown_placing_is_refused(gcp_file: Path) -> None:
    with pytest.raises(ValueError):
        AssetPath(str(gcp_file), dataset_id="d", item_id="i", asset="vv", georeferencing="affine")  # type: ignore[arg-type]


# --- slices of a pass -------------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def slice_files(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    directory = tmp_path_factory.mktemp("pass")
    return mini_pass.build_slice(directory / "a.tif", 0), mini_pass.build_slice(directory / "b.tif", 1)


def slice_of(path: Path, item: dict) -> Slice:
    with rasterio.open(path) as dataset:
        grid = RadarGrid.of(dataset)
    first = line_time(item, mini_pass.FIRST_LINE)
    return Slice(item["id"], grid, first, line_time(item, mini_pass.LAST_LINE))


def test_two_slices_that_follow_each_other_join(slice_files: tuple[Path, Path]) -> None:
    a, b = slice_of(slice_files[0], mini_pass.item(0)), slice_of(slice_files[1], mini_pass.item(1))
    runs, reasons = join_slices([b, a])
    assert reasons == [] and len(runs) == 1
    joined = runs[0]
    assert [piece.item_id for piece in joined.slices] == ["slice-0", "slice-1"]
    assert joined.offsets == (0, mini_pass.HEIGHT)
    assert (joined.grid.width, joined.grid.height) == (mini_pass.WIDTH, 2 * mini_pass.HEIGHT)
    assert len(joined.grid.gcps) == len(a.grid.gcps) + len(b.grid.gcps)


def test_the_spline_of_a_joined_pass_closes_the_seam(slice_files: tuple[Path, Path]) -> None:
    a, b = slice_of(slice_files[0], mini_pass.item(0)), slice_of(slice_files[1], mini_pass.item(1))
    joined = join_slices([a, b])[0][0]
    cols = numpy.linspace(0, mini_pass.WIDTHS[1] - 1, 9)
    last = tps(joined.grid.gcps, numpy.full(cols.shape, mini_pass.HEIGHT - 0.5), cols + 0.5)
    first = tps(joined.grid.gcps, numpy.full(cols.shape, mini_pass.HEIGHT + 0.5), cols + 0.5)
    expected = numpy.array([mini_pass.position(mini_pass.HEIGHT + 0.5, col + 0.5) for col in cols])
    assert numpy.abs(first - expected).max() < 2 * mini_pass.STEP_LAT
    assert numpy.abs(first - last)[:, 1].max() < 2 * mini_pass.STEP_LAT


@pytest.mark.parametrize(
    ("gap_lines", "reason"),
    [
        (mini_pass.HEIGHT, "missing"),
        (-3, "overlap"),
    ],
)
def test_a_gap_or_an_overlap_splits_the_pass(slice_files: tuple[Path, Path], gap_lines: int, reason: str) -> None:
    a = slice_of(slice_files[0], mini_pass.item(0))
    b = slice_of(slice_files[1], mini_pass.item(1, gap_lines=gap_lines))
    runs, reasons = join_slices([a, b])
    assert len(runs) == 2 and len(reasons) == 1 and reason in reasons[0]


def test_a_slice_off_the_line_grid_does_not_join(slice_files: tuple[Path, Path]) -> None:
    a = slice_of(slice_files[0], mini_pass.item(0))
    b = slice_of(slice_files[1], mini_pass.item(1))
    late = dataclasses.replace(
        b,
        first_line=b.first_line + mini_pass.LINE_INTERVAL / 2,
        last_line=b.last_line + mini_pass.LINE_INTERVAL / 2,
    )
    runs, reasons = join_slices([a, late])
    assert len(runs) == 2 and "whole line" in reasons[0]


def test_slices_of_another_line_interval_do_not_join(slice_files: tuple[Path, Path]) -> None:
    a = slice_of(slice_files[0], mini_pass.item(0))
    b = slice_of(slice_files[1], mini_pass.item(1))
    stretched = dataclasses.replace(b, last_line=b.last_line + timedelta(milliseconds=5))
    _, reasons = join_slices([a, stretched])
    assert "interval" in reasons[0]


def test_columns_that_begin_elsewhere_do_not_join(tmp_path: Path, slice_files: tuple[Path, Path]) -> None:
    shifted = mini_pass.build_slice(tmp_path / "shifted.tif", 1, col_shift=6.0)
    a = slice_of(slice_files[0], mini_pass.item(0))
    b = slice_of(shifted, mini_pass.item(1))
    _, reasons = join_slices([a, b])
    assert reasons and "columns" in reasons[0]


def test_slices_in_different_gcp_crs_do_not_join(slice_files: tuple[Path, Path]) -> None:
    a = slice_of(slice_files[0], mini_pass.item(0))
    b = slice_of(slice_files[1], mini_pass.item(1))
    other = dataclasses.replace(b, grid=dataclasses.replace(b.grid, gcp_crs="EPSG:4258"))
    with pytest.raises(SlicesDoNotJoin):
        join_slices([a, other])


def test_no_slices_is_no_pass() -> None:
    with pytest.raises(SlicesDoNotJoin):
        join_slices([])


@pytest.mark.parametrize(
    "properties",
    [{}, {"start_datetime": 5}, {"start_datetime": "yesterday"}, {"start_datetime": "2026-10-26T05:34:34"}],
)
def test_a_slice_without_a_readable_time_does_not_join(properties: dict) -> None:
    with pytest.raises(SlicesDoNotJoin):
        line_time({"properties": properties}, "start_datetime")


def test_a_run_of_a_split_pass_the_region_misses_is_left_out(slice_files: tuple[Path, Path]) -> None:
    from shapely.geometry import shape

    a = slice_of(slice_files[0], mini_pass.item(0))
    b = slice_of(slice_files[1], mini_pass.item(1, gap_lines=mini_pass.HEIGHT))
    ring = [list(mini_pass.position(line, col)) for line, col in ((10, 10), (10, 50), (30, 50), (30, 10))]
    region = shape({"type": "Polygon", "coordinates": [[*ring, ring[0]]]})
    placed, reasons, missed = pass_runs([a, b], region)
    assert [joined.slices[0].item_id for joined, _ in placed] == ["slice-0"]
    assert missed == ["slice-1"] and "missing" in reasons[0]
