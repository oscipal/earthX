"""``core._cast``: a float written to an integer type is rounded half away from zero and clamped (M4-26).

The rule is the one of GDAL's ``GDALCopyWords`` (``gcore/gdal_priv_templates.hpp``, read 13.10.2026): add 0.5 to
the magnitude, drop the fraction, clamp to the type. NaN differs on purpose: GDAL writes 0, the core keeps it masked.
"""

from __future__ import annotations

import numpy
import pytest

from earthx.processing.core import _cast

INF = float("inf")


def _cast_values(values: list[float], dtype: str, *, source: str = "float32") -> numpy.ma.MaskedArray:
    return _cast(numpy.ma.MaskedArray(numpy.array([values], dtype=source)), dtype)


@pytest.mark.parametrize("dtype", ["uint8", "uint16", "int16"])
class TestRounding:
    def test_below_half_goes_down_above_half_goes_up(self, dtype: str) -> None:
        result = _cast_values([12.4, 12.6, 100.49, 100.51], dtype)
        assert result.tolist() == [[12, 13, 100, 101]]

    def test_exactly_half_goes_away_from_zero_not_to_even(self, dtype: str) -> None:
        result = _cast_values([0.5, 1.5, 2.5, 3.5], dtype)
        assert result.tolist() == [[1, 2, 3, 4]]

    def test_the_type_is_the_requested_one(self, dtype: str) -> None:
        assert _cast_values([1.0], dtype).dtype == numpy.dtype(dtype)

    def test_values_over_the_range_are_clamped_to_its_maximum(self, dtype: str) -> None:
        top = numpy.iinfo(dtype).max
        result = _cast_values([top + 0.4, top + 1000.0, 1e9, INF], dtype, source="float64")
        assert result.tolist() == [[top] * 4]

    def test_values_under_the_range_are_clamped_to_its_minimum(self, dtype: str) -> None:
        bottom = numpy.iinfo(dtype).min
        result = _cast_values([bottom - 0.4, bottom - 1000.0, -1e9, -INF], dtype, source="float64")
        assert result.tolist() == [[bottom] * 4]

    def test_a_value_just_below_half_stays_below(self, dtype: str) -> None:
        just_below = numpy.nextafter(numpy.float32(0.5), numpy.float32(0))
        assert _cast_values([just_below], dtype).tolist() == [[0]]

    def test_nan_stays_masked_and_the_rest_is_kept(self, dtype: str) -> None:
        result = _cast_values([float("nan"), 7.6], dtype)
        assert result.mask.tolist() == [[True, False]]
        assert result.compressed().tolist() == [8]


def test_a_negative_half_rounds_away_from_zero_in_a_signed_type() -> None:
    assert _cast_values([-0.5, -1.5, -1234.4, -1234.5, -1234.6], "int16").tolist() == [[-1, -2, -1234, -1235, -1235]]


def test_negative_values_clamp_to_zero_in_an_unsigned_type() -> None:
    assert _cast_values([-0.5, -0.4, -3.7], "uint16").tolist() == [[0, 0, 0]]


def test_the_cases_of_the_task_per_type() -> None:
    values = [1234.4, 1234.5, 1234.6, -0.5]
    assert _cast_values(values, "uint16").tolist() == [[1234, 1235, 1235, 0]]
    assert _cast_values(values, "int16").tolist() == [[1234, 1235, 1235, -1]]
    assert _cast_values(values, "uint8").tolist() == [[255, 255, 255, 0]]


def test_an_existing_mask_is_kept() -> None:
    data = numpy.ma.MaskedArray(numpy.array([[1.4, 2.6]], dtype="float64"), mask=[[True, False]])
    result = _cast(data, "uint16")
    assert result.mask.tolist() == [[True, False]]
    assert result.compressed().tolist() == [3]


def test_a_masked_pixel_is_filled_with_nodata() -> None:
    result = _cast_values([float("nan"), 2.5], "uint16")
    assert numpy.ma.filled(result, 65535).tolist() == [[65535, 3]]


@pytest.mark.parametrize("dtype", ["float32", "float64"])
def test_a_float_target_is_not_rounded(dtype: str) -> None:
    assert _cast_values([1234.4, -0.5], dtype, source="float64").tolist() == [[pytest.approx(1234.4), -0.5]]


def test_an_integer_source_is_cast_as_before() -> None:
    data = numpy.ma.MaskedArray(numpy.array([[1, 70000]], dtype="int32"))
    assert _cast(data, "uint16").tolist() == [[1, 70000 - 65536]]
