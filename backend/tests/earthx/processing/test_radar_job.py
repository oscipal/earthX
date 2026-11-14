"""A job over a dataset placed by GCPs stays in radar geometry (DS-04d): one scene or the joined slices of a pass, the
source's pixels in their own rows and columns, the GCPs shifted onto the window, no CRS; and the map shows the result
through the spline of its GCPs (A3). Synthetic slices (`mini_pass`), read through the real readers."""

from __future__ import annotations

import copy
import math
import warnings
from pathlib import Path
from typing import Any

import numpy
import pytest
import rasterio
from rasterio.errors import NotGeoreferencedWarning
from rio_tiler.constants import WEB_MERCATOR_TMS

from earthx.access.radar import gcp_key, item_line_times
from earthx.api.result_tiles import ResultPath, ResultReader, result_statistics
from earthx.processing import run
from earthx.processing.core import area_statistics
from earthx.processing.errors import AoiOutsideInputs, GridMismatch
from earthx.processing.recipe import recipe_from_data
from earthx.processing.source import Source
from earthx.processing.tile import OperatorTileReader
from earthx.readers.cog import AS_WRITTEN, AssetPath, CogReader
from tests.earthx.processing import sources
from tests.earthx.processing.recipes import recipe_data, resolved
from tests.earthx.processing.testops import OPERATORS
from tests.earthx.readers import mini_pass

ITEMS = ["slice-0", "slice-1"]


def area(line0: float, col0: float, line1: float, col1: float) -> dict[str, Any]:
    ring = [list(mini_pass.position(line, col)) for line, col in ((line0, col0), (line0, col1), (line1, col1), (line1, col0))]
    return {"type": "Polygon", "coordinates": [[*ring, ring[0]]]}


ACROSS = area(50, 10, 80, 50)


@pytest.fixture(scope="module")
def slices(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    directory = tmp_path_factory.mktemp("pass")
    return {name: mini_pass.build_slice(directory / f"{name}.tif", index) for index, name in enumerate(ITEMS)}


@pytest.fixture
def served(slices: dict[str, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    sources.serve({sources.url(name): path for name, path in slices.items()}, monkeypatch)


def recipe(
    group: list[str], aoi: dict[str, Any] = ACROSS, *, gap_lines: int = 0, times: bool = True, steps: list | None = None
) -> Any:
    entries = []
    for name in group:
        entry = resolved(name, "vv", scale=None, offset=None, href=sources.url(name))
        entry["asset"].update(crs=None, georeferencing="gcp_tps")
        entries.append(entry)
    line_times = {}
    for name in group:
        index = ITEMS.index(name)
        stac = mini_pass.item(index, gap_lines=gap_lines if index else 0, item_id=name)
        first, last = item_line_times(stac, mini_pass.FIRST_LINE, mini_pass.LAST_LINE)
        line_times[name] = {"first": first.isoformat(), "last": last.isoformat()}
    data = recipe_data(
        inputs=[
            {
                "name": "s1", "dataset": "synthetic", "groups": [list(group)], "assets": ["vv"], "resolved": entries,
                **({"line_times": line_times} if times else {}),
            }
        ],
        aoi=copy.deepcopy(aoi),
        steps=steps or [],
        output={"kind": "raster", "format": "cog", "dtype": "uint16" if not steps else "float32", "bands": ["vv"]},
    )  # fmt: skip
    return recipe_from_data(data, OPERATORS)


def lines_and_cols(path: Path) -> tuple[numpy.ndarray, numpy.ndarray]:
    with rasterio.open(path) as dataset:
        return numpy.vectorize(mini_pass.value_at)(dataset.read(1))


@pytest.mark.usefixtures("served")
def test_a_job_joins_the_slices_of_a_pass_in_radar_geometry(tmp_path: Path) -> None:
    result = run(recipe(ITEMS), workdir=tmp_path, progress=lambda *_: None, operators=OPERATORS)
    with rasterio.open(result.path) as out, rasterio.open(result.mask_path) as mask:
        assert out.crs is None and out.transform.is_identity
        assert gcp_key(out) == gcp_key(mask)
        assert len(out.gcps[0]) == 2 * len(mini_pass.gcps(0, mini_pass.WIDTHS[0]))
        assert mask.read(1).any()
    lines, cols = lines_and_cols(result.path)
    # One row of the result is one line of the pass, across the seam: nothing warped, nothing flipped.
    assert (numpy.diff(lines, axis=0) == 1).all() and (numpy.diff(cols, axis=1) == 1).all()
    assert lines.min() < mini_pass.HEIGHT <= lines.max()
    assert result.properties["earthx:georeferencing"] == "gcp_tps"
    assert "proj:code" not in result.properties and "gsd" not in result.properties
    assert result.properties["processing:lineage"].startswith("mosaic of 2 scenes")


@pytest.mark.usefixtures("served")
def test_two_runs_of_a_pass_give_the_same_bytes(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    first = run(recipe(ITEMS), workdir=tmp_path / "a", progress=lambda *_: None, operators=OPERATORS)
    second = run(recipe(ITEMS), workdir=tmp_path / "b", progress=lambda *_: None, operators=OPERATORS)
    assert Path(first.path).read_bytes() == Path(second.path).read_bytes()


@pytest.mark.usefixtures("served")
@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"gap_lines": mini_pass.HEIGHT}, "missing"),
        ({"gap_lines": -2}, "overlap"),
        ({"times": False}, "no times"),
    ],
    ids=["a missing slice", "an overlap", "no line times"],
)
def test_slices_that_do_not_join_fail_the_job_with_the_reason(tmp_path: Path, changes: dict, reason: str) -> None:
    with pytest.raises(GridMismatch, match=reason):
        run(recipe(ITEMS, **changes), workdir=tmp_path, progress=lambda *_: None, operators=OPERATORS)
    assert not any(tmp_path.iterdir())


