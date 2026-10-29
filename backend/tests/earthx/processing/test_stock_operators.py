"""``band_math``, ``mask`` and ``normalize`` in version 2: they work on a stock of named bands (adr/0020 §4, §6)."""

from __future__ import annotations

import numpy
import pytest
from pydantic import ValidationError
from rasterio.transform import from_origin
from rio_tiler.models import ImageData

from earthx.processing.errors import RecipeInvalid
from earthx.processing.operators import (
    BAND_MATH,
    BAND_MATH_V2,
    MASK,
    MASK_V2,
    NORMALIZE,
    NORMALIZE_V2,
    BandMeta,
    RasterMeta,
)
from earthx.processing.operators.band_math import BandMathParamsV2, check_name, replace_name
from earthx.processing.operators.mask import MaskParams
from earthx.processing.operators.normalize import NormalizeParams, NormalizeParamsV2

BOUNDS = (0.0, 0.0, 4.0, 4.0)


def _image(**bands: numpy.ndarray) -> ImageData:
    """Bands as ``float32`` arrays of 4 × 4; a ``numpy.ma.masked`` entry masks a pixel."""
    stack = numpy.ma.stack([numpy.ma.asarray(array, dtype="float32") for array in bands.values()])
    return ImageData(stack, bounds=BOUNDS, crs="EPSG:32632", band_names=list(bands))


def _meta(*bands: BandMeta) -> RasterMeta:
    return RasterMeta("EPSG:32632", from_origin(0, 4, 1, 1), 4, 4, bands)


def _band(name: str, **options) -> BandMeta:
    return BandMeta(name, "float32", float("nan"), **options)


def _ramp(offset: float) -> numpy.ndarray:
    return numpy.arange(16, dtype="float32").reshape(4, 4) + numpy.float32(offset)


class TestTheNameOfANewBand:
    @pytest.mark.parametrize("name", ["NDVI", "ndvi_2", "Band_Math_1", "a", "x" * 32])
    def test_a_name_that_fits_is_taken(self, name: str) -> None:
        check_name(name)
        BandMathParamsV2.model_validate_json(f'{{"expression": "red + nir", "name": "{name}"}}', strict=True)

    @pytest.mark.parametrize(
        ("name", "reason"),
        [
            ("1st", "a letter, then letters"),
            ("_x", "a letter, then letters"),
            ("my band", "a letter, then letters"),
            ("NDVI-2", "a letter, then letters"),
            ("x" * 33, "at most 32 characters"),
            ("NDVI\n", "a letter, then letters"),
            ("in", "Python keyword"),
            ("True", "Python keyword"),
            ("not", "Python keyword"),
            ("where", "is a function"),
            ("sqrt", "is a function"),
        ],
    )
    def test_a_name_that_an_expression_could_not_use_is_refused_with_the_reason(self, name: str, reason: str) -> None:
        with pytest.raises(ValueError, match=reason):
            check_name(name)

    def test_the_name_is_part_of_the_parameters_and_never_left_to_a_default(self) -> None:
        with pytest.raises(ValidationError, match="name"):
            BandMathParamsV2.model_validate_json('{"expression": "red + nir"}', strict=True)

    def test_a_word_inside_a_longer_name_or_a_number_is_not_renamed(self) -> None:
        assert replace_name("band_math2 + band_math * 1e5 - xband_math", "band_math", "NDVI") == (
            "band_math2 + NDVI * 1e5 - xband_math"
        )


