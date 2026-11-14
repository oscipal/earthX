"""A ``focal`` step through ``processing.run`` (M5-10, adr/0030 F3): the halo at the edge of every block, past the AOI,
at the edge of the raster and after a ``grid`` step, and the same result for every block size.

A synthetic model of heights in metres (``float32``, nodata −9999, 10 m in UTM 32N), served through the real `readers`.
The expected values are the kernel on the whole raster at once, which needs no block and no halo of the core.
"""

from __future__ import annotations

from pathlib import Path

import numpy
import pytest
import rasterio
from rasterio.crs import CRS
from rasterio.windows import Window
from rio_tiler.models import ImageData

from earthx.processing import core as core_module
from earthx.processing import run
from earthx.processing.core import _with_halo, area_statistics
from earthx.processing.errors import RecipeInvalid
from earthx.processing.operators import REGISTRY, TERRAIN, TerrainParams
from earthx.processing.plan import plan_steps, segments
from tests.earthx.processing import sources
from tests.earthx.processing.recipes import recipe_of_data

WIDTH, HEIGHT = 300, 260
NODATA = -9999.0
SLOPE = {"product": "slope", "bands": ["dem"], "name": "slope", "slope_unit": "degrees"}
HILLSHADE = {
    "product": "hillshade",
    "bands": ["dem"],
    "name": "shade",
    "azimuth": 315,
    "altitude": 45,
    "z_factor": 1,
    "multidirectional": False,
}


def _heights() -> numpy.ndarray:
    rows, cols = numpy.indices((HEIGHT, WIDTH), dtype="float64")
    heights = 900 + 40 * numpy.sin(cols / 17) * numpy.cos(rows / 23) + 0.8 * cols - 0.3 * rows
    heights[100:104, 150:160] = NODATA  # a gap inside
    return heights.astype("float32")


def _entry() -> dict:
    return {
        "asset": {
            "dataset_id": "synthetic",
            "item_id": "ITEM_A",
            "asset": "dem",
            "reader": "cog",
            "href": sources.url("dem"),
            "variable": None,
            "crs": sources.CRS,
        },
        "version": {"kind": "file:checksum", "value": "1220ITEM_Adem"},
        "bands": [{"data_type": "float32", "nodata": NODATA, "scale": None, "offset": None, "unit": "m"}],
        "scaling": "none",
        "gsd": 10.0,
    }


def _recipe(steps: list, aoi: dict | None = None, bands: list[str] | None = None) -> dict:
    return {
        "recipe_version": 2,
        "inputs": [
            {"name": "dem", "dataset": "synthetic", "groups": [["ITEM_A"]], "assets": ["dem"], "resolved": [_entry()]}
        ],
        "aoi": aoi or sources.whole(WIDTH, HEIGHT),
        "steps": steps,
        "output": {"kind": "raster", "format": "cog", "dtype": "float32", "bands": bands or ["slope"]},
    }


def _step(params: dict) -> dict:
    return {"op": "terrain", "op_version": 1, "params": params}


def _run(data: dict, workdir: Path):
    workdir.mkdir(parents=True, exist_ok=True)
    return run(recipe_of_data(data, REGISTRY), workdir=workdir, progress=lambda done, total: None, operators=REGISTRY)


def _read(path: Path) -> numpy.ma.MaskedArray:
    with rasterio.open(path) as dataset:
        return dataset.read(1, masked=True)


def _whole(params: dict) -> numpy.ma.MaskedArray:
    """The kernel once over the whole raster, with a masked ring around it: no block, no halo of the core."""
    heights = _heights().astype("float64")
    padded = numpy.pad(heights, 1, constant_values=NODATA)
    mask = padded == NODATA
    left, top = sources.ORIGIN_X - sources.RESOLUTION, sources.ORIGIN_Y + sources.RESOLUTION
    bounds = (left, top - (HEIGHT + 2) * sources.RESOLUTION, left + (WIDTH + 2) * sources.RESOLUTION, top)
    image = ImageData(
        numpy.ma.MaskedArray(padded[None].astype("float32"), mask=mask[None]),
        bounds=bounds,
        crs=CRS.from_string(sources.CRS),
        band_names=["dem"],
    )
    return TERRAIN.run(image, TerrainParams.model_validate(params, strict=True)).array[1]


