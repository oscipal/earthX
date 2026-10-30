"""The methods of ``normalize`` version 3: linear, percentile, z-score, robust (NM4-11, adr/0014 §15 Nachtrag NM4-11).

Every method is a line per band whose numbers stand in the recipe. The kernels are held against plain Python floats
(IEEE doubles, one operation at a time) and against exact fractions; the numbers a measure gives are held against numpy
on the same pixels; a run gives the formula on physical values, the same bytes twice, and the same bytes with and
without the bands the planner drops.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
import textwrap
from dataclasses import replace
from fractions import Fraction
from pathlib import Path

import numpy
import pytest
import rasterio
from pydantic import ValidationError
from rasterio.transform import Affine
from rio_tiler.io import Reader
from rio_tiler.models import ImageData

from earthx.api.processing_docs import order_schema
from earthx.catalog.datasets import COP_DEM_GLO_30, SENTINEL_2_L2A
from earthx.processing import run
from earthx.processing.errors import RecipeInvalid
from earthx.processing.operators import (
    NORMALIZE,
    NORMALIZE_V2,
    NORMALIZE_V3,
    REGISTRY,
    BandMeta,
    NormalizeParamsV2,
    NormalizeParamsV3,
    OperatorRegistry,
    RasterMeta,
    Tier,
    applicable,
)
from earthx.processing.operators.normalize import NormalizeParams
from earthx.processing.recipe import recipe_from_data
from earthx.processing.statistics import MEASURE_PERCENTILES, BandStatistics
from tests.earthx.processing import sources
from tests.earthx.processing.recipes import resolved
from tests.earthx.processing.test_band_math import _SETTING_D, _glibc_masks_features
from tests.earthx.processing.version_1_cases import HEIGHT, WIDTH

LINEAR = {"method": "linear", "bands": ["red"], "in_min": 0.0, "in_max": 0.5, "out_min": 0.0, "out_max": 255.0, "clip": True}
PERCENTILE = {
    "method": "percentile",
    "bands": ["red"],
    "low": 2,
    "high": 98,
    "out_min": 0.0,
    "out_max": 1.0,
    "clip": True,
    "measured": {"factor": 1, "bands": {"red": {"p_low": 0.1, "p_high": 0.9}}},
}
ZSCORE = {
    "method": "zscore",
    "bands": ["red"],
    "measured": {"factor": 1, "bands": {"red": {"mean": 0.5, "stddev": 0.25}}},
}
ROBUST = {
    "method": "robust",
    "bands": ["red"],
    "measured": {"factor": 1, "bands": {"red": {"p25": 0.25, "median": 0.5, "p75": 0.75}}},
}
METHODS = {"linear": LINEAR, "percentile": PERCENTILE, "zscore": ZSCORE, "robust": ROBUST}


def _params(data: dict) -> NormalizeParamsV3:
    return NormalizeParamsV3.model_validate_json(json.dumps(data), strict=True)


def _with(data: dict, **change) -> dict:
    changed = copy.deepcopy(data)
    changed.update(change)
    return {key: value for key, value in changed.items() if value is not ...}


def _image(*arrays: numpy.ndarray, mask=None, names: list[str] | None = None) -> ImageData:
    stack = numpy.ma.stack([numpy.ma.masked_array(a, mask=mask) for a in arrays])
    return ImageData(
        stack, bounds=(0, 0, 1, 1), crs="EPSG:32632", band_names=names or [f"b{i}" for i in range(len(arrays))]
    )


def _samples(seed: int = 3, size: int = 4000) -> numpy.ndarray:
    """One row of values: an image band is rows by columns."""
    return numpy.random.default_rng(seed).uniform(-0.4, 1.4, (1, size))


def _plain(values: numpy.ndarray, formula) -> numpy.ndarray:
    """``formula`` on each value as a plain Python float, then float32: a second implementation of the arithmetic."""
    done = numpy.array([formula(float(value)) for value in values.ravel()], dtype="float64")
    return done.reshape(values.shape).astype("float32")


class TestParameters:
    @pytest.mark.parametrize("method", list(METHODS))
    def test_each_method_reads_from_json(self, method: str) -> None:
        assert _params(METHODS[method]).method == method

    def test_the_ends_of_the_percentiles_may_be_the_minimum_and_the_maximum(self) -> None:
        assert (_params(_with(PERCENTILE, low=0, high=100)).low, _params(_with(PERCENTILE, low=5, high=95)).high) == (0, 95)

    @pytest.mark.parametrize(
        ("name", "base", "change"),
        [
            ("unknown method", LINEAR, {"method": "minmax"}),
            ("no method", LINEAR, {"method": ...}),
            ("linear with measured", LINEAR, {"measured": PERCENTILE["measured"]}),
            ("linear with low", LINEAR, {"low": 2}),
            ("linear without in_max", LINEAR, {"in_max": ...}),
            ("linear with in_min at in_max", LINEAR, {"in_min": 0.5}),
            ("linear with a clip that is no boolean", LINEAR, {"clip": 1}),
            ("percentile with in_min", PERCENTILE, {"in_min": 0.0}),
            ("percentile without measured", PERCENTILE, {"measured": ...}),
            ("percentile without clip", PERCENTILE, {"clip": ...}),
            ("percentile with a low that is no choice", PERCENTILE, {"low": 3}),
            ("percentile with a high that is no choice", PERCENTILE, {"high": 97}),
            ("percentile with a flat target range", PERCENTILE, {"out_max": 0.0}),
            ("zscore with clip", ZSCORE, {"clip": True}),
            ("zscore with a target range", ZSCORE, {"out_min": 0.0}),
            ("zscore without measured", ZSCORE, {"measured": ...}),
            ("robust with measured of another method", ROBUST, {"measured": ZSCORE["measured"]}),
            ("empty bands", LINEAR, {"bands": []}),
            ("a band twice, case ignored", LINEAR, {"bands": ["red", "RED"]}),
            ("a band name of 65 characters", LINEAR, {"bands": ["x" * 65]}),
            ("an empty band name", LINEAR, {"bands": [""]}),
            ("too many bands", LINEAR, {"bands": [f"b{i}" for i in range(257)]}),
            ("extra field", LINEAR, {"extra": 1}),
        ],
        ids=lambda value: value if isinstance(value, str) else None,
    )
    def test_misuse_is_refused(self, name: str, base: dict, change: dict) -> None:
        with pytest.raises(ValidationError):
            _params(_with(base, **change))

    @pytest.mark.parametrize(
        ("name", "measured"),
        [
            ("band missing", {"factor": 1, "bands": {}}),
            ("another band", {"factor": 1, "bands": {"nir": {"p_low": 0.1, "p_high": 0.9}}}),
            ("name in another case", {"factor": 1, "bands": {"RED": {"p_low": 0.1, "p_high": 0.9}}}),
            ("an extra band", {"factor": 1, "bands": {"red": {"p_low": 0.1, "p_high": 0.9}, "nir": {"p_low": 0, "p_high": 1}}}),
            ("p_low above p_high", {"factor": 1, "bands": {"red": {"p_low": 0.9, "p_high": 0.1}}}),
            ("a number of another method", {"factor": 1, "bands": {"red": {"p_low": 0.1, "p_high": 0.9, "mean": 0.5}}}),
            ("p_high missing", {"factor": 1, "bands": {"red": {"p_low": 0.1}}}),
            ("factor 0", {"factor": 0, "bands": {"red": {"p_low": 0.1, "p_high": 0.9}}}),
            ("factor as a fraction", {"factor": 1.5, "bands": {"red": {"p_low": 0.1, "p_high": 0.9}}}),
            ("factor beyond reason", {"factor": 10001, "bands": {"red": {"p_low": 0.1, "p_high": 0.9}}}),
            ("a range that overflows", {"factor": 1, "bands": {"red": {"p_low": -1e308, "p_high": 1e308}}}),
            ("a number as text", {"factor": 1, "bands": {"red": {"p_low": "0.1", "p_high": 0.9}}}),
            ("an extra key", {"factor": 1, "bands": {"red": {"p_low": 0.1, "p_high": 0.9}}, "note": "x"}),
        ],
    )
    def test_numbers_that_do_not_fit_the_percentile_stretch_are_refused(self, name: str, measured: dict) -> None:
        with pytest.raises(ValidationError):
            _params(_with(PERCENTILE, measured=measured))

    @pytest.mark.parametrize(
        ("method", "values"),
        [
            ("zscore", {"mean": 0.5, "stddev": -1.0}),
            ("zscore", {"mean": 0.5}),
            ("zscore", {"stddev": 1.0}),
            ("zscore", {"mean": 0.5, "stddev": 1.0, "median": 0.5}),
            ("robust", {"p25": 0.6, "median": 0.5, "p75": 0.75}),
            ("robust", {"p25": 0.25, "median": 0.8, "p75": 0.75}),
            ("robust", {"p25": 0.25, "median": 0.5}),
            ("robust", {"p25": -1e308, "median": 0.0, "p75": 1e308}),
        ],
    )
    def test_numbers_that_do_not_fit_the_other_methods_are_refused(self, method: str, values: dict) -> None:
        base = ZSCORE if method == "zscore" else ROBUST
        with pytest.raises(ValidationError):
            _params(_with(base, measured={"factor": 1, "bands": {"red": values}}))

    @pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity"])
    @pytest.mark.parametrize("method", list(METHODS))
    def test_a_non_finite_number_is_refused(self, method: str, token: str) -> None:
        text = json.dumps(METHODS[method])
        for needle in ('"in_max": 0.5', '"p_high": 0.9', '"stddev": 0.25', '"p75": 0.75'):
            if needle in text:
                text = text.replace(needle, needle.rsplit(": ", 1)[0] + f": {token}")
        with pytest.raises(ValidationError):
            NormalizeParamsV3.model_validate_json(text, strict=True)

    def test_a_constant_band_is_allowed_and_a_reversed_target_range_too(self) -> None:
        _params(_with(ZSCORE, measured={"factor": 1, "bands": {"red": {"mean": 0.5, "stddev": 0.0}}}))
        _params(_with(ROBUST, measured={"factor": 1, "bands": {"red": {"p25": 0.5, "median": 0.5, "p75": 0.5}}}))
        _params(_with(PERCENTILE, measured={"factor": 3, "bands": {"red": {"p_low": 0.5, "p_high": 0.5}}}, out_min=1.0, out_max=0.0))


class TestKernelAgainstAnIndependentCalculation:
    def test_linear_is_the_line_of_version_2_to_the_bit(self) -> None:
        values = _samples()
        image = _image(values.astype("float32"), values.astype("float32") * 2, names=["red", "nir"])
        third = NORMALIZE_V3.run(image, _params(LINEAR)).array
        second = NORMALIZE_V2.run(
            image, NormalizeParamsV2(bands=["red"], **{k: v for k, v in LINEAR.items() if k not in ("method", "bands")})
        ).array
        assert numpy.ma.getdata(third).tobytes() == numpy.ma.getdata(second).tobytes()
        assert third.mask.tobytes() == second.mask.tobytes()
        first = NORMALIZE.run(
            _image(values.astype("float32")),
            NormalizeParams(**{k: v for k, v in LINEAR.items() if k not in ("method", "bands")}),
        ).array
        assert numpy.ma.getdata(third)[0].tobytes() == numpy.ma.getdata(first)[0].tobytes()

    @pytest.mark.parametrize("clip", [True, False])
    @pytest.mark.parametrize(("out_min", "out_max"), [(0.0, 1.0), (1.0, 0.0), (-3.0, 250.0)])
    def test_percentile_is_the_line_through_the_two_values(self, clip: bool, out_min: float, out_max: float) -> None:
        data = _with(PERCENTILE, clip=clip, out_min=out_min, out_max=out_max)
        values = _samples()
        result = NORMALIZE_V3.run(_image(values, names=["red"]), _params(data)).array
        low, high = 0.1, 0.9

        def formula(x: float) -> float:
            y = (x - low) / (high - low) * (out_max - out_min) + out_min
            return min(max(y, min(out_min, out_max)), max(out_min, out_max)) if clip else y

        numpy.testing.assert_array_equal(numpy.ma.getdata(result)[0], _plain(values, formula))
        exact = [
            float(
                (Fraction(float(x)) - Fraction(low)) / (Fraction(high) - Fraction(low)) * Fraction(out_max - out_min)
                + Fraction(out_min)
            )
            for x in values.ravel()
        ]
        if not clip:
            numpy.testing.assert_allclose(numpy.ma.getdata(result)[0].ravel(), exact, rtol=1e-6, atol=1e-9)

    def test_zscore_is_the_value_less_the_mean_over_the_standard_deviation(self) -> None:
        values = _samples()
        result = NORMALIZE_V3.run(_image(values, names=["red"]), _params(ZSCORE)).array
        numpy.testing.assert_array_equal(numpy.ma.getdata(result)[0], _plain(values, lambda x: (x - 0.5) / 0.25))
        exact = [float((Fraction(float(x)) - Fraction(1, 2)) / Fraction(1, 4)) for x in values.ravel()]
        numpy.testing.assert_allclose(numpy.ma.getdata(result)[0].ravel(), exact, rtol=1e-6, atol=1e-9)

    def test_robust_is_the_value_less_the_median_over_the_interquartile_range(self) -> None:
        values = _samples()
        result = NORMALIZE_V3.run(_image(values, names=["red"]), _params(ROBUST)).array
        numpy.testing.assert_array_equal(numpy.ma.getdata(result)[0], _plain(values, lambda x: (x - 0.5) / (0.75 - 0.25)))

    @pytest.mark.parametrize(
        ("data", "formula"),
        [
            (
                _with(ZSCORE, measured={"factor": 1, "bands": {"red": {"mean": 0.5, "stddev": 0.0}}}),
                lambda x: x - 0.5,
            ),
            (
                _with(ROBUST, measured={"factor": 1, "bands": {"red": {"p25": 0.4, "median": 0.5, "p75": 0.4}}}),
                lambda x: x - 0.5,
            ),
            (
                _with(PERCENTILE, measured={"factor": 1, "bands": {"red": {"p_low": 0.5, "p_high": 0.5}}}),
                lambda x: min(max((x - 0.5) / 1.0 * 1.0 + 0.0, 0.0), 1.0),
            ),
        ],
        ids=["zscore", "robust", "percentile"],
    )
    def test_a_span_of_zero_divides_by_one_as_in_scikit_learn(self, data: dict, formula) -> None:
        if data["method"] == "robust":  # p25 above p75 is refused; a zero span needs equal quartiles
            data = _with(data, measured={"factor": 1, "bands": {"red": {"p25": 0.5, "median": 0.5, "p75": 0.5}}})
        values = _samples()
        result = NORMALIZE_V3.run(_image(values, names=["red"]), _params(data)).array
        assert numpy.isfinite(numpy.ma.getdata(result)).all() and not numpy.ma.getmaskarray(result).any()
        numpy.testing.assert_array_equal(numpy.ma.getdata(result)[0], _plain(values, formula))

    @pytest.mark.parametrize("method", list(METHODS))
    def test_the_mask_is_kept_and_a_masked_pixel_is_nan(self, method: str) -> None:
        values = numpy.array([[0.25, 0.5, 0.75, 2.0]])
        masked = numpy.array([[False, True, False, False]])
        result = NORMALIZE_V3.run(_image(values, mask=masked, names=["red"]), _params(METHODS[method])).array
        numpy.testing.assert_array_equal(numpy.ma.getmaskarray(result)[0], masked)
        assert numpy.isnan(numpy.ma.getdata(result)[0, 0, 1])

    def test_an_overflow_is_masked(self) -> None:
        data = _with(ZSCORE, measured={"factor": 1, "bands": {"red": {"mean": 0.0, "stddev": 1e-300}}})
        result = NORMALIZE_V3.run(_image(numpy.array([[0.0, 1.0]]), names=["red"]), _params(data)).array
        numpy.testing.assert_array_equal(numpy.ma.getmaskarray(result)[0], [[False, True]])

    @pytest.mark.parametrize("method", list(METHODS))
    def test_it_does_not_look_at_the_other_pixels(self, method: str) -> None:
        """The numbers are in the recipe: the same pixel gives the same value in any neighbourhood."""
        one = NORMALIZE_V3.run(_image(numpy.array([[0.3]]), names=["red"]), _params(METHODS[method])).array.data
        many = NORMALIZE_V3.run(_image(numpy.array([[0.3, 100.0, -50.0]]), names=["red"]), _params(METHODS[method])).array.data
        assert one[0, 0, 0] == many[0, 0, 0]

    def test_each_band_gets_its_own_numbers_and_the_others_are_left_alone(self) -> None:
        data = {
            "method": "zscore",
            "bands": ["a", "c"],
            "measured": {
                "factor": 1,
                "bands": {"a": {"mean": 1.0, "stddev": 2.0}, "c": {"mean": 10.0, "stddev": 5.0}},
            },
        }
        a, b, c = numpy.array([[1.0, 3.0]]), numpy.array([[7, 9]], dtype="uint16"), numpy.array([[10.0, 20.0]])
        image = ImageData(
            numpy.ma.stack([numpy.ma.masked_array(x.astype("float64")) for x in (a, b, c)]),
            bounds=(0, 0, 1, 1),
            crs="EPSG:32632",
            band_names=["a", "b", "c"],
        )
        result = NORMALIZE_V3.run(image, _params(data))
        numpy.testing.assert_array_equal(result.array.data[0], [[0.0, 1.0]])
        numpy.testing.assert_array_equal(result.array.data[1], [[7.0, 9.0]])
        numpy.testing.assert_array_equal(result.array.data[2], [[0.0, 2.0]])
        assert list(result.band_names) == ["a", "b", "c"]

    def test_a_band_that_is_not_in_the_stock_is_named_in_the_refusal(self) -> None:
        with pytest.raises(RecipeInvalid, match="unknown band.*red.*the input has: b0"):
            NORMALIZE_V3.run(_image(numpy.array([[1.0]])), _params(LINEAR))


class TestNumbersFromTheStatisticsOfTheArea:
    """The route measures with the fixed histogram of M4-32; the percentiles it adds are the nearest ranks of numpy."""

    def test_whole_percents_of_a_sixteen_bit_band_are_exact(self) -> None:
        rng = numpy.random.default_rng(11)
        values = rng.integers(1, 4000, 50_000).astype("uint16")
        statistics = BandStatistics("uint16")
        statistics.add(values)
        summary = statistics.summary(values.size, MEASURE_PERCENTILES)
        for percent in (1, 2, 5, 25, 50, 75, 95, 98, 99):
            assert summary[f"percentile_{percent}"] == numpy.percentile(values, percent, method="inverted_cdf")

    def test_a_float_band_holds_the_exact_value_within_a_bin_and_the_other_numbers_are_exact(self) -> None:
        values = numpy.random.default_rng(5).normal(0.3, 0.2, 60_000).astype("float32")
        statistics = BandStatistics("float32")
        for start in range(0, values.size, 4096):
            statistics.add(values[start : start + 4096])
        summary = statistics.summary(values.size, MEASURE_PERCENTILES)
        for percent in (1, 2, 5, 25, 50, 75, 95, 98, 99):
            exact = float(numpy.percentile(values, percent, method="inverted_cdf"))
            got = summary[f"percentile_{percent}"]
            assert (got <= exact) if percent <= 50 else (got >= exact)
            assert got == pytest.approx(exact, rel=2**-6, abs=1e-12)
        assert summary["mean"] == pytest.approx(float(values.astype("float64").mean()), rel=1e-12)
        assert summary["stddev"] == pytest.approx(float(values.astype("float64").std()), rel=1e-6)
        assert summary["minimum"] == float(values.min()) and summary["maximum"] == float(values.max())
        ladder = [summary[name] for name in ("percentile_1", "percentile_2", "percentile_5", "percentile_25",
                                             "percentile_50", "percentile_75", "percentile_95", "percentile_98",
                                             "percentile_99")]
        assert ladder == sorted(ladder)

    def test_a_percent_outside_one_to_ninety_nine_is_refused(self) -> None:
        statistics = BandStatistics("uint16")
        statistics.add(numpy.arange(1, 10, dtype="uint16"))
        for percent in (0, 100, -1, 101):
            with pytest.raises(ValueError, match="whole percent from 1 to 99"):
                statistics.summary(9, (percent,))

    def test_the_summary_without_extras_is_what_a_result_carries(self) -> None:
        statistics = BandStatistics("uint16")
        statistics.add(numpy.arange(1, 1000, dtype="uint16"))
        assert {k for k in statistics.summary(999) if k.startswith("percentile")} == {"percentile_2", "percentile_98"}

    @pytest.mark.parametrize("seed", [1, 2])
    def test_the_methods_do_what_they_say_with_those_numbers(self, seed: int) -> None:
        values = numpy.random.default_rng(seed).normal(0.4, 0.15, 80_000).astype("float32")
        statistics = BandStatistics("float32")
        statistics.add(values)
        summary = statistics.summary(values.size, MEASURE_PERCENTILES)
        image = _image(values.reshape(1, -1), names=["x"])

        def measured(**numbers) -> dict:
            return {"factor": 1, "bands": {"x": numbers}}

        stretch = NORMALIZE_V3.run(
            image,
            _params(
                {
                    "method": "percentile", "bands": ["x"], "low": 2, "high": 98, "out_min": 0.0, "out_max": 1.0,
                    "clip": True,
                    "measured": measured(p_low=summary["percentile_2"], p_high=summary["percentile_98"]),
                }
            ),
        ).array.data[0, 0]
        assert stretch.min() == 0.0 and stretch.max() == 1.0
        assert (stretch == 0.0).mean() == pytest.approx(0.02, abs=0.004)
        assert (stretch == 1.0).mean() == pytest.approx(0.02, abs=0.004)

        zscore = NORMALIZE_V3.run(
            image, _params({"method": "zscore", "bands": ["x"], "measured": measured(mean=summary["mean"], stddev=summary["stddev"])})
        ).array.data[0, 0].astype("float64")
        assert zscore.mean() == pytest.approx(0.0, abs=1e-4) and zscore.std() == pytest.approx(1.0, abs=1e-4)

        robust = NORMALIZE_V3.run(
            image,
            _params(
                {
                    "method": "robust", "bands": ["x"],
                    "measured": measured(p25=summary["percentile_25"], median=summary["percentile_50"], p75=summary["percentile_75"]),
                }
            ),
        ).array.data[0, 0].astype("float64")
        assert numpy.median(robust) == pytest.approx(0.0, abs=0.01)
        assert numpy.percentile(robust, 75) - numpy.percentile(robust, 25) == pytest.approx(1.0, abs=0.03)


class TestTheOperator:
    def test_it_runs_as_a_tile_and_as_a_job_and_is_not_listed_until_the_panel_sends_it(self) -> None:
        assert NORMALIZE_V3.tiers == frozenset({Tier.T1, Tier.T2})
        assert NORMALIZE_V3.kind == "pixel" and NORMALIZE_V3.stock is True and NORMALIZE_V3.listed is False
        assert REGISTRY.operator("normalize", 3) is NORMALIZE_V3
        # Version 2 stays accepted, version 1 too.
        assert REGISTRY.operator("normalize", 2) is NORMALIZE_V2

    def test_the_process_description_offers_it_once_it_is_listed(self) -> None:
        steps = order_schema(REGISTRY)["$defs"]
        assert "step_normalize_v1" in steps and "step_normalize_v3" not in steps
        listed = OperatorRegistry(
            replace(operator, listed=True) if operator.op == "normalize" and operator.op_version == 3 else operator
            for operator in REGISTRY.values()
        )
        steps = order_schema(listed)["$defs"]
        assert "step_normalize_v3" in steps and "step_normalize_v1" not in steps
        assert {"method", "bands", "measured"} <= set(steps["step_normalize_v3"]["properties"]["params"]["properties"])
        assert {"step_normalize_v3__Measured", "step_normalize_v3__BandValues"} <= set(steps)

    def test_the_parameters_are_a_schema_the_panel_can_read_the_methods_from(self) -> None:
        schema = REGISTRY.params_schema("normalize", 3)
        assert schema["properties"]["method"]["enum"] == ["linear", "percentile", "zscore", "robust"]
        assert schema["required"] == ["method", "bands"]

    def test_transform_changes_the_named_bands_to_float32_with_nan_and_leaves_the_others(self) -> None:
        meta = RasterMeta(
            "EPSG:32632", Affine(10, 0, 0, 0, -10, 0), 4, 4,
            (BandMeta("red", "uint16", 0, resampled=True), BandMeta("scl", "uint8", 0, "1")), False,
        )
        result = NORMALIZE_V3.transform(meta, _params(LINEAR))
        assert [(b.name, b.data_type) for b in result.bands] == [("red", "float32"), ("scl", "uint8")]
        assert numpy.isnan(result.bands[0].nodata) and result.bands[1].nodata == 0 and result.bands[0].resampled
        with pytest.raises(RecipeInvalid, match="unknown band.*nir"):
            NORMALIZE_V3.transform(meta, _params(_with(LINEAR, bands=["nir"])))

    def test_the_planner_sees_the_bands_it_acts_on(self) -> None:
        use = NORMALIZE_V3.bands_used(_params(_with(ZSCORE, bands=["red"])))
        assert use.acts_on == frozenset({"red"}) and use.reads == frozenset() and use.adds is None

    def test_restricting_the_step_drops_the_numbers_of_the_bands_that_are_gone(self) -> None:
        data = {
            "method": "zscore",
            "bands": ["a", "b"],
            "measured": {"factor": 2, "bands": {"a": {"mean": 1.0, "stddev": 2.0}, "b": {"mean": 3.0, "stddev": 4.0}}},
        }
        restricted = NORMALIZE_V3.restrict(_params(data), frozenset({"b", "z"}))
        assert restricted.bands == ["b"] and list(restricted.measured.bands) == ["b"] and restricted.measured.factor == 2
        linear = NORMALIZE_V3.restrict(_params(_with(LINEAR, bands=["a", "b"])), frozenset({"a"}))
        assert linear.bands == ["a"] and linear.measured is None

    def test_the_cost_factor_is_the_measured_one(self) -> None:
        assert all(NORMALIZE_V3.cost_factor(_params(data)) == 0.3 for data in METHODS.values())

    def test_lineage(self) -> None:
        assert NORMALIZE_V3.lineage(_params(LINEAR)) == "normalize: [0, 0.5] to [0, 255], clipped of red"
        assert NORMALIZE_V3.lineage(_params(_with(LINEAR, clip=False))) == "normalize: [0, 0.5] to [0, 255] of red"
        assert NORMALIZE_V3.lineage(_params(PERCENTILE)) == "normalize: percentiles 2 to 98 to [0, 1], clipped of red"
        assert NORMALIZE_V3.lineage(_params(ZSCORE)) == "normalize: zscore of red"
        assert NORMALIZE_V3.lineage(_params(_with(ROBUST, bands=["red"]))) == "normalize: robust of red"

    def test_the_methods_text_of_each_method(self) -> None:
        assert NORMALIZE_V3.method(_params(LINEAR)) == (
            "The band red was mapped linearly from the range 0 to 0.5 onto the range 0 to 255, values outside the "
            "source range limited to the target range, in 32-bit floating point."
        )
        assert NORMALIZE_V3.method(_params(PERCENTILE)) == (
            "The band red was stretched from the 2nd to the 98th percentile (red: 0.1 to 0.9; as measured before "
            "the run) onto the range 0 to 1, values outside limited to the target range, in 32-bit floating point."
        )
        assert NORMALIZE_V3.method(_params(ZSCORE)) == (
            "The band red was standardised, (x - mean) / standard deviation, with the mean and the population standard "
            "deviation of the band (red: mean 0.5, standard deviation 0.25; as measured before the run), in 32-bit "
            "floating point."
        )
        assert NORMALIZE_V3.method(_params(ROBUST)) == (
            "The band red was scaled robustly, (x - median) / interquartile range, with the median and the "
            "interquartile range (75th minus 25th percentile) of the band (red: median 0.5, interquartile range 0.5; "
            "as measured before the run), in 32-bit floating point."
        )

    def test_the_methods_text_names_a_coarser_read_and_a_constant_band(self) -> None:
        coarse = _with(ZSCORE, measured={"factor": 3, "bands": {"red": {"mean": 0.5, "stddev": 0.0}}})
        text = NORMALIZE_V3.method(_params(coarse))
        assert "as measured before the run, on a read 3 times coarser than the result" in text
        assert text.endswith("A band that is constant (standard deviation 0) was only centred.")

    def test_the_methods_text_of_several_bands_gives_the_numbers_of_each(self) -> None:
        data = {
            "method": "percentile", "bands": ["B04", "B08"], "low": 5, "high": 95, "out_min": -1.0, "out_max": 1.0,
            "clip": False,
            "measured": {"factor": 1, "bands": {"B04": {"p_low": 0.01, "p_high": 0.2}, "B08": {"p_low": 0.1, "p_high": 0.5}}},
        }
        assert NORMALIZE_V3.method(_params(data)) == (
            "The bands B04, B08 were stretched from the 5th to the 95th percentile (B04: 0.01 to 0.2; B08: 0.1 to "
            "0.5; as measured before the run) onto the range -1 to 1, values outside continued along the same line, "
            "in 32-bit floating point."
        )

    def test_the_licence_and_the_flag_are_those_of_the_other_versions(self) -> None:
        for config in (SENTINEL_2_L2A, COP_DEM_GLO_30):
            assert applicable(NORMALIZE_V3, config, _params(LINEAR)) == []
        off = replace(SENTINEL_2_L2A, capabilities=replace(SENTINEL_2_L2A.capabilities, normalization=False))
        assert applicable(NORMALIZE_V3, off, _params(LINEAR)) == ["sentinel-2-c1-l2a does not allow normalization"]


# --- a run ------------------------------------------------------------------------------------------------------


def _entry(asset: str) -> dict:
    entry = resolved("ITEM_A", asset, href=sources.url(asset), scale=0.0001, offset=-0.1)
    entry["gsd"] = 10.0
    entry["bands"][0]["unit"] = "1"
    return entry


def _recipe(steps: list, bands: list[str], assets=("red", "nir")) -> dict:
    return {
        "recipe_version": 2,
        "inputs": [
            {
                "name": "s2",
                "dataset": "synthetic",
                "groups": [["ITEM_A"]],
                "assets": list(assets),
                "resolved": [_entry(asset) for asset in assets],
            }
        ],
        "aoi": sources.whole(WIDTH, HEIGHT),
        "steps": steps,
        "output": {"kind": "raster", "format": "cog", "dtype": "float32", "bands": bands},
    }


def _step(params: dict) -> dict:
    return {"op": "normalize", "op_version": 3, "params": params}


def _run(data: dict, workdir: Path):
    workdir.mkdir(exist_ok=True)
    return run(recipe_from_data(data, REGISTRY), workdir=workdir, progress=lambda done, total: None, operators=REGISTRY)


def _read(path: Path) -> numpy.ma.MaskedArray:
    with rasterio.open(path) as dataset:
        return dataset.read(masked=True)


@pytest.fixture(scope="module")
def bands(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    root = tmp_path_factory.mktemp("normalize-methods")
    return {
        "red": sources.build_band_cog(root / "red.tif", sources.ramp(WIDTH, HEIGHT, 1200)),
        "nir": sources.build_band_cog(root / "nir.tif", sources.ramp(WIDTH, HEIGHT, 3400)),
    }


@pytest.fixture
def served(bands: dict[str, Path], monkeypatch: pytest.MonkeyPatch) -> list[str]:
    return sources.serve({sources.url(name): path for name, path in bands.items()}, monkeypatch)


@pytest.fixture(scope="module")
def physical(bands: dict[str, Path]) -> dict[str, numpy.ma.MaskedArray]:
    result = {}
    for name in ("red", "nir"):
        with Reader(str(bands[name])) as reader:
            result[name] = reader.read(unscale=True).array[0]
    return result


def _expected(band: numpy.ma.MaskedArray, formula) -> numpy.ndarray:
    return numpy.ma.masked_array(
        numpy.array([formula(float(v)) for v in numpy.ma.getdata(band).ravel()]).reshape(band.shape).astype("float32"),
        mask=numpy.ma.getmaskarray(band),
    )


@pytest.mark.usefixtures("served")
class TestARun:
    @pytest.mark.parametrize("method", list(METHODS))
    def test_a_run_gives_the_formula_on_physical_values(self, method: str, tmp_path: Path, physical: dict) -> None:
        formulas = {
            "linear": lambda x: min(max((x - 0.0) / 0.5 * 255.0 + 0.0, 0.0), 255.0),
            "percentile": lambda x: min(max((x - 0.1) / (0.9 - 0.1) * 1.0 + 0.0, 0.0), 1.0),
            "zscore": lambda x: (x - 0.5) / 0.25,
            "robust": lambda x: (x - 0.5) / (0.75 - 0.25),
        }
        result = _run(_recipe([_step(METHODS[method])], ["red"]), tmp_path)
        expected = _expected(physical["red"], formulas[method])
        got = _read(result.path)[0]
        numpy.testing.assert_array_equal(numpy.ma.getmaskarray(got), numpy.ma.getmaskarray(expected))
        numpy.testing.assert_array_equal(got.compressed(), expected.compressed())

    def test_two_runs_give_the_same_bytes(self, tmp_path: Path) -> None:
        data = _recipe([_step(PERCENTILE), _step(_with(ZSCORE, bands=["nir"], measured={"factor": 1, "bands": {"nir": {"mean": 0.4, "stddev": 0.1}}}))], ["red", "nir"])
        digests = {hashlib.sha256(_run(data, tmp_path / name).path.read_bytes()).hexdigest() for name in ("a", "b")}
        assert len(digests) == 1

    def test_the_lineage_the_methods_and_the_statistics_of_the_result(self, tmp_path: Path) -> None:
        result = _run(_recipe([_step(PERCENTILE)], ["red"]), tmp_path)
        assert result.properties["processing:lineage"] == "normalize: percentiles 2 to 98 to [0, 1], clipped of red"
        statistics = result.properties["bands"][0]["statistics"]
        assert 0.0 <= statistics["minimum"] <= statistics["maximum"] <= 1.0

    def test_a_band_that_nobody_converts_is_left_as_it_is(self, tmp_path: Path, physical: dict) -> None:
        result = _run(_recipe([_step(ZSCORE)], ["red", "nir"]), tmp_path)
        data = _read(result.path)
        numpy.testing.assert_array_equal(data[1].compressed(), physical["nir"].astype("float32").compressed())

    def test_an_unknown_band_is_named_before_the_first_pixel(self, tmp_path: Path) -> None:
        with pytest.raises(RecipeInvalid, match="unknown band.*swir"):
            _run(_recipe([_step(_with(LINEAR, bands=["red", "swir"]))], ["red"]), tmp_path)

    @pytest.mark.parametrize(
        ("name", "step"),
        [
            ("linear", _step(_with(LINEAR, bands=["red", "nir"]))),
            ("percentile", _step(_with(PERCENTILE, bands=["red", "nir"], measured={"factor": 1, "bands": {"red": {"p_low": 0.1, "p_high": 0.9}, "nir": {"p_low": 0.3, "p_high": 0.7}}}))),
            ("zscore", _step(_with(ZSCORE, bands=["red", "nir"], measured={"factor": 1, "bands": {"red": {"mean": 0.5, "stddev": 0.25}, "nir": {"mean": 0.4, "stddev": 0.1}}}))),
            ("robust", _step(_with(ROBUST, bands=["red", "nir"], measured={"factor": 1, "bands": {"red": {"p25": 0.25, "median": 0.5, "p75": 0.75}, "nir": {"p25": 0.3, "median": 0.4, "p75": 0.5}}}))),
        ],
    )
    def test_dropping_a_band_nobody_needs_changes_no_value_of_the_others(
        self, name: str, step: dict, tmp_path: Path
    ) -> None:
        """The planner narrows the step to the bands the output keeps; the band that stays has its value (adr/0020 §4)."""
        both = _run(_recipe([step], ["red", "nir"]), tmp_path / "both")
        alone = _run(_recipe([step], ["nir"]), tmp_path / "alone")
        assert _read(alone.path)[0].compressed().tobytes() == _read(both.path)[1].compressed().tobytes()

    def test_a_step_whose_bands_are_all_dropped_is_not_run_and_not_reported(self, tmp_path: Path) -> None:
        result = _run(_recipe([_step(ZSCORE)], ["nir"]), tmp_path)
        assert "processing:lineage" not in result.properties or "normalize" not in result.properties["processing:lineage"]


# --- bit-stability across CPU levels (adr/0016 §12a) -------------------------------------------------------------

_PROBE = textwrap.dedent(
    """
    import hashlib, json, sys
    import numpy
    from rio_tiler.models import ImageData
    from earthx.processing.operators import NORMALIZE_V3, NormalizeParamsV3

    rng = numpy.random.default_rng(7)
    a = rng.uniform(-0.3, 1.6, (512, 512))
    out = {}
    for dtype in ("float32", "float64"):
        image = ImageData(
            numpy.ma.stack([numpy.ma.masked_array(a.astype(dtype)), numpy.ma.masked_array((a * 7).astype(dtype))]),
            bounds=(0, 0, 1, 1), crs="EPSG:32632", band_names=["red", "nir"],
        )
        for name, params in json.loads(sys.argv[1]).items():
            result = NORMALIZE_V3.run(image, NormalizeParamsV3.model_validate_json(json.dumps(params), strict=True)).array
            out[f"{dtype}: {name}"] = hashlib.sha256(numpy.ma.getdata(result).tobytes() + result.mask.tobytes()).hexdigest()
    print(json.dumps(out))
    """
)


def _probe(env_extra: dict[str, str]) -> dict[str, str]:
    backend = str(Path(__file__).resolve().parents[3])
    both = ["red", "nir"]
    cases = {
        "linear": _with(LINEAR, bands=both),
        "percentile": _with(PERCENTILE, bands=both, measured={"factor": 1, "bands": {"red": {"p_low": -0.1, "p_high": 1.3}, "nir": {"p_low": 0.2, "p_high": 9.0}}}),
        "percentile reversed": _with(PERCENTILE, bands=both, out_min=1.0, out_max=-1.0, clip=False, measured={"factor": 1, "bands": {"red": {"p_low": -0.1, "p_high": 1.3}, "nir": {"p_low": 0.2, "p_high": 9.0}}}),
        "zscore": _with(ZSCORE, bands=both, measured={"factor": 1, "bands": {"red": {"mean": 0.7, "stddev": 0.45}, "nir": {"mean": 4.9, "stddev": 3.1}}}),
        "robust": _with(ROBUST, bands=both, measured={"factor": 1, "bands": {"red": {"p25": 0.3, "median": 0.7, "p75": 1.2}, "nir": {"p25": 2.1, "median": 4.9, "p75": 8.4}}}),
    }
    done = subprocess.run(
        [sys.executable, "-c", _PROBE, json.dumps(cases)],
        capture_output=True,
        text=True,
        env={**os.environ, **env_extra, "PYTHONPATH": backend},
        timeout=300,
        check=False,
    )
    assert done.returncode == 0, done.stderr[-2000:]
    return json.loads(done.stdout.strip().splitlines()[-1])


class TestBitStabilityAcrossCpuLevels:
    def test_the_four_methods_give_the_same_bytes_under_settings_a_and_d(self) -> None:
        if not _glibc_masks_features():
            pytest.skip("GLIBC_TUNABLES does not change the CPU features this loader reports: setting D is not one")
        setting_a, setting_d = _probe({}), _probe(_SETTING_D)
        assert len(setting_a) == 2 * 5
        assert sorted(key for key in setting_a if setting_a[key] != setting_d[key]) == []
        assert hashlib.sha256(b"").hexdigest() not in setting_a.values()