class TestBandMathVersion2:
    def test_the_result_is_a_band_beside_the_others(self) -> None:
        image = _image(red=_ramp(1), nir=_ramp(5))
        result = BAND_MATH_V2.run(image, BandMathParamsV2(expression="(nir - red) / (nir + red)", name="NDVI"))
        assert list(result.band_names) == ["red", "nir", "NDVI"]
        numpy.testing.assert_array_equal(numpy.ma.getdata(result.array[:2]), numpy.ma.getdata(image.array))
        expected = ((_ramp(5).astype("float64") - _ramp(1)) / (_ramp(5).astype("float64") + _ramp(1))).astype("float32")
        numpy.testing.assert_array_equal(numpy.ma.getdata(result.array[2]), expected)

    def test_it_gives_the_values_version_1_gave(self) -> None:
        image = _image(red=_ramp(0), nir=_ramp(3))
        old = BAND_MATH.run(image, BAND_MATH.params(expression="nir / red"))
        new = BAND_MATH_V2.run(image, BandMathParamsV2(expression="nir / red", name="Ratio"))
        assert numpy.ma.getdata(old.array[0]).tobytes() == numpy.ma.getdata(new.array[2]).tobytes()
        assert numpy.ma.getmaskarray(old.array[0]).tobytes() == numpy.ma.getmaskarray(new.array[2]).tobytes()

    def test_a_pixel_is_masked_where_a_band_it_names_is_and_where_the_result_is_not_finite(self) -> None:
        red = numpy.ma.masked_array(_ramp(1), mask=numpy.zeros((4, 4), bool))
        red.mask[0, 0] = True
        image = _image(red=red, nir=_ramp(0), unused=numpy.ma.masked_all((4, 4)))
        result = BAND_MATH_V2.run(image, BandMathParamsV2(expression="red / nir", name="Q"))
        added = result.array[3]
        assert added.mask[0, 0] and added.mask[0, 0] == numpy.ma.getmaskarray(result.array[0])[0, 0]  # masked in both
        assert added.mask[0, 0]  # nir is 0 at [0, 0]: 0/0 would be NaN anyway
        assert not added.mask[1, 1]
        assert numpy.ma.getmaskarray(result.array[2]).all()  # the band nobody named keeps its own mask

    def test_the_stock_keeps_a_type_that_holds_every_band(self) -> None:
        classes = numpy.ma.masked_array(numpy.full((4, 4), 4, dtype="uint8"))
        stock = numpy.ma.stack([numpy.ma.asarray(_ramp(1)), classes])
        image = ImageData(stock, bounds=BOUNDS, crs="EPSG:32632", band_names=["red", "scl"])
        result = BAND_MATH_V2.run(image, BandMathParamsV2(expression="red * 2", name="Twice"))
        assert result.array.dtype == numpy.float32
        assert list(numpy.ma.getdata(result.array[1]).ravel()) == [4.0] * 16

    def test_an_unknown_band_is_named_with_what_the_stock_has(self) -> None:
        meta = _meta(_band("red"), _band("nir"))
        with pytest.raises(RecipeInvalid, match=r"unknown band\(s\): swir; the input has: red, nir"):
            BAND_MATH_V2.transform(meta, BandMathParamsV2(expression="swir - red", name="X"))

    @pytest.mark.parametrize("taken", ["red", "RED", "Red"])
    def test_a_name_that_the_stock_has_already_is_refused_in_any_case(self, taken: str) -> None:
        meta = _meta(_band("red"), _band("nir"))
        with pytest.raises(RecipeInvalid, match=f"{taken} is used twice"):
            BAND_MATH_V2.transform(meta, BandMathParamsV2(expression="nir - red", name=taken))

    def test_the_meta_has_the_bands_and_the_new_one_float32_with_nan(self) -> None:
        meta = _meta(_band("red", unit="1"), _band("nir", unit="1"))
        out = BAND_MATH_V2.transform(meta, BandMathParamsV2(expression="nir - red", name="Diff"))
        assert [band.name for band in out.bands] == ["red", "nir", "Diff"]
        assert out.bands[2].data_type == "float32" and numpy.isnan(out.bands[2].nodata)
        assert out.bands[2].unit is None  # a formula has no known unit

    def test_the_bare_name_of_a_band_is_that_band_again_with_its_unit(self) -> None:
        meta = _meta(_band("red", unit="W/m2"))
        out = BAND_MATH_V2.transform(meta, BandMathParamsV2(expression="red", name="Copy"))
        assert out.bands[1].unit == "W/m2"

    def test_a_result_is_resampled_where_a_band_it_used_was(self) -> None:
        meta = _meta(_band("red"), _band("swir", resampled=True), _band("nir"))
        near = BAND_MATH_V2.transform(meta, BandMathParamsV2(expression="nir - red", name="Near"))
        far = BAND_MATH_V2.transform(meta, BandMathParamsV2(expression="nir - swir", name="Far"))
        assert [band.resampled for band in near.bands][3] is False
        assert [band.resampled for band in far.bands][3] is True

    def test_it_says_which_bands_it_reads_and_which_it_adds(self) -> None:
        use = BAND_MATH_V2.bands_used(BandMathParamsV2(expression="(nir - red) / (nir + red)", name="NDVI"))
        assert (use.reads, use.adds, use.acts_on) == (frozenset({"nir", "red"}), "NDVI", None)

    def test_version_1_still_replaces_everything_and_is_no_step_of_a_stock(self) -> None:
        assert not BAND_MATH.stock and BAND_MATH_V2.stock
        assert not BAND_MATH_V2.listed and BAND_MATH.listed


