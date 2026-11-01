"""The planner and the cost of a step that measures (NM4-71): where the chain is cut, what the cut costs, what it needs.

``segments`` ends a ``pixel`` run before a step with a non-empty ``Operator.measures``, after the planner's selections and
narrowing; the pass before it counts the bands. ``estimate`` adds the time of the extra pass, and the work file of the count is
the ``float64`` pass that ``disk_needed`` already plans for.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy
import pytest
from rasterio.transform import from_origin

from earthx.processing.operators import REGISTRY, BandMeta, RasterMeta
from earthx.processing.plan import (
    DISK_RESERVE_BYTES,
    MEMORY_BYTES_PER_MEASURED_BAND,
    SECONDS_PER_MEASURE_BAND_MPIXEL,
    disk_needed,
    estimate,
    memory_needed,
    plan_steps,
    segments,
    stock_steps,
)
from earthx.processing.recipe import Step, recipe_from_data
from tests.earthx.processing import sources
from tests.earthx.processing.test_normalize_exact import (
    LINEAR,
    PERCENTILE,
    ZSCORE,
    _with,
    do_run,
    recipe,
    step,
)

NAMES = ("red", "nir", "green", "scl")


def _meta(names: tuple[str, ...] = NAMES) -> RasterMeta:
    bands = tuple(BandMeta(name, "float32", float("nan")) for name in names)
    return RasterMeta("EPSG:32632", from_origin(0, 100, 10, 10), 10, 10, bands)


def _step(op: str, version: int, **params) -> Step:
    return Step(op=op, op_version=version, params=params)


def _normalize(method: str, *bands: str, version: int = 4, **more) -> Step:
    params = {
        "zscore": {},
        "robust": {},
        "percentile": {"low": 2, "high": 98, "out_min": 0.0, "out_max": 1.0, "clip": True},
    }
    return _step("normalize", version, method=method, bands=list(bands), **params.get(method, {}), **more)


LINEAR_STEP = _step("normalize", 4, **{k: v for k, v in LINEAR.items() if k != "bands"}, bands=["red"])
NDVI = _step("band_math", 2, expression="(nir - red) / (nir + red)", name="NDVI")
MASK = _step("mask", 2, source="scl", classes=[3, 8])
REPROJECT = _step("reproject", 4, crs="EPSG:3035", resolution=20.0, resampling="nearest", align=False)


def _passes(steps: list[Step], output: list[str]) -> list[tuple[str, list[str]]]:
    """The passes of a chain, the planner's own selections of bands left out of the lists (they are in the pass they precede)."""
    chain = stock_steps(_meta(), plan_steps(steps, REGISTRY), output)
    return [
        (segment.kind, [s.step.op for s in segment.steps if s.step.op != "select_bands"]) for segment in segments(chain)
    ]


