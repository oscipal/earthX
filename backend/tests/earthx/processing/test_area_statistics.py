"""The statistics of the area without a run (NM4-19): the same numbers as the result's, or a coarser read of them.

``area_statistics`` reads and counts as ``run`` does but writes nothing. On the job's own grid its
``statistics`` are those of the result's properties, field for field; above ``max_pixels`` it reads a grid
``factor`` times coarser. The scenes are those of M4-32 (one scene, an AOI whose box holds other values) and
M4-12a (a mosaic over two UTM zones), served through the real `readers`.
"""

from __future__ import annotations

from pathlib import Path

import numpy
import pytest

from earthx.processing import run
from earthx.processing.core import MAX_AREA_PIXELS, area_factor, area_statistics
from earthx.processing.errors import AoiOutsideInputs, UnsupportedRecipe
from tests.earthx.processing import sources
from tests.earthx.processing import test_core_statistics as single
from tests.earthx.processing import test_mosaic as mosaic
from tests.earthx.processing.recipes import crop_data, recipe_of_data
from tests.earthx.processing.test_mosaic import scenes, served  # noqa: F401  (fixtures)
from tests.earthx.processing.testops import OPERATORS


def _run(data: dict, workdir: Path):
    workdir.mkdir(exist_ok=True)
    return run(recipe_of_data(data, OPERATORS), workdir=workdir, progress=lambda done, total: None, operators=OPERATORS)


def _measure(data: dict, **options):
    return area_statistics(recipe_of_data(data, OPERATORS), operators=OPERATORS, **options)


def _statistics_of(result) -> list[dict]:
    return [band["statistics"] for band in result.properties["bands"]]


@pytest.fixture
def band(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> numpy.ndarray:
    """The scene of M4-32: a ramp of small values, high ones in the two corners of the triangle's box."""
    raw = sources.ramp(single.SIZE, single.SIZE, 1200) % 4000 + 1
    raw[100:200, 100:150] = single.CORNER
    raw[100:200, 550:600] = single.CORNER
    path = sources.build_band_cog(tmp_path / "band.tif", raw)
    sources.serve({sources.url("band"): path}, monkeypatch)
    return raw


@pytest.mark.usefixtures("band")
class TestOnTheJobsGrid:
    def test_the_statistics_are_those_of_the_result(self, tmp_path: Path) -> None:
        data = single._recipe(single._triangle())
        measured = _measure(data)
        assert measured.exact and measured.factor == 1
        assert [band["statistics"] for band in measured.bands] == _statistics_of(_run(data, tmp_path / "work"))

    def test_the_corners_outside_the_area_do_not_count(self) -> None:
        measured = _measure(single._recipe(single._triangle()))
        corner = (single.CORNER * sources.SCALE + sources.OFFSET) * 2.0
        assert measured.bands[0]["statistics"]["maximum"] < corner / 5

    @pytest.mark.parametrize("dtype", ["uint16", "int16", "float64"])
    def test_the_output_type_is_cast_as_the_job_casts_it(self, tmp_path: Path, dtype: str) -> None:
        data = single._recipe(single._triangle(), dtype=dtype, step={"op": "scale", "op_version": 1, "params": {"factor": 3000.0}})
        assert [band["statistics"] for band in _measure(data).bands] == _statistics_of(_run(data, tmp_path / "work"))

    def test_the_bands_are_named_as_in_the_result(self, tmp_path: Path) -> None:
        data = single._recipe(single._triangle())
        result = _run(data, tmp_path / "work")
        assert [band["name"] for band in _measure(data).bands] == [band["name"] for band in result.properties["bands"]]

    def test_the_window_at_the_limit_is_still_exact(self, tmp_path: Path) -> None:
        data = single._recipe(single._triangle())
        pixels = 500 * 500  # the triangle's box: raster rows and columns 100–600
        assert _measure(data, max_pixels=pixels).exact
        assert not _measure(data, max_pixels=pixels - 1).exact


@pytest.mark.usefixtures("band")
class TestAboveTheLimit:
    def test_a_coarser_grid_is_read(self) -> None:
        measured = _measure(single._recipe(single._triangle()), max_pixels=10_000)
        assert not measured.exact
        assert measured.factor == 5
        assert measured.pixels_read <= 10_000

    def test_the_coarser_values_lie_near_those_of_the_area(self, tmp_path: Path) -> None:
        data = single._recipe(single._triangle())
        exact = _statistics_of(_run(data, tmp_path / "work"))[0]
        coarse = _measure(data, max_pixels=10_000).bands[0]["statistics"]
        assert 0 < coarse["count"] < exact["count"]
        for name in ("percentile_2", "percentile_98", "mean"):
            assert coarse[name] == pytest.approx(exact[name], rel=0.05)


@pytest.mark.usefixtures("served")
class TestAMosaic:
    def test_the_statistics_are_those_of_the_mosaic_job(self, tmp_path: Path) -> None:
        data = mosaic._recipe(["A", "B", "C"], steps=[mosaic.SCALE_2])
        measured = _measure(data)
        assert measured.exact
        assert [band["statistics"] for band in measured.bands] == _statistics_of(mosaic._run(data, tmp_path))

    def test_the_order_of_the_scenes_is_the_jobs(self, tmp_path: Path) -> None:
        data = mosaic._recipe(["B", "A"], steps=[mosaic.SCALE_2])
        assert [band["statistics"] for band in _measure(data).bands] == _statistics_of(mosaic._run(data, tmp_path))

    def test_a_coarser_mosaic_still_reads_every_scene(self) -> None:
        coarse = _measure(mosaic._recipe(["A", "B", "C"], steps=[mosaic.SCALE_2]), max_pixels=2_000)
        assert not coarse.exact and coarse.bands[0]["statistics"]["count"] > 0


@pytest.mark.usefixtures("band")
class TestWhatIsNotMeasured:
    def test_a_grid_step_is_refused(self) -> None:
        data = single._recipe(single._triangle(), step={"op": "coarsen", "op_version": 1, "params": {"factor": 2}})
        with pytest.raises(UnsupportedRecipe, match="pixel steps only"):
            _measure(data)

    def test_an_export_is_refused(self) -> None:
        with pytest.raises(UnsupportedRecipe, match="export"):
            _measure(crop_data())

    def test_an_area_outside_the_scene_is_refused(self) -> None:
        far = sources.aoi_around(sources.ORIGIN_X + 50_000, sources.ORIGIN_Y - 60_000, sources.ORIGIN_X + 51_000, sources.ORIGIN_Y - 59_000)
        with pytest.raises(AoiOutsideInputs):
            _measure(single._recipe(far))


class TestTheFactor:
    @pytest.mark.parametrize(
        ("width", "height", "factor"),
        [(1, 1, 1), (2048, 2048, 1), (2049, 2048, 2), (4096, 4096, 2), (4097, 4096, 3), (10980, 10980, 6)],
    )
    def test_the_smallest_factor_that_fits(self, width: int, height: int, factor: int) -> None:
        assert area_factor(width, height) == factor
        assert -(-width // factor) * -(-height // factor) <= MAX_AREA_PIXELS

    def test_a_long_thin_window(self) -> None:
        assert area_factor(100_000, 3) == 1
        assert area_factor(10_000_000, 1) == 3

    @pytest.mark.parametrize("max_pixels", [0, -1])
    def test_no_pixel_is_no_limit(self, max_pixels: int) -> None:
        with pytest.raises(ValueError, match="at least 1"):
            area_factor(10, 10, max_pixels)
