"""The index presets against the formula of their source and against ``band_math`` (NM4-14 plan §10 points 1, 2, 6).

Nothing here reads a file: the kernel runs on arrays, the check on the registry.
"""

from __future__ import annotations

import ast
from dataclasses import replace
from fractions import Fraction

import numpy
import pytest
from rio_tiler.models import ImageData

from earthx.catalog.datasets import COP_DEM_GLO_30, REGISTRY, SENTINEL_2_L2A
from earthx.catalog.registry import DatasetRegistry, IndexPreset
from earthx.processing.index_presets import IndexPresetMismatch, check_index_presets
from earthx.processing.operators import BAND_MATH_V2
from earthx.processing.operators.band_math import BandMathParamsV2

PRESETS = {preset.name: preset for preset in SENTINEL_2_L2A.index_presets}

#: Physical reflectance of one pixel, chosen so that every index has a value well inside −1…1.
REFLECTANCE = {"blue": "0.05", "green": "0.08", "red": "0.06", "nir": "0.40", "swir16": "0.20", "swir22": "0.10"}

#: Each index worked out by hand on :data:`REFLECTANCE`, as exact fractions.
_R = {band: Fraction(value) for band, value in REFLECTANCE.items()}
BY_HAND = {
    "NDVI": (_R["nir"] - _R["red"]) / (_R["nir"] + _R["red"]),  # 17/23
    "NDWI": (_R["green"] - _R["nir"]) / (_R["green"] + _R["nir"]),  # -2/3
    "NDSI": (_R["green"] - _R["swir16"]) / (_R["green"] + _R["swir16"]),  # -3/7
    "NBR": (_R["nir"] - _R["swir22"]) / (_R["nir"] + _R["swir22"]),  # 3/5
    "EVI": Fraction(5, 2)
    * (_R["nir"] - _R["red"])
    / (_R["nir"] + 6 * _R["red"] - Fraction(15, 2) * _R["blue"] + 1),  # 170/277
}

#: Awesome Spectral Indices' symbols on the bands of Sentinel-2 at Earth Search (`bands.json`: N is B8, S1 is B11, S2 is
#: B12) and its constants (`constants.json`, commit 835fea7). Only this test knows the mapping (plan §10 point 2).
ASI_BANDS = {"N": "nir", "R": "red", "G": "green", "B": "blue", "S1": "swir16", "S2": "swir22"}
ASI_CONSTANTS = {"g": Fraction(5, 2), "C1": Fraction(6), "C2": Fraction(15, 2), "L": Fraction(1)}


def _image(values: dict[str, float]) -> ImageData:
    bands = list(values)
    data = numpy.ma.masked_array(numpy.array([[[values[band]]] for band in bands], dtype="float64"))
    return ImageData(data, bounds=(0, 0, 1, 1), crs="EPSG:32632", band_names=bands)


def _computed(preset: IndexPreset) -> numpy.float32:
    image = _image({band: float(value) for band, value in REFLECTANCE.items()})
    result = BAND_MATH_V2.run(image, BandMathParamsV2(expression=preset.expression, name=preset.name))
    assert result.band_names[-1] == preset.name
    return result.array[-1].data[0, 0]


def _exact(formula: str, symbols: dict[str, Fraction]) -> Fraction:
    """``formula`` in exact arithmetic: only names, numbers and + - * / with brackets, as in the catalogue."""

    def value(node: ast.expr) -> Fraction:
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            return Fraction(str(node.value))
        if isinstance(node, ast.Name):
            return symbols[node.id]
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            return -value(node.operand)
        if isinstance(node, ast.BinOp):
            left, right = value(node.left), value(node.right)
            operations = {ast.Add: left.__add__, ast.Sub: left.__sub__, ast.Mult: left.__mul__, ast.Div: left.__truediv__}
            return operations[type(node.op)](right)
        raise AssertionError(f"{ast.dump(node)} is not in a catalogue formula")

    return value(ast.parse(formula, mode="eval").body)


