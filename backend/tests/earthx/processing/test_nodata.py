"""``processing.nodata``: the nodata of a result never equals a real value (plan M5-28, Otto 11.11.2026).

R1 float: NaN. R2 integer: the source's nodata where the steps only pass the source's integers on. R3 otherwise an edge
of the type, ``max`` unsigned and ``min`` signed (``gdal_calc.py``'s side). F7: a source nodata the type cannot hold is
refused. R4: a valid value on the nodata moves one step towards the middle, as GDAL's ``AvoidNoData``.
"""

from __future__ import annotations

import math

import numpy
import pytest

from earthx.processing.errors import UnsupportedRecipe
from earthx.processing.nodata import avoid_nodata, edge, output_nodata
from earthx.processing.operators import BandMeta

INTEGERS = ["uint8", "uint16", "int16", "uint32", "int32"]


def _band(data_type: str = "uint16", nodata: float | None = 0.0, name: str = "b") -> BandMeta:
    return BandMeta(name=name, data_type=data_type, nodata=nodata)


class TestEdge:
    @pytest.mark.parametrize(
        ("dtype", "value"),
        [("uint8", 255), ("uint16", 65535), ("uint32", 4294967295), ("int16", -32768), ("int32", -2147483648)],
    )
    def test_the_top_of_an_unsigned_type_and_the_bottom_of_a_signed_one(self, dtype: str, value: int) -> None:
        assert edge(dtype) == value

    @pytest.mark.parametrize("dtype", INTEGERS)
    def test_zero_is_never_the_edge_so_0_degrees_0_mm_and_0_m_stay_values(self, dtype: str) -> None:
        assert edge(dtype) != 0


class TestOutputNodata:
    @pytest.mark.parametrize("dtype", ["float32", "float64"])
    def test_a_float_type_takes_nan_whatever_the_source_says(self, dtype: str) -> None:
        assert math.isnan(output_nodata(dtype, [_band("float32", -9999.0)], passes_values=True))
        assert math.isnan(output_nodata(dtype, [_band("float32", None)], passes_values=False))

    def test_an_integer_type_keeps_the_source_nodata_where_the_steps_only_pass_values(self) -> None:
        assert output_nodata("uint8", [_band("uint8", 0.0)], passes_values=True) == 0.0
        assert output_nodata("uint8", [_band("uint16", 0.0), _band("uint16", 0.0, "c")], passes_values=True) == 0.0

    @pytest.mark.parametrize(
        ("bands", "passes"),
        [
            ([_band("uint16", 0.0)], False),  # interpolation, band math, normalize
            ([_band("float32", 0.0)], True),  # scaled by the core, or a float source: rounding makes new values
            ([_band("uint16", None)], True),  # no source nodata
            ([_band("uint16", 0.0), _band("uint16", 1.0, "c")], True),  # bands disagree; a GeoTIFF has one
            ([_band("uint16", 0.0), _band("float32", math.nan, "c")], True),  # a band of band math beside a source band
            ([_band("uint16", 0.0), _band("uint16", None, "c")], True),
        ],
    )
    def test_otherwise_an_integer_type_takes_its_edge(self, bands: list[BandMeta], passes: bool) -> None:
        assert output_nodata("uint16", bands, passes_values=passes) == 65535.0
        assert output_nodata("int16", bands, passes_values=passes) == -32768.0

    def test_after_band_math_an_integer_type_is_taken_with_its_edge(self) -> None:
        assert output_nodata("int16", [_band("float32", math.nan)], passes_values=False) == -32768.0

    @pytest.mark.parametrize(
        ("dtype", "nodata"),
        [("uint16", -9999.0), ("uint8", 256.0), ("int16", 40000.0), ("uint16", 0.5), ("int32", math.inf)],
    )
    def test_a_source_nodata_the_type_cannot_hold_is_refused_with_the_reason(self, dtype: str, nodata: float) -> None:
        with pytest.raises(UnsupportedRecipe, match=f"nodata .* does not fit the output type {dtype}"):
            output_nodata(dtype, [_band("float32", nodata)], passes_values=False)

    def test_the_refusal_comes_first_even_beside_a_band_that_fits(self) -> None:
        with pytest.raises(UnsupportedRecipe, match="-9999 does not fit"):
            output_nodata("uint16", [_band("uint16", 0.0), _band("float32", -9999.0, "h")], passes_values=True)

    def test_a_type_that_is_neither_float_nor_integer_is_refused(self) -> None:
        with pytest.raises(UnsupportedRecipe, match="no nodata for the output type complex64"):
            output_nodata("complex64", [_band()], passes_values=True)

    def test_no_bands_give_the_edge(self) -> None:
        assert output_nodata("uint8", [], passes_values=True) == 255.0


class TestAvoidNodata:
    def test_a_valid_value_on_the_nodata_moves_down_by_one_and_is_counted_per_band(self) -> None:
        values = numpy.array([[[65535, 65534, 7]], [[65535, 65535, 1]]], dtype="uint16")
        valid = numpy.ones(values.shape, bool)
        assert avoid_nodata(values, valid, 65535.0) == [1, 2]
        assert values.tolist() == [[[65534, 65534, 7]], [[65534, 65534, 1]]]

    def test_at_the_bottom_of_the_type_it_moves_up(self) -> None:
        values = numpy.array([[[-32768, 0]]], dtype="int16")
        assert avoid_nodata(values, numpy.ones(values.shape, bool), -32768.0) == [1]
        assert values.tolist() == [[[-32767, 0]]]

    def test_a_source_nodata_in_the_middle_moves_down(self) -> None:
        values = numpy.array([[[0, 1]]], dtype="int16")
        assert avoid_nodata(values, numpy.ones(values.shape, bool), 0.0) == [1]
        assert values.tolist() == [[[-1, 1]]]

    def test_a_masked_pixel_stays_where_it_is(self) -> None:
        values = numpy.array([[[255, 255]]], dtype="uint8")
        valid = numpy.array([[[False, True]]])
        assert avoid_nodata(values, valid, 255.0) == [1]
        assert values.tolist() == [[[255, 254]]]

    def test_nothing_to_move_leaves_the_values(self) -> None:
        values = numpy.array([[[1, 2]]], dtype="uint8")
        assert avoid_nodata(values, numpy.ones(values.shape, bool), 255.0) == [0]
        assert values.tolist() == [[[1, 2]]]
