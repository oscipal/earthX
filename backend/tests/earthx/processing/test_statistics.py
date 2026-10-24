"""``processing.statistics`` against an independent computation on synthetic rasters (M4-32, plan §6.2, §6.10).

The reference is plain Python and numpy, not the module's own arithmetic: the exact mean
from ``Fraction``, the percentiles from ``numpy.percentile(method="inverted_cdf")`` (the
nearest rank), ``stddev`` from ``numpy.std``.
"""

from __future__ import annotations

import json
import math
from fractions import Fraction

import numpy
import pytest

from earthx.processing.statistics import BandStatistics, gdal_tags, summarize

#: The relative width of one bin of the float histogram: 7 bits of the significand.
BIN = 2.0**-7

RNG = numpy.random.default_rng(20261020)


def _gathered(values: numpy.ndarray, block: int = 1024, reverse: bool = False) -> BandStatistics:
    statistics = BandStatistics(values.dtype)
    starts = list(range(0, values.size, block))
    for start in reversed(starts) if reverse else starts:
        statistics.add(values[start : start + block])
    return statistics


def _exact_mean(values: numpy.ndarray) -> float:
    return float(sum(map(Fraction, values.astype(numpy.float64).tolist())) / values.size)


def _assert_independent(summary: dict, values: numpy.ndarray, pixels: int, *, exact_percentiles: bool) -> None:
    """``summary`` against the reference computed from the valid values themselves."""
    assert summary["count"] == values.size
    assert summary["valid_percent"] == 100.0 * values.size / pixels
    assert summary["minimum"] == values.min() and summary["maximum"] == values.max()
    assert summary["mean"] == _exact_mean(values)
    assert summary["stddev"] == pytest.approx(float(values.astype(numpy.float64).std()), rel=1e-9)
    for percent, outward in ((2, -1), (98, 1)):
        true = float(numpy.percentile(values.astype(numpy.float64), percent, method="inverted_cdf"))
        reported = summary[f"percentile_{percent}"]
        if exact_percentiles:
            assert reported == true
        else:
            assert (reported - true) * outward >= 0  # rounded outwards, never inwards
            assert abs(reported - true) <= abs(true) * BIN


def _dem(size: int) -> numpy.ndarray:
    axis = numpy.linspace(0.0, 1.0, size)
    hills = 600 + 1800 * numpy.add.outer(numpy.sin(3 * axis), numpy.cos(5 * axis)) ** 2
    return (hills + RNG.normal(0, 2, (size, size))).astype("float32")


class TestAgainstAnIndependentComputation:
    def test_float_with_nan(self) -> None:
        data = RNG.normal(300.0, 80.0, 512 * 512).astype("float32")
        data[RNG.random(data.size) < 0.15] = numpy.nan
        valid = data[~numpy.isnan(data)]
        summary = _gathered(valid).summary(data.size)
        _assert_independent(summary, valid, data.size, exact_percentiles=False)
        assert summary["valid_percent"] < 90

    def test_integer_with_nodata(self) -> None:
        data = RNG.integers(1, 12000, 600 * 400).astype("uint16")
        data[RNG.random(data.size) < 0.2] = 0  # nodata
        valid = data[data != 0]
        summary = _gathered(valid).summary(data.size)
        _assert_independent(summary, valid, data.size, exact_percentiles=True)
        assert isinstance(summary["minimum"], int) and isinstance(summary["percentile_98"], int)

    def test_dem_like(self) -> None:
        values = _dem(700).ravel()
        _assert_independent(_gathered(values).summary(values.size), values, values.size, exact_percentiles=False)

    def test_ndvi_like(self) -> None:
        values = numpy.clip(RNG.normal(0.35, 0.3, 500 * 500), -1, 1).astype("float32")
        summary = _gathered(values).summary(values.size)
        _assert_independent(summary, values, values.size, exact_percentiles=False)
        assert -1 <= summary["percentile_2"] < 0 < summary["percentile_98"] <= 1

    @pytest.mark.parametrize("dtype", ["uint8", "uint16", "int16", "uint32", "int32", "float32", "float64"])
    def test_every_output_type(self, dtype: str) -> None:
        info = numpy.iinfo(dtype) if numpy.dtype(dtype).kind in "iu" else None
        if info is None:
            values = RNG.normal(-50.0, 400.0, 300_000).astype(dtype)
        else:
            values = RNG.integers(int(info.min), int(info.max), 300_000, endpoint=True, dtype=dtype)
        summary = _gathered(values, block=70_000).summary(values.size)
        exact = info is not None and numpy.dtype(dtype).itemsize <= 2
        if dtype in ("uint32", "int32"):
            # Through float32 on the way into the histogram, then outwards to whole numbers (plan §6.2).
            for percent, outward in ((2, -1), (98, 1)):
                true = float(numpy.percentile(values.astype(numpy.float64), percent, method="inverted_cdf"))
                reported = summary[f"percentile_{percent}"]
                assert isinstance(reported, int)
                assert 0 <= (reported - true) * outward <= abs(true) * BIN * 1.01
            summary = {key: value for key, value in summary.items() if not key.startswith("percentile")}
            assert summary["mean"] == _exact_mean(values) and summary["count"] == values.size
        else:
            _assert_independent(summary, values, values.size, exact_percentiles=exact)