@pytest.mark.usefixtures("served")
def test_an_aoi_beside_the_scene_fails_the_job(tmp_path: Path) -> None:
    with pytest.raises(AoiOutsideInputs):
        run(recipe(["slice-0"], area(400, 400, 420, 420)), workdir=tmp_path, progress=lambda *_: None, operators=OPERATORS)


@pytest.mark.usefixtures("served")
def test_a_pixel_step_runs_on_the_radar_grid(tmp_path: Path) -> None:
    steps = [{"op": "scale", "op_version": 1, "params": {"factor": 2.0}}]
    plain = run(recipe(ITEMS), workdir=tmp_path, progress=lambda *_: None, operators=OPERATORS)
    (tmp_path / "scaled").mkdir()
    scaled = run(recipe(ITEMS, steps=steps), workdir=tmp_path / "scaled", progress=lambda *_: None, operators=OPERATORS)
    with rasterio.open(plain.path) as a, rasterio.open(scaled.path) as b:
        assert b.crs is None and gcp_key(a) == gcp_key(b)
        values, doubled = a.read(1).astype("float64"), b.read(1).astype("float64")
    valid = values != mini_pass.NODATA
    assert numpy.allclose(doubled[valid], 2 * values[valid])


@pytest.mark.usefixtures("served")
@pytest.mark.parametrize("max_pixels", [1_000_000, 200], ids=["on the job's grid", "on a coarser grid"])
def test_the_statistics_of_the_area_are_read_in_radar_geometry(tmp_path: Path, max_pixels: int) -> None:
    measured = area_statistics(recipe(ITEMS), operators=OPERATORS, max_pixels=max_pixels)
    (band,) = measured.bands
    lines_min = (band["statistics"]["minimum"] - 1) // mini_pass.WIDTH
    lines_max = (band["statistics"]["maximum"] - 1) // mini_pass.WIDTH
    assert lines_min < mini_pass.HEIGHT <= lines_max
    if max_pixels > 200:
        result = run(recipe(ITEMS), workdir=tmp_path, progress=lambda *_: None, operators=OPERATORS)
        assert measured.factor == 1
        assert band["statistics"] == result.properties["bands"][0]["statistics"]
    else:
        assert measured.factor > 1