class TestWhereTheChainIsCut:
    def test_a_chain_that_measures_nothing_is_cut_as_before(self) -> None:
        assert _passes([NDVI, LINEAR_STEP, MASK], ["NDVI", "red"]) == [("pixel", ["band_math", "normalize", "mask"])]
        assert _passes([REPROJECT, NDVI], ["NDVI"]) == [
            ("pixel", []),
            ("grid", ["reproject"]),
            ("pixel", ["band_math"]),
        ]

    def test_the_run_ends_before_a_step_that_measures(self) -> None:
        assert _passes([NDVI, _normalize("zscore", "NDVI")], ["NDVI"]) == [
            ("pixel", ["band_math"]),
            ("pixel", ["normalize"]),
        ]
        assert _passes([MASK, NDVI, _normalize("robust", "NDVI"), MASK], ["NDVI"]) == [
            ("pixel", ["mask", "band_math"]),
            ("pixel", ["normalize", "mask"]),
        ]

    def test_a_first_step_that_measures_has_an_empty_pass_before_it_that_reads_the_inputs(self) -> None:
        assert _passes([_normalize("percentile", "red")], ["red"]) == [("pixel", []), ("pixel", ["normalize"])]

    def test_after_a_grid_step_the_pass_of_that_step_is_the_one_that_counts(self) -> None:
        assert _passes([REPROJECT, _normalize("zscore", "red")], ["red"]) == [
            ("pixel", []),
            ("grid", ["reproject"]),
            ("pixel", ["normalize"]),
        ]

    def test_two_steps_that_measure_are_two_cuts(self) -> None:
        steps = [_normalize("zscore", "red"), _normalize("percentile", "red")]
        assert _passes(steps, ["red"]) == [("pixel", []), ("pixel", ["normalize"]), ("pixel", ["normalize"])]

    def test_what_is_judged_is_what_the_step_converts_after_the_planner_dropped_the_rest(self) -> None:
        """The bands nobody keeps are not converted, so not measured; a step left with none is not run at all."""
        chain = stock_steps(_meta(), plan_steps([_normalize("zscore", "red", "nir")], REGISTRY), ["nir"])
        (kept,) = [s for s in chain if s.step.op == "normalize"]
        assert kept.operator.measures(kept.params) == {"nir"}
        assert "normalize" not in [op for _, ops in _passes([_normalize("zscore", "red")], ["nir"]) for op in ops]

    def test_the_planners_selection_before_the_step_stays_in_the_pass_before_it(self) -> None:
        chain = stock_steps(_meta(), plan_steps([_normalize("zscore", "nir")], REGISTRY), ["nir"])
        assert [s.step.op for s in chain] == ["select_bands", "normalize"]
        assert [(p.kind, [s.step.op for s in p.steps]) for p in segments(chain)] == [
            ("pixel", ["select_bands"]),
            ("pixel", ["normalize"]),
        ]

    def test_the_pass_that_opens_with_the_step_knows_it_and_no_other_pass_does(self) -> None:
        chain = stock_steps(_meta(), plan_steps([NDVI, _normalize("zscore", "NDVI"), MASK], REGISTRY), ["NDVI"])
        found = [bool(segment.measuring) for segment in segments(chain)]
        assert found == [False, True]
        assert segments(chain)[1].measuring.step.op == "normalize"

    def test_a_step_that_measures_before_a_grid_step_is_cut_like_any_other_and_counts_on_the_grid_of_the_stock(
        self,
    ) -> None:
        assert _passes([_normalize("zscore", "red"), REPROJECT], ["red"]) == [
            ("pixel", []),
            ("pixel", ["normalize"]),
            ("grid", ["reproject"]),
        ]
        assert _passes([NDVI, _normalize("zscore", "NDVI"), REPROJECT], ["NDVI"]) == [
            ("pixel", ["band_math"]),
            ("pixel", ["normalize"]),
            ("grid", ["reproject"]),
        ]

    def test_linear_before_a_grid_step_is_no_problem(self) -> None:
        chain = stock_steps(_meta(), plan_steps([LINEAR_STEP, REPROJECT], REGISTRY), ["red"])
        assert [segment.kind for segment in segments(chain)] == ["pixel", "grid"]


def _job(steps: list[dict], bands: list[str], **options):
    return recipe_from_data(recipe(steps, bands, **options), REGISTRY)


class TestWhatTheCutCosts:
    def test_the_seconds_grow_by_the_measure_rate_for_every_band_of_the_stock_at_the_cut(self) -> None:
        plain = estimate(_job([step(LINEAR, 3)], ["red", "nir"]), REGISTRY)
        cut = estimate(_job([step(_with(ZSCORE, bands=["red", "nir"]))], ["red", "nir"]), REGISTRY)
        extra = SECONDS_PER_MEASURE_BAND_MPIXEL * cut.output_pixels / 1e6 * 2
        assert cut.seconds - plain.seconds == pytest.approx(extra, rel=1e-9)
        assert (cut.input_bytes, cut.output_bytes) == (plain.input_bytes, plain.output_bytes)
        assert cut.memory_bytes - plain.memory_bytes == 2 * MEMORY_BYTES_PER_MEASURED_BAND

    def test_the_rate_is_the_one_measured_in_the_plan(self) -> None:
        assert SECONDS_PER_MEASURE_BAND_MPIXEL == 0.2

    def test_each_cut_counts_with_the_bands_of_the_stock_at_that_cut(self) -> None:
        one = estimate(_job([step(_with(ZSCORE, bands=["red"]))], ["red", "nir"]), REGISTRY)
        two = estimate(
            _job([step(_with(ZSCORE, bands=["red"])), step(_with(PERCENTILE, bands=["red"]))], ["red", "nir"]), REGISTRY
        )
        assert two.seconds - one.seconds == pytest.approx(
            SECONDS_PER_MEASURE_BAND_MPIXEL * one.output_pixels / 1e6 * 2, rel=1e-9
        )

    def test_linear_costs_no_cut(self) -> None:
        a = estimate(_job([step(LINEAR, 3)], ["red", "nir"]), REGISTRY)
        b = estimate(_job([step(LINEAR, 4)], ["red", "nir"]), REGISTRY)
        assert a.seconds == b.seconds

    def test_a_cut_before_a_grid_step_counts_the_pixels_of_the_raster_before_it(self) -> None:
        """The raster at the cut is the stock's, not the result's: the warp to 20 m has a quarter of the pixels."""
        reproject = {"op": "reproject", "op_version": 4, "params": REPROJECT.params}
        before = estimate(_job([step(_with(ZSCORE, bands=["red"])), reproject], ["red"]), REGISTRY)
        after = estimate(_job([reproject, step(_with(ZSCORE, bands=["red"]))], ["red"]), REGISTRY)
        plain = estimate(_job([reproject], ["red"]), REGISTRY)
        assert after.output_pixels == before.output_pixels
        extra_after = SECONDS_PER_MEASURE_BAND_MPIXEL * after.output_pixels / 1e6
        extra_before = SECONDS_PER_MEASURE_BAND_MPIXEL * 4 * after.output_pixels / 1e6  # 10 m to 20 m: a quarter
        assert after.seconds - plain.seconds == pytest.approx(extra_after, rel=1e-9)
        assert before.seconds - plain.seconds == pytest.approx(extra_before, rel=0.05)