class TestMaskVersion2:
    def _image(self) -> ImageData:
        classes = numpy.zeros((4, 4), dtype="float32")
        classes[0, 0], classes[1, 1], classes[2, 2] = 3, 8, 4
        return _image(red=_ramp(1), scl=classes)

    def test_every_band_is_masked_where_the_layer_holds_a_class_and_the_layer_stays(self) -> None:
        result = MASK_V2.run(self._image(), MaskParams(source="scl", classes=[3, 8]))
        assert list(result.band_names) == ["red", "scl"]
        for band in (0, 1):
            masked = numpy.ma.getmaskarray(result.array[band])
            assert masked[0, 0] and masked[1, 1] and not masked[2, 2] and masked.sum() == 2

    def test_the_values_of_the_other_bands_are_not_touched(self) -> None:
        image = self._image()
        result = MASK_V2.run(image, MaskParams(source="scl", classes=[3]))
        assert numpy.ma.getdata(result.array[0]).tobytes() == numpy.ma.getdata(image.array[0]).tobytes()

    def test_it_hides_what_version_1_hid(self) -> None:
        image = self._image()
        old = MASK.run(image, MaskParams(source="scl", classes=[3, 8]))
        new = MASK_V2.run(image, MaskParams(source="scl", classes=[3, 8]))
        assert numpy.ma.getmaskarray(old.array[0]).tobytes() == numpy.ma.getmaskarray(new.array[0]).tobytes()
        assert numpy.ma.getdata(old.array[0]).tobytes() == numpy.ma.getdata(new.array[0]).tobytes()

    def test_a_stock_of_the_layer_alone_may_be_masked(self) -> None:
        result = MASK_V2.run(_image(scl=self._image().array[1]), MaskParams(source="scl", classes=[3]))
        assert numpy.ma.getmaskarray(result.array[0]).sum() == 1

    def test_the_meta_keeps_every_band(self) -> None:
        meta = _meta(_band("red"), _band("scl"))
        assert MASK_V2.transform(meta, MaskParams(source="scl", classes=[3])) == meta
        assert [band.name for band in MASK.transform(meta, MaskParams(source="scl", classes=[3])).bands] == ["red"]

    def test_a_layer_that_is_not_there_is_named(self) -> None:
        with pytest.raises(RecipeInvalid, match=r"mask source 'scl' is not among the bands: red"):
            MASK_V2.transform(_meta(_band("red")), MaskParams(source="scl", classes=[3]))

    def test_it_reads_the_layer(self) -> None:
        assert MASK_V2.bands_used(MaskParams(source="scl", classes=[3])).reads == {"scl"}


class TestNormalizeVersion2:
    RANGES = {"in_min": 0.0, "in_max": 10.0, "out_min": 0.0, "out_max": 100.0, "clip": True}

    def _params(self, *bands: str) -> NormalizeParamsV2:
        return NormalizeParamsV2(bands=list(bands), **self.RANGES)

    def test_the_bands_named_are_converted_and_the_others_are_left_as_they_are(self) -> None:
        image = _image(red=_ramp(0), nir=_ramp(1))
        result = NORMALIZE_V2.run(image, self._params("red"))
        assert list(result.band_names) == ["red", "nir"]
        assert numpy.ma.getdata(result.array[1]).tobytes() == numpy.ma.getdata(image.array[1]).tobytes()
        assert numpy.ma.getdata(result.array[0])[0, 1] == 10.0 and numpy.ma.getdata(result.array[0])[3, 3] == 100.0

    def test_a_converted_band_is_what_version_1_gave(self) -> None:
        image = _image(red=_ramp(0), nir=_ramp(1))
        old = NORMALIZE.run(image, NormalizeParams(**self.RANGES))
        new = NORMALIZE_V2.run(image, self._params("red", "nir"))
        assert numpy.ma.getdata(old.array).tobytes() == numpy.ma.getdata(new.array).tobytes()
        assert numpy.ma.getmaskarray(old.array).tobytes() == numpy.ma.getmaskarray(new.array).tobytes()

    def test_a_masked_pixel_stays_masked(self) -> None:
        red = numpy.ma.masked_array(_ramp(0), mask=numpy.zeros((4, 4), bool))
        red.mask[2, 2] = True
        result = NORMALIZE_V2.run(_image(red=red, nir=_ramp(1)), self._params("red"))
        assert numpy.ma.getmaskarray(result.array[0])[2, 2] and not numpy.ma.getmaskarray(result.array[1]).any()

    def test_the_meta_converts_only_the_named_bands_and_drops_their_unit(self) -> None:
        meta = _meta(_band("red", unit="1", resampled=True), _band("nir", unit="1"))
        out = NORMALIZE_V2.transform(meta, self._params("red"))
        assert (out.bands[0].unit, out.bands[0].resampled) == (None, True)
        assert out.bands[1] == meta.bands[1]

    def test_an_unknown_band_is_named_with_what_the_stock_has(self) -> None:
        with pytest.raises(RecipeInvalid, match=r"unknown band\(s\): swir; the input has: red"):
            NORMALIZE_V2.transform(_meta(_band("red")), self._params("swir"))

    @pytest.mark.parametrize("bands", [[], ["red", "RED"], ["red", "red"], [""], ["x" * 65]])
    def test_the_bands_are_given_and_each_once(self, bands: list[str]) -> None:
        with pytest.raises(ValidationError):
            NormalizeParamsV2(bands=bands, **self.RANGES)

    def test_bands_are_always_given(self) -> None:
        with pytest.raises(ValidationError, match="bands"):
            NormalizeParamsV2.model_validate_json('{"in_min": 0, "in_max": 1, "out_min": 0, "out_max": 1, "clip": true}')

    def test_it_changes_the_bands_it_names_only(self) -> None:
        use = NORMALIZE_V2.bands_used(self._params("red", "nir"))
        assert (use.reads, use.adds, use.acts_on) == (frozenset(), None, frozenset({"red", "nir"}))
