"""``normalize`` version 4 over an area the preview cannot read at the job's resolution (NM4-71).

The route of NM4-19 reads at most 2048² pixels; over a larger window it reads a coarser grid and reports ``factor`` above 1.
A job is exact whatever the size. The scene here is 2600 × 1900 (4.9 million pixels, 2.4 times the limit) with a diamond as
the AOI, three bands of ``uint16`` raw values with Sentinel-2's scale, so that the physical values are ``float32`` with many
equal values in every bin of the histogram. The numbers a run reports are held against numpy over the pixels of the mask.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy
import pytest

from earthx.processing import core
from earthx.processing.operators import REGISTRY
from earthx.processing.recipe import recipe_from_data
from earthx.processing.statistics import MEASURE_PERCENTILES
from tests.earthx.processing import sources
from tests.earthx.processing.test_normalize_exact import (
    PERCENTILE,
    ROBUST,
    ZSCORE,
    _with,
    assert_numbers,
    diamond,
    do_run,
    expected_numbers,
    pixels_before,
    recipe,
    sha,
    step,
)

WIDTH, HEIGHT = 2600, 1900
ASSETS = ("red", "nir", "blue")


def _raw(seed: int, centre: float, spread: float) -> numpy.ndarray:
    """A smooth field with noise as ``uint16`` raw values: a few thousand levels, each held by about 1600 pixels."""
    rows, cols = numpy.indices((HEIGHT, WIDTH))
    field = centre + 600 * numpy.sin(rows / 300) + 400 * numpy.cos(cols / 250)
    field += numpy.random.default_rng(seed).normal(0, spread, (HEIGHT, WIDTH))
    raw = numpy.clip(field, 1, 60000).astype("uint16")
    raw[:8, :8] = sources.NODATA
    return raw


class Measures:
    """Everything the tests below read, made once: the runs are the cost."""

    def __init__(self, root: Path, patch: pytest.MonkeyPatch) -> None:
        built = {
            name: sources.build_band_cog(root / f"{name}.tif", _raw(seed, centre, spread))
            for name, seed, centre, spread in (("red", 1, 2500, 300), ("nir", 2, 4200, 500), ("blue", 3, 1500, 200))
        }
        sources.serve({sources.url(name): path for name, path in built.items()}, patch)
        self.aoi = diamond(WIDTH, HEIGHT, inset=40)
        self.three = recipe(
            [
                step(_with(PERCENTILE, bands=["red"])),
                step(_with(ZSCORE, bands=["nir"])),
                step(_with(ROBUST, bands=["blue"])),
            ],
            list(ASSETS),
            assets=ASSETS,
            aoi=self.aoi,
            size=(WIDTH, HEIGHT),
        )
        self.result = do_run(self.three, root / "three")
        self.pixels = pixels_before(self.three, [], list(ASSETS), root / "before")
        # One stretch alone, for the counter-sample: the preview's numbers in version 3 against the job's exact ones.
        self.alone = recipe([step(_with(PERCENTILE, bands=["red"]))], ["red"], assets=("red",), aoi=self.aoi)
        self.exact = do_run(self.alone, root / "alone")
        self.route = core.area_statistics(
            recipe_from_data(
                {**self.alone, "steps": [], "output": {**self.alone["output"], "dtype": "float64"}}, REGISTRY
            ),
            extra_percentiles=MEASURE_PERCENTILES,
        )
        statistics = self.route.bands[0]["statistics"]
        route_numbers = {"p_low": statistics["percentile_2"], "p_high": statistics["percentile_98"]}
        self.preview = do_run(self._version_3(route_numbers, self.route.factor), root / "preview")
        reported = self.exact.properties["earthx:normalize"][0]["bands"]["red"]
        self.third = do_run(self._version_3(reported, 1), root / "third")
        self.route_numbers = route_numbers

    def _version_3(self, numbers: dict[str, float], factor: int) -> dict[str, Any]:
        params = {**_with(PERCENTILE, bands=["red"]), "measured": {"factor": factor, "bands": {"red": numbers}}}
        return recipe([step(params, 3)], ["red"], assets=("red",), aoi=self.aoi)


@pytest.fixture(scope="module")
def measures(tmp_path_factory: pytest.TempPathFactory) -> Measures:
    with pytest.MonkeyPatch.context() as patch:
        yield Measures(tmp_path_factory.mktemp("normalize-large"), patch)


class TestAJobOverMoreThanTheLimitOfTheRoute:
    def test_the_window_is_larger_than_what_the_route_reads_at_the_jobs_resolution(self, measures: Measures) -> None:
        assert measures.result.meta.width * measures.result.meta.height > core.MAX_AREA_PIXELS
        assert measures.route.factor > 1 and measures.route.exact is False
        assert 0 < measures.pixels["red"].size < measures.result.meta.width * measures.result.meta.height

    def test_every_number_is_that_of_numpy_over_the_pixels_of_the_mask(self, measures: Measures) -> None:
        percentile, zscore, robust = measures.result.properties["earthx:normalize"]
        assert [(entry["step"], entry["method"], entry["exact"]) for entry in (percentile, zscore, robust)] == [
            (0, "percentile", True),
            (1, "zscore", True),
            (2, "robust", True),
        ]
        red, nir, blue = (measures.pixels[name] for name in ASSETS)
        assert_numbers(percentile["bands"]["red"], expected_numbers(red, "percentile", PERCENTILE))
        assert_numbers(robust["bands"]["blue"], expected_numbers(blue, "robust", ROBUST), float64_only=False)
        assert zscore["bands"]["nir"]["mean"] == pytest.approx(math.fsum(nir) / nir.size, rel=1e-14)
        assert zscore["bands"]["nir"]["stddev"] == pytest.approx(float(nir.std()), rel=1e-9)
        for percent, key in ((2, "p_low"), (98, "p_high")):
            assert percentile["bands"]["red"][key] == float(numpy.percentile(red, percent, method="inverted_cdf"))
        for percent, key in ((25, "p25"), (50, "median"), (75, "p75")):
            assert robust["bands"]["blue"][key] == float(numpy.percentile(blue, percent, method="inverted_cdf"))

    def test_many_pixels_hold_the_same_value_so_a_bin_of_the_histogram_holds_many_equal_ones(
        self, measures: Measures
    ) -> None:
        red = measures.pixels["red"]
        levels = numpy.unique(red)
        assert red.size / levels.size > 500
        exact = measures.result.properties["earthx:normalize"][0]["bands"]["red"]
        assert exact["p_low"] in levels and exact["p_high"] in levels

    def test_the_preview_numbers_in_version_3_give_other_bytes_than_the_exact_job(self, measures: Measures) -> None:
        """The counter-sample: it is the change of this task that the preview's numbers are not the job's."""
        exact = measures.exact.properties["earthx:normalize"][0]["bands"]["red"]
        assert measures.route_numbers != exact
        assert sha(measures.preview.path) != sha(measures.exact.path)

    def test_version_3_with_the_exact_numbers_gives_the_bytes_of_the_job(self, measures: Measures) -> None:
        assert sha(measures.third.path) == sha(measures.exact.path)
        assert sha(measures.third.mask_path) == sha(measures.exact.mask_path)

    def test_the_stretch_puts_the_two_percentiles_on_the_ends(self, measures: Measures) -> None:
        import rasterio

        with rasterio.open(measures.exact.path) as file, rasterio.open(measures.exact.mask_path) as mask:
            out, inside = file.read(1), mask.read(1) == 1
        values = out[inside & numpy.isfinite(out)]
        assert (values == 0.0).mean() >= 0.02 and (values == 1.0).mean() >= 0.02
