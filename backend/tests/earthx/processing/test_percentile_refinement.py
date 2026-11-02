"""The exact percentiles of the job: a second look at the values of the bins that hold a wanted rank (NM4-71).

Stage 1 is the histogram of M4-32 (the bin and the rank inside it), stage 2 counts the values of that bin by the lower
16 bits of their float32 pattern. The results are held against ``numpy.percentile(method="inverted_cdf")`` and against
a sort of all the values, the nearest-rank value; for values only float64 holds they are held to the outward rounding of
M4-32. The sizes are odd and not a multiple of 5, so that no rank falls on a whole number and numpy's float arithmetic
has no tie to break.
"""

from __future__ import annotations

import math

import numpy
import pytest

from earthx.processing.statistics import MEASURE_PERCENTILES, PERCENTILES, BandStatistics

ALL = (*MEASURE_PERCENTILES, *PERCENTILES)
SIZE = 99_999


def _counted(values: numpy.ndarray, dtype: str, block: int = 4096) -> BandStatistics:
    statistics = BandStatistics(dtype)
    for start in range(0, values.size, block):
        statistics.add(values[start : start + block])
    return statistics


def _refined(values: numpy.ndarray, dtype: str, percents=ALL, block: int = 4096) -> dict:
    statistics = _counted(values, dtype, block)
    refinement = statistics.refine_targets(percents)
    for start in range(0, values.size, block):
        refinement.add(values[start : start + block])
    return refinement.values()