@pytest.mark.usefixtures("served")
def test_the_map_shows_a_radar_result_through_its_spline(tmp_path: Path) -> None:
    result = run(recipe(ITEMS), workdir=tmp_path, progress=lambda *_: None, operators=OPERATORS)
    mask = AssetPath(str(result.mask_path), dataset_id="", item_id="", asset="mask.tif", georeferencing=AS_WRITTEN)
    path = ResultPath(str(result.path), mask=mask)
    lon, lat = mini_pass.position(mini_pass.HEIGHT, 30)
    tile = WEB_MERCATOR_TMS.tile(lon, lat, 16)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", NotGeoreferencedWarning)
        with ResultReader(path) as reader:
            assert reader.dataset.crs is not None
            image = reader.tile(tile.x, tile.y, tile.z, indexes=(1,))
        statistics = result_statistics(path, {})
    assert (~numpy.ma.getmaskarray(image.array)).any()
    assert statistics[0]["statistics"]["count"] > 0


class _Inputs:
    """What `api` hands a tile reader: the assets and no steps."""

    def __init__(self, inputs: tuple) -> None:
        self.inputs = inputs
        self.steps = ()
        self.bands = None


def test_a_tile_with_an_operator_still_reads_through_the_spline(slices: dict[str, Path]) -> None:
    entry = recipe(["slice-0"]).inputs[0].resolved[0]
    path = AssetPath(str(slices["slice-0"]), dataset_id="synthetic", item_id="slice-0", asset="vv", georeferencing="gcp_tps")
    lon, lat = mini_pass.position(mini_pass.HEIGHT / 2, 40)
    tile = WEB_MERCATOR_TMS.tile(lon, lat, 16)
    with OperatorTileReader(_Inputs(((entry, path),))) as reader:
        image = reader.tile(tile.x, tile.y, tile.z)
        preview = reader.preview(max_size=32)
    assert (~numpy.ma.getmaskarray(image.array)).any()
    assert preview.width <= 32 and (~numpy.ma.getmaskarray(preview.array)).any()


def test_a_scene_without_nodata_keeps_its_one_band(tmp_path: Path) -> None:
    with rasterio.open(mini_pass.build_slice(tmp_path / "a.tif", 0)) as source:
        profile, data = source.profile, source.read()
        gcps = source.gcps
    profile.pop("nodata")
    plain = tmp_path / "plain.tif"
    with rasterio.open(plain, "w", **{**profile, "gcps": gcps[0], "crs": gcps[1]}) as dst:
        dst.write(data)
    entry = recipe(["slice-0"]).inputs[0].resolved[0]
    path = AssetPath(str(plain), dataset_id="synthetic", item_id="slice-0", asset="vv", georeferencing="gcp_tps")
    from contextlib import ExitStack

    with ExitStack() as stack:
        source = Source.open(entry, path, stack)
        assert isinstance(source.reader, CogReader) and source.reader.dataset.count == 2  # the warp adds alpha
        assert source.names == ["vv"] and source.nodata == [None]


# --- Otto's check of step 6 (14.11.2026): two slices of a pass, Normalize, AOI only, through the intake ------------

NORMALIZE = {
    "op": "normalize",
    "op_version": 4,
    "params": {"method": "linear", "bands": ["vv"], "in_min": 0.0, "in_max": 1000.0, "out_min": 0.0, "out_max": 1.0, "clip": True},
}


def _stac(index: int, gap_lines: int = 0) -> dict[str, Any]:
    from tests.earthx.api.test_download_radar import footprint

    stac = mini_pass.item(index, gap_lines=gap_lines)
    name = stac["id"]
    stac["geometry"] = footprint(index)
    lons, lats = zip(*stac["geometry"]["coordinates"][0], strict=True)
    stac["bbox"] = [min(lons), min(lats), max(lons), max(lats)]
    stac["properties"].update({"gsd": 10.0, "s1:datatake_id": "40282"})
    stac["assets"] = {
        "vv": {
            "href": sources.url(name),
            "type": "image/tiff; application=geotiff",
            "file:checksum": f"1220{name}",
            "raster:bands": [{"data_type": "uint16", "nodata": 0}],
        }
    }
    return stac