class TestDeterminism:
    def test_another_blocking_and_order_give_the_same_values(self) -> None:
        values = _dem(600).ravel()
        one = _gathered(values, block=1024).summary(values.size)
        other = _gathered(values, block=333, reverse=True).summary(values.size)
        assert {k: v for k, v in one.items() if k != "stddev"} == {k: v for k, v in other.items() if k != "stddev"}
        assert other["stddev"] == pytest.approx(one["stddev"], rel=1e-12)

    def test_computed_twice_the_same_bits(self) -> None:
        values = numpy.clip(RNG.normal(0.2, 0.4, 400_000), -1, 1).astype("float32")
        first, second = (json.dumps(_gathered(values).summary(values.size)) for _ in range(2))
        assert first == second

    def test_the_mean_is_exact_where_a_float_sum_is_not(self) -> None:
        values = numpy.array([1e20, 1.0, -1e20], dtype="float64")
        assert float(values.sum()) == 0.0  # what a float64 sum makes of it
        assert _gathered(values).summary(3)["mean"] == 1 / 3

    def test_merging_summaries_is_adding_their_values(self) -> None:
        values = RNG.normal(10.0, 3.0, 50_000).astype("float32")
        merged = BandStatistics("float32")
        for part in numpy.array_split(values, 7):
            merged.merge(summarize(part))
        assert merged.summary(values.size) == _gathered(values, block=values.size).summary(values.size) | {
            "stddev": merged.summary(values.size)["stddev"]
        }


class TestOutwardsAcrossTypes:
    """Through float32 on the way into the histogram, nothing may move inwards (review M4-32a)."""

    @pytest.mark.parametrize(
        ("dtype", "value"),
        [
            ("int32", 2**25 - 1),  # rounds up to 2^25, the lower edge of a bin
            ("uint32", 2**32 - 1),
            ("float64", 2 - 2**-40),  # rounds up to 2.0
            ("float64", 1e300),  # beyond float32
            ("float64", -1e300),
            ("float64", -(2 - 2**-40)),
        ],
    )
    def test_a_constant_band_has_p2_equal_to_p98_equal_to_the_value(self, dtype: str, value: float) -> None:
        summary = _gathered(numpy.full(1000, value, dtype=dtype)).summary(1000)
        assert summary["percentile_2"] == summary["percentile_98"] == summary["minimum"] == value

    @pytest.mark.parametrize("dtype", ["int32", "uint32", "float64"])
    def test_values_near_bin_edges_stay_inside_the_reported_range(self, dtype: str) -> None:
        if dtype == "float64":
            edges = 2.0 ** RNG.integers(-20, 40, 2000)
            values = (edges * (1 + RNG.choice([-1, 1], 2000) * 2.0**-35)).astype("float64")
        else:
            edges = 2 ** RNG.integers(25, 31, 2000)
            values = (edges + RNG.integers(-3, 4, 2000)).astype(dtype)
        summary = _gathered(values).summary(values.size)
        low = float(numpy.percentile(values.astype(numpy.float64), 2, method="inverted_cdf"))
        high = float(numpy.percentile(values.astype(numpy.float64), 98, method="inverted_cdf"))
        assert summary["percentile_2"] <= low <= high <= summary["percentile_98"]

    def test_no_negative_zero_from_a_bin_edge(self) -> None:
        summary = _gathered(numpy.array([-1e-30, 0.0, 0.0], dtype="float32")).summary(3)
        assert math.copysign(1.0, summary["percentile_98"]) == 1.0