def _nearest_rank(values: numpy.ndarray, percent: int) -> float:
    ordered = numpy.sort(values[numpy.isfinite(values)] if values.dtype.kind == "f" else values)
    return ordered[max(1, -(-percent * ordered.size // 100)) - 1].item()


def _assert_exact(found: dict, values: numpy.ndarray, percents=ALL) -> None:
    assert sorted(found) == sorted(set(percents))
    for percent in percents:
        assert found[percent] == _nearest_rank(values, percent), percent
        assert found[percent] == float(numpy.percentile(values, percent, method="inverted_cdf")), percent


class TestFloat32IsExact:
    def test_many_values_in_one_bin_give_the_value_and_not_the_edge_of_the_bin(self) -> None:
        """Forty float32 steps around 0.5 all lie in one bin of 2⁻⁷: the histogram alone can only name an edge."""
        values = (0.5 + numpy.random.default_rng(1).integers(0, 40, SIZE) * 2.0**-24).astype("float32")
        found = _refined(values, "float32")
        _assert_exact(found, values)
        coarse = _counted(values, "float32").summary(values.size, MEASURE_PERCENTILES)
        assert any(coarse[f"percentile_{percent}"] != found[percent] for percent in ALL), (
            "the counter sample has no bite"
        )

    def test_a_normal_band(self) -> None:
        values = numpy.random.default_rng(2).normal(0.3, 0.2, SIZE).astype("float32")
        _assert_exact(_refined(values, "float32"), values)

    def test_negative_and_mixed_values(self) -> None:
        values = numpy.random.default_rng(3).normal(0.0, 5.0, SIZE).astype("float32")
        values[::7] *= -1e-3
        _assert_exact(_refined(values, "float32"), values)
        negative = -numpy.abs(values) - 1.0
        _assert_exact(_refined(negative.astype("float32"), "float32"), negative.astype("float32"))

    def test_values_that_repeat_a_lot(self) -> None:
        values = numpy.random.default_rng(4).integers(0, 6, SIZE).astype("float32") / 5
        _assert_exact(_refined(values, "float32"), values)

    def test_the_order_and_the_size_of_the_blocks_do_not_matter(self) -> None:
        values = numpy.random.default_rng(5).gamma(2.0, 0.1, SIZE).astype("float32")
        reference = _refined(values, "float32", block=1000)
        assert _refined(values, "float32", block=70_000) == reference
        statistics = _counted(values, "float32")
        refinement = statistics.refine_targets(ALL)
        for part in numpy.array_split(numpy.random.default_rng(6).permutation(values), 13):
            refinement.add(part)
        assert refinement.values() == reference

    def test_a_constant_band_is_that_constant_for_every_percent(self) -> None:
        values = numpy.full(1001, 0.25, dtype="float32")
        assert set(_refined(values, "float32").values()) == {0.25}

    def test_zero_is_never_negative_zero(self) -> None:
        values = numpy.concatenate([numpy.full(500, -0.0), numpy.full(501, 0.0), numpy.full(1, 1.0)]).astype("float32")
        found = _refined(values, "float32")
        assert all(
            value == 0.0 and math.copysign(1.0, value) == 1.0 for percent, value in found.items() if percent < 99
        )

    def test_a_value_that_is_not_finite_is_skipped_as_the_count_skips_it(self) -> None:
        values = numpy.random.default_rng(7).normal(0.0, 1.0, SIZE).astype("float32")
        values[::50] = numpy.nan
        values[7::333] = numpy.inf
        values[11::777] = -numpy.inf
        finite = values[numpy.isfinite(values)]
        statistics = _counted(values, "float32")
        assert statistics.count == finite.size
        refinement = statistics.refine_targets(ALL)
        refinement.add(values)
        found = refinement.values()
        for percent in ALL:
            assert found[percent] == _nearest_rank(finite, percent)

    def test_the_ends_of_the_float32_range(self) -> None:
        top = numpy.finfo("float32").max
        values = numpy.concatenate([numpy.full(300, top), numpy.full(300, -top), numpy.zeros(399)]).astype("float32")
        found = _refined(values, "float32")
        assert found[1] == -top and found[99] == top and found[50] == 0.0


class TestFloat64:
    def test_values_a_float32_holds_are_exact_in_a_float64_band_too(self) -> None:
        """The work file is float64; what a float32 source made of it stays exact (no step up for the upper percents)."""
        values = numpy.random.default_rng(8).normal(0.4, 0.1, SIZE).astype("float32").astype("float64")
        _assert_exact(_refined(values, "float64"), values)

    def test_a_value_only_float64_holds_is_rounded_outwards_to_float32(self) -> None:
        values = numpy.random.default_rng(9).uniform(0.0, 1.0, SIZE)
        found = _refined(values, "float64")
        for percent in ALL:
            true = _nearest_rank(values, percent)
            step = abs(float(numpy.spacing(numpy.float32(true))))
            if percent <= 50:
                assert true - step < found[percent] <= true, percent
            else:
                assert true <= found[percent] < true + step, percent

    def test_a_mixture_of_the_two_stays_inside_one_step(self) -> None:
        values = numpy.random.default_rng(10).normal(0.0, 1.0, SIZE)
        values[::2] = values[::2].astype("float32")
        found = _refined(values, "float64")
        for percent in ALL:
            true = _nearest_rank(values, percent)
            assert abs(found[percent] - true) <= abs(float(numpy.spacing(numpy.float32(true)))), percent

    def test_the_range_of_the_band_limits_the_result(self) -> None:
        values = numpy.random.default_rng(11).uniform(0.1, 0.2, SIZE)
        found = _refined(values, "float64")
        assert all(values.min() <= value <= values.max() for value in found.values())

    def test_a_value_beyond_float32_is_the_minimum_or_the_maximum(self) -> None:
        values = numpy.concatenate([numpy.full(300, 1e300), numpy.full(300, -1e300), numpy.zeros(399)])
        found = _refined(values, "float64")
        assert found[1] == -1e300 and found[99] == 1e300


class TestIntegers:
    @pytest.mark.parametrize("dtype", ["uint8", "int8", "uint16", "int16"])
    def test_up_to_sixteen_bits_stage_one_is_exact_and_nothing_is_to_be_seen_again(self, dtype: str) -> None:
        info = numpy.iinfo(dtype)
        values = numpy.random.default_rng(12).integers(info.min, info.max + 1, SIZE).astype(dtype)
        statistics = _counted(values, dtype)
        refinement = statistics.refine_targets(ALL)
        assert refinement.needed is False
        refinement.add(values)  # a no-op, not an error
        found = refinement.values()
        _assert_exact(found, values)
        assert all(isinstance(value, int) for value in found.values())

    def test_int32_below_two_to_the_24th_is_exact(self) -> None:
        values = numpy.random.default_rng(13).integers(-5_000_000, 5_000_000, SIZE).astype("int32")
        found = _refined(values, "int32")
        _assert_exact(found, values)
        assert all(isinstance(value, int) for value in found.values())

    def test_int32_beyond_two_to_the_24th_is_a_whole_number_rounded_outwards(self) -> None:
        values = numpy.random.default_rng(14).integers(2**26, 2**28, SIZE).astype("int32")
        found = _refined(values, "int32")
        for percent in ALL:
            true = _nearest_rank(values, percent)
            assert (found[percent] <= true) if percent <= 50 else (found[percent] >= true), percent
            assert abs(found[percent] - true) <= 2**5, percent  # a float32 step at 2²⁸ is 2⁵
            assert isinstance(found[percent], int)
        assert values.min() <= min(found.values()) and max(found.values()) <= values.max()


class TestMisuse:
    def _statistics(self) -> tuple[BandStatistics, numpy.ndarray]:
        values = numpy.random.default_rng(15).normal(0.0, 1.0, 5001).astype("float32")
        return _counted(values, "float32"), values

    @pytest.mark.parametrize("percent", [0, 100, -1, 101])
    def test_a_percent_outside_one_to_ninety_nine_is_refused(self, percent: int) -> None:
        statistics, _ = self._statistics()
        with pytest.raises(ValueError, match="whole percent from 1 to 99"):
            statistics.refine_targets([50, percent])

    def test_a_band_without_a_value_has_no_percentiles(self) -> None:
        with pytest.raises(ValueError, match="without a valid value"):
            BandStatistics("float32").refine_targets([50])

    def test_values_that_are_not_the_ones_counted_are_noticed(self) -> None:
        statistics, values = self._statistics()
        refinement = statistics.refine_targets([2, 50, 98])
        median = float(numpy.sort(values)[values.size // 2])
        refinement.add(values[values != median])  # the check sees the bins that hold a wanted rank
        with pytest.raises(ValueError, match="not the values the statistics counted"):
            refinement.values()
        again = statistics.refine_targets([50])
        again.add(numpy.concatenate([values, numpy.full(3, median, dtype="float32")]))
        with pytest.raises(ValueError, match="not the values the statistics counted"):
            again.values()

    def test_values_of_another_type_or_shape_are_refused(self) -> None:
        statistics, values = self._statistics()
        refinement = statistics.refine_targets([50])
        with pytest.raises(ValueError, match="do not belong"):
            refinement.add(values.astype("float64"))
        with pytest.raises(ValueError, match="one dimension"):
            refinement.add(values.reshape(1, -1))

    def test_no_percent_at_all_asks_for_nothing(self) -> None:
        statistics, values = self._statistics()
        refinement = statistics.refine_targets([])
        assert refinement.needed is False and refinement.values() == {}
        refinement.add(values)

    def test_a_percent_twice_is_one_value(self) -> None:
        statistics, values = self._statistics()
        refinement = statistics.refine_targets([50, 50, 25])
        refinement.add(values)
        assert list(refinement.values()) == [25, 50]