class TestReferenceValues:
    @pytest.mark.parametrize("name", list(BY_HAND))
    def test_the_kernel_gives_the_value_worked_out_by_hand(self, name: str) -> None:
        assert _computed(PRESETS[name]) == numpy.float32(float(BY_HAND[name]))

    def test_every_preset_of_sentinel_2_has_a_value_by_hand(self) -> None:
        assert set(PRESETS) == set(BY_HAND)

    @pytest.mark.parametrize("name", list(BY_HAND))
    def test_the_expression_is_the_formula_of_the_catalogue(self, name: str) -> None:
        """Copying ``nir08`` for ``nir`` or 7 for 7.5 would show here, on any reflectance."""
        preset = PRESETS[name]
        symbols = {**ASI_CONSTANTS, **{symbol: _R[band] for symbol, band in ASI_BANDS.items()}}
        assert _exact(preset.formula, symbols) == BY_HAND[name]
        bands = {band: _R[band] for band in REFLECTANCE}
        assert _exact(preset.expression, bands) == BY_HAND[name]

    @pytest.mark.parametrize("name", ["NDVI", "NDWI", "NDSI", "NBR"])
    def test_a_normalized_difference_of_reflectance_from_0_to_1_stays_inside_its_range(self, name: str) -> None:
        rng = numpy.random.default_rng(14)
        values = {band: rng.uniform(0.0, 1.0, (64, 64)) for band in REFLECTANCE}
        data = numpy.ma.masked_array(numpy.stack(list(values.values())))
        image = ImageData(data, bounds=(0, 0, 1, 1), crs="EPSG:32632", band_names=list(values))
        preset = PRESETS[name]
        result = BAND_MATH_V2.run(image, BandMathParamsV2(expression=preset.expression, name=name)).array[-1]
        low, high = preset.rescale
        assert low <= result.min() and result.max() <= high

    def test_a_dark_pixel_is_masked_instead_of_dividing_by_zero(self) -> None:
        image = _image({"red": 0.0, "nir": 0.0})
        result = BAND_MATH_V2.run(image, BandMathParamsV2(expression=PRESETS["NDVI"].expression, name="NDVI"))
        assert result.array[-1].mask[0, 0]


class TestTheCheckAtTheStart:
    def test_the_registry_of_the_platform_passes(self) -> None:
        check_index_presets(REGISTRY)

    @pytest.mark.parametrize(
        ("change", "reason"),
        [
            ({"expression": "log(nir) - red"}, "the functions are"),
            ({"expression": "nir ** 0.5 - red"}, "the exponent of"),
            ({"expression": "~nir"}, "needs a truth value"),
            ({"expression": "(nir - red"}, "not a valid expression"),
            ({"expression": "nir if red else blue"}, "IfExp is not allowed"),
            ({"name": "where"}, "is a function"),
            ({"name": "True"}, "Python keyword"),
            ({"colormap_name": "rainbow_unicorn"}, "knows no colormap 'rainbow_unicorn'"),
        ],
    )
    def test_a_preset_band_math_or_the_tiler_would_refuse_stops_the_start(self, change: dict, reason: str) -> None:
        broken = replace(SENTINEL_2_L2A, index_presets=(replace(PRESETS["NDVI"], **change),))
        with pytest.raises(IndexPresetMismatch, match=f"sentinel-2-c1-l2a: the index preset .*{reason}"):
            check_index_presets(DatasetRegistry((broken, COP_DEM_GLO_30)))

    def test_the_bands_band_math_reads_are_matched_against_the_entry_once_more(self) -> None:
        """A net under the text check of `catalog`: here the bands come off the syntax tree."""
        entry = replace(SENTINEL_2_L2A)
        object.__setattr__(entry, "index_presets", (replace(PRESETS["NDVI"], expression="visual - red"),))
        with pytest.raises(IndexPresetMismatch, match="preset NDVI: reads visual, which is no band of the data"):
            check_index_presets(DatasetRegistry((entry,)))

    def test_every_problem_is_named_not_only_the_first(self) -> None:
        broken = replace(
            SENTINEL_2_L2A,
            index_presets=(
                replace(PRESETS["NDVI"], expression="log(nir) - red"),
                replace(PRESETS["NDWI"], colormap_name="nope"),
            ),
        )
        with pytest.raises(IndexPresetMismatch) as error:
            check_index_presets(DatasetRegistry((broken,)))
        assert "preset NDVI" in str(error.value) and "preset NDWI" in str(error.value)

    def test_the_api_that_serves_the_collection_does_not_build_with_such_a_preset(self) -> None:
        """The tiler is not asked: its start stays without `processing` (`test_tiler_start_is_light`, plan §14)."""
        from earthx.api.main import build_app

        broken = replace(SENTINEL_2_L2A, index_presets=(replace(PRESETS["NDVI"], colormap_name="nope"),))
        with pytest.raises(IndexPresetMismatch, match="knows no colormap 'nope'"):
            build_app(DatasetRegistry((broken, COP_DEM_GLO_30)))