def _accepted(gap_lines: int = 0) -> Any:
    import asyncio
    from dataclasses import replace

    from earthx.catalog.registry import DatasetRegistry
    from earthx.processing.operators import REGISTRY
    from tests.earthx.api.test_download_radar import RADAR
    from tests.earthx.api.test_intake import Source, accept

    # A pass as Sentinel-1 names it: the day and the datatake (`sentinel-1-grd.yaml`, `viewer.group_by`).
    take = ("datetime", "s1:datatake_id")
    config = replace(
        RADAR,
        source=replace(RADAR.source, asset_hosts=(sources.HOST,)),
        viewer=replace(RADAR.viewer, group_by=take, results_group_by=take),
    )
    order = {
        "recipe_version": 2,
        "inputs": [{"name": "s1", "dataset": config.dataset_id, "groups": [ITEMS]}],
        "aoi": ACROSS,
        "steps": [NORMALIZE],
        "output": {"kind": "raster", "format": "cog", "dtype": "float32", "bands": ["vv"]},
    }
    items = Source((config, _stac(0)), (config, _stac(1, gap_lines)))
    return asyncio.run(accept(order, items, registry=DatasetRegistry((config,)), operators=REGISTRY)).recipe


@pytest.mark.usefixtures("served")
def test_two_slices_of_a_pass_normalized_over_an_aoi_run_in_radar_geometry(tmp_path: Path) -> None:
    from earthx.processing.operators import REGISTRY

    recipe = _accepted()
    entry = recipe.inputs[0]
    assert entry.groups == [ITEMS] and entry.line_times is not None
    assert {item.asset.georeferencing for item in entry.resolved} == {"gcp_tps"}
    result = run(recipe, workdir=tmp_path, progress=lambda *_: None, operators=REGISTRY)
    with rasterio.open(result.path) as out:
        assert out.crs is None and out.gcps[0] and out.dtypes[0] == "float32"
        values = out.read(1, masked=True)
    assert 0.0 <= float(values.min()) and float(values.max()) <= 1.0
    assert result.properties["processing:lineage"].startswith("mosaic of 2 scenes")