class TestEdges:
    def test_no_valid_value(self) -> None:
        statistics = BandStatistics("float32")
        statistics.add(numpy.array([numpy.nan, numpy.nan], dtype="float32"))
        statistics.add(numpy.array([], dtype="float32"))
        summary = statistics.summary(16)
        assert summary == {"count": 0, "valid_percent": 0.0}
        assert gdal_tags(summary) == {"STATISTICS_VALID_PERCENT": "0.0"}

    def test_a_constant_band(self) -> None:
        summary = _gathered(numpy.full(5000, 7.25, dtype="float32")).summary(5000)
        assert summary["minimum"] == summary["maximum"] == summary["mean"] == 7.25
        assert summary["percentile_2"] == summary["percentile_98"] == 7.25
        assert summary["stddev"] == 0.0

    def test_only_negative_values(self) -> None:
        values = -numpy.abs(RNG.normal(500.0, 100.0, 20_000)).astype("float32") - 1
        _assert_independent(_gathered(values).summary(values.size), values, values.size, exact_percentiles=False)

    def test_infinities_do_not_count(self) -> None:
        values = numpy.array([1.0, numpy.inf, 2.0, -numpy.inf, 3.0], dtype="float32")
        summary = _gathered(values).summary(5)
        assert (summary["count"], summary["minimum"], summary["maximum"], summary["mean"]) == (3, 1.0, 3.0, 2.0)

    def test_subnormal_values(self) -> None:
        tiny = numpy.finfo("float32").smallest_subnormal
        values = numpy.array([tiny, 3 * tiny, 0.0, -tiny], dtype="float32")
        summary = _gathered(values).summary(4)
        assert summary["mean"] == float(Fraction(float(tiny)) * 3 / 4)
        assert summary["minimum"] == -float(tiny) and summary["maximum"] == 3 * float(tiny)

    def test_huge_values_give_json_without_infinity(self) -> None:
        values = numpy.array([1e300, -1e300, 5e299], dtype="float64")
        summary = _gathered(values).summary(3)
        assert summary["mean"] == float(Fraction(5e299) / 3)
        assert "stddev" not in summary  # the squares overflow; better none than `inf`
        json.dumps(summary, allow_nan=False)

    def test_the_tags_read_back_as_the_same_numbers(self) -> None:
        summary = _gathered(_dem(300).ravel()).summary(300 * 300)
        tags = gdal_tags(summary)
        assert set(tags) == {
            "STATISTICS_MINIMUM",
            "STATISTICS_MAXIMUM",
            "STATISTICS_MEAN",
            "STATISTICS_STDDEV",
            "STATISTICS_VALID_PERCENT",
            "EARTHX_PERCENTILE_2",
            "EARTHX_PERCENTILE_98",
        }
        assert float(tags["STATISTICS_MEAN"]) == summary["mean"]
        assert float(tags["EARTHX_PERCENTILE_98"]) == summary["percentile_98"]


class TestMisuse:
    @pytest.mark.parametrize("dtype", ["int64", "uint64", "float16", "bool", "complex64"])
    def test_a_type_without_statistics(self, dtype: str) -> None:
        with pytest.raises(TypeError, match="no statistics"):
            BandStatistics(dtype)
        with pytest.raises(TypeError, match="no statistics"):
            summarize(numpy.zeros(4, dtype=dtype))

    def test_a_block_not_flattened(self) -> None:
        with pytest.raises(ValueError, match="one dimension"):
            summarize(numpy.zeros((2, 2), dtype="float32"))

    def test_a_summary_of_another_type(self) -> None:
        with pytest.raises(ValueError, match="does not merge"):
            BandStatistics("float32").merge(summarize(numpy.zeros(4, dtype="uint16")))

    def test_no_pixels_or_more_values_than_pixels(self) -> None:
        statistics = _gathered(numpy.arange(10, dtype="float32"))
        with pytest.raises(ValueError, match="at least one pixel"):
            statistics.summary(0)
        with pytest.raises(ValueError, match="more valid values"):
            statistics.summary(9)

    def test_nothing_in_the_summary_is_nan(self) -> None:
        summary = _gathered(numpy.array([0.5], dtype="float32")).summary(1)
        assert all(math.isfinite(value) for value in summary.values())