@pytest.fixture(scope="module")
def dem(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("dem") / "dem.tif"
    return sources.build_band_cog(path, _heights(), scale=None, offset=None, nodata=NODATA)


@pytest.fixture
def served(dem: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sources.serve({sources.url("dem"): dem}, monkeypatch)


@pytest.mark.usefixtures("served")
class TestFocalRun:
    @pytest.mark.parametrize("params", [SLOPE, HILLSHADE], ids=["slope", "hillshade"])
    def test_the_job_is_the_kernel_over_the_whole_raster(self, tmp_path: Path, monkeypatch, params: dict) -> None:
        monkeypatch.setattr(core_module, "BLOCK_SIZE", 64)  # many block edges, none of them at the raster's
        result = _run(_recipe([_step(params)], bands=[params["name"]]), tmp_path)
        data, expected = _read(result.path), _whole(params)
        numpy.testing.assert_array_equal(numpy.ma.getmaskarray(data), numpy.ma.getmaskarray(expected))
        numpy.testing.assert_array_equal(data.compressed(), expected.compressed())
        assert result.meta.bands[0].unit == ("deg" if params is SLOPE else None)

    def test_every_block_size_gives_the_same_bytes(self, tmp_path: Path, monkeypatch) -> None:
        results = []
        for size in (1024, 48, 16):  # the work files take multiples of 16 only
            monkeypatch.setattr(core_module, "BLOCK_SIZE", size)
            results.append(_read(_run(_recipe([_step(SLOPE)]), tmp_path / str(size)).path))
        assert results[0].tobytes() == results[1].tobytes() == results[2].tobytes()
        assert numpy.ma.getmaskarray(results[0]).tobytes() == numpy.ma.getmaskarray(results[2]).tobytes()

    def test_the_edge_of_the_aoi_reads_its_neighbours_past_the_aoi(self, tmp_path: Path) -> None:
        left, top = sources.ORIGIN_X + 400.0, sources.ORIGIN_Y - 300.0
        aoi = sources.aoi_around(left + 2.5, top - 800 + 2.5, left + 1200 - 2.5, top - 2.5)
        data = _read(_run(_recipe([_step(SLOPE)], aoi=aoi), tmp_path).path)
        expected = _whole(SLOPE)[30:110, 40:160]
        assert data.shape == expected.shape and not numpy.ma.getmaskarray(data[0]).any()
        numpy.testing.assert_array_equal(data.filled(numpy.nan), expected.filled(numpy.nan))

    def test_the_edge_of_the_raster_and_the_gap_are_empty(self, tmp_path: Path) -> None:
        data = _read(_run(_recipe([_step(SLOPE)]), tmp_path).path)
        mask = numpy.ma.getmaskarray(data)
        assert mask[0].all() and mask[-1].all() and mask[:, 0].all() and mask[:, -1].all()
        assert mask[99:105, 149:161].all() and not mask[98, 148] and not mask[1:-1, 1:-1][:90].any()

    def test_a_pixel_step_before_it_runs_on_the_halo_too(self, tmp_path: Path) -> None:
        copy = {"op": "band_math", "op_version": 2, "params": {"expression": "dem", "name": "copy"}}
        data = _read(_run(_recipe([copy, _step({**SLOPE, "bands": ["copy"]})]), tmp_path / "copy").path)
        expected = _read(_run(_recipe([_step(SLOPE)]), tmp_path / "plain").path)
        assert data.tobytes() == expected.tobytes()
        assert numpy.ma.getmaskarray(data).tobytes() == numpy.ma.getmaskarray(expected).tobytes()

    def test_heights_changed_by_a_formula_are_no_longer_metres(self, tmp_path: Path) -> None:
        double = {"op": "band_math", "op_version": 2, "params": {"expression": "dem * 2", "name": "double"}}
        with pytest.raises(RecipeInvalid, match="heights in metres; double is in no unit"):
            _run(_recipe([double, _step({**SLOPE, "bands": ["double"]})]), tmp_path)
        assert list(tmp_path.iterdir()) == []

    def test_after_a_grid_step_the_ring_of_the_window_is_empty(self, tmp_path: Path) -> None:
        reproject = {
            "op": "reproject",
            "op_version": 4,
            "params": {"crs": sources.CRS, "resolution": 20.0, "resampling": "nearest", "align": True},
        }
        data = _read(_run(_recipe([reproject, _step(SLOPE)]), tmp_path).path)
        mask = numpy.ma.getmaskarray(data)
        assert mask[0].all() and mask[-1].all() and mask[:, 0].all() and mask[:, -1].all()
        assert not mask[1:-1, 1:-1][:40].any()

    def test_the_statistics_of_the_area_are_those_of_the_job(self, tmp_path: Path) -> None:
        recipe = recipe_of_data(_recipe([_step(SLOPE)]), REGISTRY)
        result = run(recipe, workdir=tmp_path, progress=lambda done, total: None, operators=REGISTRY)
        measured = area_statistics(recipe, operators=REGISTRY)
        assert measured.factor == 1
        assert [band["statistics"] for band in measured.bands] == [
            band["statistics"] for band in result.properties["bands"]
        ]

    def test_a_coarse_measure_of_the_area_reads_a_halo_as_well(self) -> None:
        recipe = recipe_of_data(_recipe([_step(SLOPE)]), REGISTRY)
        coarse = area_statistics(recipe, operators=REGISTRY, max_pixels=2000)
        assert coarse.factor > 1 and coarse.bands[0]["statistics"]["count"] > 0


def test_a_focal_step_stays_in_the_pass_of_the_pixel_steps() -> None:
    copy = {"op": "band_math", "op_version": 2, "params": {"expression": "dem", "name": "copy"}}
    planned = plan_steps(recipe_of_data(_recipe([copy, _step(SLOPE), _step(HILLSHADE)]), REGISTRY).steps, REGISTRY)
    passes = segments(planned)
    assert [(segment.kind, len(segment.steps), segment.halo) for segment in passes] == [("pixel", 3, 2)]


def test_the_halo_is_read_where_the_limits_allow_and_the_block_always() -> None:
    asked: list[Window] = []

    def read(window: Window) -> ImageData:
        asked.append(window)
        data = numpy.ma.MaskedArray(numpy.ones((1, int(window.height), int(window.width)), dtype="float32"))
        left, top = window.col_off, -window.row_off
        bounds = (left, top - window.height, left + window.width, top)
        return ImageData(data, bounds=bounds, crs=CRS.from_string(sources.CRS), band_names=["dem"])

    # The block sticks out past the limits (the last coarse column of a measure): it is read, only the halo is cut.
    image = _with_halo(read, Window(8, 0, 4, 4), 1, Window(0, 0, 10, 3))
    assert asked == [Window(7, 0, 5, 4)]
    assert image.array.shape == (1, 6, 6)
    mask = numpy.ma.getmaskarray(image.array[0])
    assert mask[0].all() and mask[:, -1].all() and not mask[1:-1, :-1].any()
    assert image.bounds == (7.0, -5.0, 13.0, 1.0)