@pytest.mark.usefixtures("served")
@pytest.mark.parametrize(
    ("gap_lines", "kind"),
    [(mini_pass.HEIGHT, "pass_slice_missing"), (-mini_pass.HEIGHT // 2, "pass_slices_overlap")],
)
def test_slices_of_a_pass_that_do_not_join_say_why(tmp_path: Path, gap_lines: int, kind: str) -> None:
    from earthx.api.processing_route import _FAILURES
    from earthx.processing import failure_kind
    from earthx.processing.operators import REGISTRY

    with pytest.raises(GridMismatch) as error:
        run(_accepted(gap_lines), workdir=tmp_path, progress=lambda *_: None, operators=REGISTRY)
    assert failure_kind(error.value) == kind
    status, title = _FAILURES[kind]
    assert status == 422 and "grid" not in title and "scene" in title


# --- Otto's check of step 7 (14.11.2026): the result lies pixel on pixel on its scenes, and keeps to the AOI -------

TRIANGLE = {
    "type": "Polygon",
    "coordinates": [[list(mini_pass.position(*corner)) for corner in ((40, 5), (40, 70), (90, 5), (40, 5))]],
}


def _scene_tile(slices: dict[str, Path], names: list[str], tile: Any) -> numpy.ndarray:
    """The tile of the scenes as the map draws them: each by its own spline, the first scene of the pass first."""
    mosaic = None
    for name in names:
        path = AssetPath(str(slices[name]), dataset_id="d", item_id=name, asset="vv", georeferencing="gcp_tps")
        with CogReader(path) as reader:
            image = reader.tile(tile.x, tile.y, tile.z, indexes=(1,), resampling_method="nearest")
        values = numpy.where(numpy.ma.getmaskarray(image.array[0]), 0, numpy.ma.getdata(image.array[0])).astype(int)
        mosaic = values if mosaic is None else numpy.where(mosaic > 0, mosaic, values)
    assert mosaic is not None
    return mosaic


def _result_tile(result: Any, tile: Any) -> numpy.ma.MaskedArray:
    mask = AssetPath(str(result.mask_path), dataset_id="", item_id="", asset="mask.tif", georeferencing=AS_WRITTEN)
    with ResultReader(ResultPath(str(result.path), mask=mask)) as reader:
        return reader.tile(tile.x, tile.y, tile.z, indexes=(1,), resampling_method="nearest").array[0]


@pytest.mark.usefixtures("served")
@pytest.mark.parametrize(
    ("names", "aoi", "line", "col"),
    [(["slice-0"], area(10, 10, 50, 60), 30, 35), (ITEMS, TRIANGLE, mini_pass.HEIGHT, 30)],
    ids=["one scene", "two slices, at the seam"],
)
@pytest.mark.parametrize("zoom", [15, 16, 17, 18])
def test_a_radar_result_lies_pixel_on_pixel_on_its_scenes(
    tmp_path: Path, slices: dict[str, Path], names: list[str], aoi: dict, line: int, col: int, zoom: int
) -> None:
    """Otto, 14.11.2026: drawn slice by slice as its scenes, every pixel of the result on its source pixel. A pixel
    step changes values only; the result of ``scale`` 2 is twice the source pixel it lies on, or it lies wrong."""
    from earthx.readers.radar_slices import SLICES_TAG

    steps = [{"op": "scale", "op_version": 1, "params": {"factor": 2.0}}]
    result = run(recipe(names, aoi, steps=steps), workdir=tmp_path, progress=lambda *_: None, operators=OPERATORS)
    with rasterio.open(result.path) as out, rasterio.open(result.mask_path) as mask:
        assert SLICES_TAG in out.tags() and SLICES_TAG in mask.tags()
    lon, lat = mini_pass.position(line, col)
    tile = WEB_MERCATOR_TMS.tile(lon, lat, zoom)
    scenes = _scene_tile(slices, names, tile)
    drawn = _result_tile(result, tile)
    shown = ~numpy.ma.getmaskarray(drawn)
    assert shown.any()
    # Nothing drawn where no scene is, and every drawn pixel twice the value of the scene pixel under it.
    assert (scenes[shown] > 0).all()
    assert (numpy.ma.getdata(drawn)[shown] == 2 * scenes[shown]).all()


@pytest.mark.usefixtures("served")
def test_a_radar_result_keeps_to_the_aoi_on_the_map(tmp_path: Path, slices: dict[str, Path]) -> None:
    """As every result: the map shows the pixels ``mask.tif`` marks (all touched). Drawn pixel on pixel, what shows
    outside the AOI lies within one pixel of its edge, and what lies more than two pixels inside it shows where the
    scenes show."""
    from rasterio.warp import transform
    from shapely.geometry import Point, shape

    result = run(recipe(ITEMS, TRIANGLE), workdir=tmp_path, progress=lambda *_: None, operators=OPERATORS)
    aoi = shape(TRIANGLE)
    lon, lat = mini_pass.position(65, 30)
    tile = WEB_MERCATOR_TMS.tile(lon, lat, 17)
    # The diagonal of the largest pixel of the fixture (its bend stretches some by up to a tenth), plus the pixel of the
    # tile at which the map samples it.
    largest = max(
        math.dist(mini_pass.position(row, col), mini_pass.position(row + 1, col + 1))
        for row in range(2 * mini_pass.HEIGHT)
        for col in range(mini_pass.WIDTH)
    )
    pixel = largest + (WEB_MERCATOR_TMS.bounds(tile).right - WEB_MERCATOR_TMS.bounds(tile).left) / 256
    shown = ~numpy.ma.getmaskarray(_result_tile(result, tile))
    bounds = WEB_MERCATOR_TMS.xy_bounds(tile)
    size = shown.shape[0]
    xs = bounds.left + (numpy.arange(size) + 0.5) * (bounds.right - bounds.left) / size
    ys = bounds.top - (numpy.arange(size) + 0.5) * (bounds.top - bounds.bottom) / size
    lons, lats = transform("EPSG:3857", "EPSG:4326", *(axis.ravel() for axis in numpy.meshgrid(xs, ys)))
    points = [Point(x, y) for x, y in zip(lons, lats, strict=True)]
    outside = numpy.array([aoi.distance(point) for point in points]).reshape(shown.shape)
    inside = numpy.array([aoi.exterior.distance(point) if aoi.contains(point) else 0.0 for point in points])
    assert outside[shown].max() <= pixel
    # Where the scenes show (the splines of two slices need not meet at the seam, for scenes and result alike).
    scenes = _scene_tile(slices, ITEMS, tile).ravel() > 0
    assert shown.ravel()[(inside > 2 * pixel) & scenes].all()