class TestWhatTheCutCostsInMemory:
    def test_every_measured_band_adds_its_share_on_top_of_the_stock(self) -> None:
        for bands in (1, 2, 4):
            assert memory_needed(bands, 1, bands) - memory_needed(bands) == bands * MEMORY_BYTES_PER_MEASURED_BAND

    def test_the_estimate_of_a_job_counts_the_bands_the_step_measures_and_not_the_stock(self) -> None:
        plain = estimate(_job([step({**LINEAR, "bands": ["red", "nir"]}, 3)], ["red", "nir"]), REGISTRY)
        one = estimate(_job([step(_with(ZSCORE, bands=["red"]))], ["red", "nir"]), REGISTRY)
        two = estimate(_job([step(ZSCORE)], ["red", "nir"]), REGISTRY)
        assert one.memory_bytes - plain.memory_bytes == MEMORY_BYTES_PER_MEASURED_BAND
        assert two.memory_bytes - plain.memory_bytes == 2 * MEMORY_BYTES_PER_MEASURED_BAND

    def test_the_most_bands_of_any_one_cut_count_and_not_their_sum(self) -> None:
        steps = [step(_with(ZSCORE, bands=["red"])), step(_with(PERCENTILE, bands=["red", "nir"]))]
        both = estimate(_job(steps, ["red", "nir"]), REGISTRY)
        plain = estimate(_job([step({**LINEAR, "bands": ["red", "nir"]}, 3)], ["red", "nir"]), REGISTRY)
        assert both.memory_bytes - plain.memory_bytes == 2 * MEMORY_BYTES_PER_MEASURED_BAND


@pytest.fixture
def served(monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory) -> None:
    """Four bands of noise: it is what deflate compresses worst, so the files in the work directory are as large as they get."""
    root = tmp_path_factory.mktemp("measure-disk")
    files = {}
    for seed, name in enumerate(("red", "nir", "green", "blue")):
        noise = numpy.random.default_rng(seed).integers(1, 60000, (3000, 3000)).astype("uint16")
        files[name] = sources.build_band_cog(root / f"{name}.tif", noise)
    sources.serve({sources.url(name): path for name, path in files.items()}, monkeypatch)


class TestTheWorkFileOfTheCount:
    BANDS = ["red", "nir", "green", "blue"]

    def test_the_formula_names_the_work_file_and_is_unchanged_by_the_cut(self) -> None:
        wide = {"assets": tuple(self.BANDS), "size": (3000, 3000)}
        with_cut = disk_needed(_job([step(_with(PERCENTILE, bands=self.BANDS))], self.BANDS, **wide), REGISTRY)
        without = disk_needed(_job([step({**LINEAR, "bands": self.BANDS}, 3)], self.BANDS, **wide), REGISTRY)
        assert with_cut == without > DISK_RESERVE_BYTES

    def test_the_most_the_work_directory_ever_holds_stays_below_what_is_needed(
        self, served: None, tmp_path: Path
    ) -> None:
        """3000², four bands: the most the files in the work directory ever add up to, probed at every block."""
        params = _with(PERCENTILE, bands=self.BANDS)
        data = recipe([step(params)], self.BANDS, assets=tuple(self.BANDS), size=(3000, 3000))
        highest = 0

        def probe(done: int, total: int) -> None:
            nonlocal highest
            with os.scandir(tmp_path) as entries:
                highest = max(highest, sum(entry.stat().st_size for entry in entries if entry.is_file()))

        result = do_run(data, tmp_path, progress=probe)
        needed = disk_needed(recipe_from_data(data, REGISTRY), REGISTRY)
        assert 0 < highest < needed
        assert sorted(path.name for path in tmp_path.iterdir()) == ["mask.tif", "result.tif"]
        assert result.properties["earthx:normalize"][0]["method"] == "percentile"
