"""The ``mask_values`` operator: parameters, kernel, metadata, applicability and runs (plan DS-06 §8, §10).

The expected values are an independent computation: a loop in plain Python over ``fractions.Fraction``, which compares
the exact value of each pixel with the exact value of the threshold, not a second use of numpy.
"""

from __future__ import annotations

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

from earthx.catalog.datasets import COP_DEM_GLO_30, SENTINEL_2_L2A
from earthx.catalog.registry import LicenseTier
from earthx.processing import run
from earthx.processing.errors import RecipeInvalid
from earthx.processing.operators import MASK_VALUES, REGISTRY, BandMeta, MaskValuesParams, RasterMeta, applicable
from tests.earthx.processing import sources
from tests.earthx.processing.recipes import resolved
from tests.earthx.processing.test_band_math import _SETTING_D, _glibc_masks_features
from tests.earthx.processing.version_1_cases import HEIGHT, WIDTH

NDVI = {"op": "band_math", "op_version": 2, "params": {"expression": "(nir - red) / (nir + red)", "name": "NDVI"}}


def _params(condition: str, *values: float, band: str = "a") -> MaskValuesParams:
    return MaskValuesParams(band=band, condition=condition, values=list(values))


def _image(names: list[str], *arrays: numpy.ndarray, masks: list | None = None) -> ImageData:
    stack = numpy.ma.stack(
        [numpy.ma.masked_array(a, mask=None if masks is None else masks[i]) for i, a in enumerate(arrays)]
    )
    return ImageData(stack, bounds=(0, 0, 1, 1), crs="EPSG:32632", band_names=names)


def _meta(*names: str) -> RasterMeta:
    bands = tuple(BandMeta(name, "float32", None) for name in names)
    return RasterMeta("EPSG:32632", Affine(10, 0, 0, 0, -10, 0), 4, 4, bands)


def _hidden(image: ImageData) -> numpy.ndarray:
    """The mask the kernel left, of every band alike."""
    mask = numpy.ma.getmaskarray(image.array)
    assert (mask == mask[0]).all()
    return mask[0]


def _by_hand(values: numpy.ndarray, condition: str, wanted: tuple[float, ...]) -> numpy.ndarray:
    """The pixels the condition hides, one exact comparison at a time in rational numbers."""
    low = Fraction(wanted[0])
    out = numpy.zeros(values.shape, dtype=bool)
    for index, pixel in numpy.ndenumerate(values):
        exact = Fraction(float(pixel))
        if condition == "lt":
            out[index] = exact < low
        elif condition == "gt":
            out[index] = exact > low
        elif condition == "between":
            out[index] = low <= exact <= Fraction(wanted[1])
        else:
            out[index] = any(exact == Fraction(v) for v in wanted)
    return out


class TestParameters:
    def test_a_valid_condition_of_each_kind(self) -> None:
        for condition, values in (("lt", [0.2]), ("gt", [2000]), ("between", [0.2, 0.8]), ("eq", [3, 8, 9])):
            body = json.dumps({"band": "NDVI", "condition": condition, "values": values})
            params = MaskValuesParams.model_validate_json(body, strict=True)
            assert params.condition == condition and params.values == [float(v) for v in values]

    @pytest.mark.parametrize(
        "data",
        [
            {"band": "a", "condition": "le", "values": [1]},
            {"band": "a", "condition": "lt", "values": []},
            {"band": "a", "condition": "lt", "values": [1, 2]},
            {"band": "a", "condition": "gt", "values": [1, 2]},
            {"band": "a", "condition": "between", "values": [1]},
            {"band": "a", "condition": "between", "values": [1, 2, 3]},
            {"band": "a", "condition": "between", "values": [2, 1]},
            {"band": "a", "condition": "between", "values": [1, 1]},
            {"band": "a", "condition": "eq", "values": [8, 3]},
            {"band": "a", "condition": "eq", "values": [3, 3]},
            {"band": "a", "condition": "eq", "values": [float(v) for v in range(65)]},
            {"band": "a", "condition": "lt", "values": [float("nan")]},
            {"band": "a", "condition": "lt", "values": [float("inf")]},
            {"band": "a", "condition": "lt", "values": [-float("inf")]},
            {"band": "a", "condition": "lt", "values": [1e39]},
            {"band": "a", "condition": "lt", "values": [True]},
            {"band": "a", "condition": "lt", "values": ["1"]},
            {"band": "a", "condition": "lt", "values": 1},
            {"band": "", "condition": "lt", "values": [1]},
            {"band": "a b", "condition": "lt", "values": [1]},
            {"band": "bänd", "condition": "lt", "values": [1]},
            {"band": "x" * 65, "condition": "lt", "values": [1]},
            {"band": 3, "condition": "lt", "values": [1]},
            {"condition": "lt", "values": [1]},
            {"band": "a", "values": [1]},
            {"band": "a", "condition": "lt"},
            {"band": "a", "condition": "lt", "values": [1], "extra": 1},
            {"source": "scl", "classes": [3]},
        ],
    )
    def test_misuse_is_refused(self, data: dict) -> None:
        with pytest.raises(ValidationError):
            MaskValuesParams.model_validate(data, strict=True)

    def test_the_largest_value_of_float32_is_allowed_and_one_beyond_is_not(self) -> None:
        largest = float(numpy.finfo("float32").max)
        assert _params("gt", largest).values == [largest]
        with pytest.raises(ValidationError):
            _params("gt", float(numpy.nextafter(largest, numpy.inf)))

    def test_the_schema_carries_the_bounds_and_no_pattern(self) -> None:
        schema = REGISTRY.params_schema("mask_values", 1)
        assert schema["properties"]["values"]["minItems"] == 1 and schema["properties"]["values"]["maxItems"] == 64
        assert schema["properties"]["condition"]["enum"] == ["lt", "gt", "between", "eq"]
        assert "pattern" not in json.dumps(schema)
        assert schema["additionalProperties"] is False and set(schema["required"]) == {"band", "condition", "values"}


class TestKernel:
    @pytest.mark.parametrize("dtype", ["float32", "float64"])
    @pytest.mark.parametrize(
        ("condition", "wanted"),
        [("lt", (0.2,)), ("gt", (0.2,)), ("between", (0.2, 0.6)), ("eq", (0.25, 0.5, 0.75))],
    )
    def test_each_condition_equals_an_exact_comparison_in_rational_numbers(self, condition, wanted, dtype) -> None:
        # Values on a grid of quarters and fifths, so that thresholds meet pixels exactly and just beside them.
        grid = numpy.array([[i / 20 for i in range(21)], [i / 4 for i in range(21)]], dtype=dtype)
        other = numpy.arange(grid.size, dtype=dtype).reshape(grid.shape)
        result = MASK_VALUES.run(_image(["a", "b"], grid, other), _params(condition, *wanted))
        # The comparison is made in the band's own type, so the thresholds are first rounded to it.
        rounded = tuple(float(numpy.asarray(v, dtype=dtype)) for v in wanted)
        numpy.testing.assert_array_equal(_hidden(result), _by_hand(grid, condition, rounded))

    @pytest.mark.parametrize("condition", ["lt", "gt"])
    def test_the_threshold_itself_and_the_neighbours_a_step_beside_it(self, condition: str) -> None:
        threshold = numpy.float32(0.2)
        pixels = numpy.array(
            [[numpy.nextafter(threshold, numpy.float32(-1)), threshold, numpy.nextafter(threshold, numpy.float32(1))]]
        )
        hidden = _hidden(MASK_VALUES.run(_image(["a", "b"], pixels, pixels), _params(condition, 0.2)))
        assert hidden.tolist() == ([[True, False, False]] if condition == "lt" else [[False, False, True]])

    def test_between_includes_both_ends_and_eq_includes_what_it_lists(self) -> None:
        pixels = numpy.array([[0.1, 0.2, 0.5, 0.8, 0.9]], dtype="float32")
        between = _hidden(MASK_VALUES.run(_image(["a"], pixels), _params("between", 0.2, 0.8)))
        assert between.tolist() == [[False, True, True, True, False]]
        eq = _hidden(MASK_VALUES.run(_image(["a"], pixels), _params("eq", 0.1, 0.9)))
        assert eq.tolist() == [[True, False, False, False, True]]

    def test_a_float32_band_is_compared_in_its_own_type(self) -> None:
        # float32(0.2) is 0.2000000030…; in float64 it is neither equal to 0.2 nor below it.
        pixels = numpy.full((2, 2), 0.2, dtype="float32")
        assert _hidden(MASK_VALUES.run(_image(["a"], pixels), _params("eq", 0.2))).all()
        assert not _hidden(MASK_VALUES.run(_image(["a"], pixels), _params("lt", 0.2))).any()
        wide = pixels.astype("float64")
        assert not _hidden(MASK_VALUES.run(_image(["a"], wide), _params("eq", 0.2))).any()

    def test_an_integer_band_is_compared_exactly(self) -> None:
        classes = numpy.array([[0, 2, 3, 3, 8, 11, 255]], dtype="uint8")
        assert _hidden(MASK_VALUES.run(_image(["a"], classes), _params("eq", 3, 8))).tolist() == [
            [False, False, True, True, True, False, False]
        ]
        assert _hidden(MASK_VALUES.run(_image(["a"], classes), _params("lt", 2.5))).tolist() == [
            [True, True, False, False, False, False, False]
        ]
        # A threshold below zero is no wrap-around of an unsigned type.
        assert not _hidden(MASK_VALUES.run(_image(["a"], classes), _params("lt", -1))).any()
        # A threshold above the type does not wrap either.
        assert _hidden(MASK_VALUES.run(_image(["a"], classes), _params("lt", 300))).all()

    def test_a_signed_integer_band_with_a_negative_threshold(self) -> None:
        heights = numpy.array([[-5, -1, 0, 2000, 2001]], dtype="int16")
        assert _hidden(MASK_VALUES.run(_image(["a"], heights), _params("gt", 2000))).tolist() == [
            [False, False, False, False, True]
        ]
        assert _hidden(MASK_VALUES.run(_image(["a"], heights), _params("between", -5, -1))).tolist() == [
            [True, True, False, False, False]
        ]

    def test_every_band_is_masked_where_the_condition_holds_the_one_looked_at_included(self) -> None:
        a = numpy.array([[0.1, 0.5], [0.9, 0.3]], dtype="float32")
        b = numpy.array([[10, 20], [30, 40]], dtype="float32")
        result = MASK_VALUES.run(_image(["a", "b"], a, b), _params("lt", 0.4))
        assert result.array.mask[0].tolist() == result.array.mask[1].tolist() == [[True, False], [False, True]]
        assert list(result.band_names) == ["a", "b"]

    def test_values_and_types_of_the_bands_are_untouched(self) -> None:
        a = numpy.array([[0.1, 0.5]], dtype="float32")
        b = numpy.array([[10, 20]], dtype="float32")
        result = MASK_VALUES.run(_image(["a", "b"], a, b), _params("lt", 0.4))
        assert result.array.dtype == numpy.float32
        numpy.testing.assert_array_equal(numpy.ma.getdata(result.array)[0], a)
        numpy.testing.assert_array_equal(numpy.ma.getdata(result.array)[1], b)

    def test_a_pixel_that_was_masked_stays_masked_in_every_band(self) -> None:
        a = numpy.array([[0.9, 0.9]], dtype="float32")
        b = numpy.array([[1.0, 2.0]], dtype="float32")
        result = MASK_VALUES.run(_image(["a", "b"], a, b, masks=[[False, False], [True, False]]), _params("lt", 0.4))
        assert result.array.mask[1].tolist() == [[True, False]] and result.array.mask[0].tolist() == [[False, False]]

    def test_a_pixel_without_a_value_in_the_band_looked_at_is_hidden_in_all(self) -> None:
        a = numpy.array([[0.9, 0.9]], dtype="float32")
        b = numpy.array([[1.0, 2.0]], dtype="float32")
        masked = _hidden(MASK_VALUES.run(_image(["a", "b"], a, b, masks=[[True, False], [False, False]]), _params("lt", 0.4)))
        assert masked.tolist() == [[True, False]]

    def test_nan_counts_as_no_value_even_when_nothing_masked_it(self) -> None:
        a = numpy.array([[numpy.nan, 0.9]], dtype="float32")
        assert _hidden(MASK_VALUES.run(_image(["a", "b"], a, a), _params("gt", 0.1))).tolist() == [[True, True]]
        assert _hidden(MASK_VALUES.run(_image(["a", "b"], a, a), _params("lt", 0.1))).tolist() == [[True, False]]

    def test_a_threshold_nobody_reaches_hides_nothing_and_one_everybody_meets_hides_all(self) -> None:
        a = numpy.linspace(0, 1, 12, dtype="float32").reshape(3, 4)
        assert not _hidden(MASK_VALUES.run(_image(["a"], a), _params("gt", 5))).any()
        assert _hidden(MASK_VALUES.run(_image(["a"], a), _params("lt", 5))).all()

    def test_the_band_is_not_among_the_bands(self) -> None:
        a = numpy.zeros((2, 2), dtype="float32")
        with pytest.raises(RecipeInvalid, match="not among the bands: a, b"):
            MASK_VALUES.run(_image(["a", "b"], a, a), _params("lt", 1, band="NDVI"))

    def test_a_band_of_text_is_refused(self) -> None:
        text = numpy.array([["x", "y"]])
        with pytest.raises(RecipeInvalid, match="compares numbers"):
            MASK_VALUES.run(_image(["a"], text), _params("lt", 1))

    def test_the_band_may_be_the_only_one(self) -> None:
        a = numpy.array([[0.1, 0.9]], dtype="float32")
        assert _hidden(MASK_VALUES.run(_image(["a"], a), _params("lt", 0.5))).tolist() == [[True, False]]


class TestMetadata:
    def test_the_bands_and_the_flag_stay(self) -> None:
        meta = replace(_meta("a", "b"), resampled=True)
        assert MASK_VALUES.transform(meta, _params("lt", 1)) == meta

    def test_a_missing_band_is_found_before_a_block_is_read(self) -> None:
        with pytest.raises(RecipeInvalid, match="not among the bands: a, b"):
            MASK_VALUES.transform(_meta("a", "b"), _params("lt", 1, band="NDVI"))

    def test_the_planner_is_told_the_band_is_read_and_nothing_is_added_or_dropped(self) -> None:
        use = MASK_VALUES.bands_used(_params("lt", 1, band="NDVI"))
        assert (use.reads, use.adds, use.acts_on) == (frozenset({"NDVI"}), None, None)

    @pytest.mark.parametrize(
        ("params", "lineage", "method"),
        [
            (_params("lt", 0.2, band="NDVI"), "mask values: NDVI < 0.2", "where NDVI was below 0.2 or had no value"),
            (_params("gt", 2000, band="data"), "mask values: data > 2000", "where data was above 2000 or"),
            (_params("between", 0.2, 0.8, band="NDVI"), "mask values: NDVI from 0.2 to 0.8", "between 0.2 and 0.8 (both included)"),
            (_params("eq", 3, 8, 9, band="scl"), "mask values: scl = 3, 8, 9", "equal to 3, 8, 9 or had no value"),
        ],
    )
    def test_lineage_and_the_sentence_of_the_methods_text_name_band_condition_and_values(
        self, params: MaskValuesParams, lineage: str, method: str
    ) -> None:
        assert MASK_VALUES.lineage(params) == lineage
        sentence = MASK_VALUES.method(params)
        assert method in sentence and sentence.startswith("Pixels were hidden in every band where ")
        assert "http" not in sentence

    def test_the_properties_say_what_was_asked(self) -> None:
        assert MASK_VALUES.properties(_params("between", 0.2, 0.8, band="NDVI")) == {
            "earthx:mask_values": {"band": "NDVI", "condition": "between", "values": [0.2, 0.8]}
        }

    def test_the_cost_factor_is_the_measured_one_and_it_runs_as_tile_and_job(self) -> None:
        assert MASK_VALUES.cost_factor(_params("lt", 1)) == 0.2
        assert {tier.value for tier in MASK_VALUES.tiers} == {"T1", "T2"} and MASK_VALUES.kind == "pixel"
        assert MASK_VALUES.stock and MASK_VALUES.listed

    def test_it_is_the_one_version_of_the_registry(self) -> None:
        assert REGISTRY.operator("mask_values", 1) is MASK_VALUES


class TestApplicable:
    @pytest.mark.parametrize("config", [SENTINEL_2_L2A, COP_DEM_GLO_30], ids=lambda config: config.dataset_id)
    def test_every_entry_allows_it_with_or_without_a_classification_layer(self, config) -> None:
        assert applicable(MASK_VALUES, config, _params("gt", 1)) == []

    def test_the_dem_has_no_layer_for_mask_but_a_mask_by_value(self) -> None:
        assert COP_DEM_GLO_30.mask is None
        assert applicable(MASK_VALUES, COP_DEM_GLO_30, _params("gt", 2000, band="data")) == []

    def test_an_entry_that_has_not_switched_it_on_refuses_it_naming_the_flag(self) -> None:
        off = replace(SENTINEL_2_L2A, capabilities=replace(SENTINEL_2_L2A.capabilities, value_masking=False))
        assert applicable(MASK_VALUES, off, _params("gt", 1)) == [f"{off.dataset_id} does not allow value_masking"]

    def test_the_flag_alone_is_not_enough_below_the_processing_tier(self) -> None:
        display = replace(SENTINEL_2_L2A, license=replace(SENTINEL_2_L2A.license, tier=LicenseTier.DISPLAY))
        assert any("does not allow processing" in reason for reason in applicable(MASK_VALUES, display))

    def test_the_flag_is_in_the_registry_without_a_default(self) -> None:
        from earthx.catalog.registry import Capabilities

        flags = {name: True for name in Capabilities.__dataclass_fields__ if name != "value_masking"}
        with pytest.raises(TypeError, match="value_masking"):
            Capabilities(**flags)


# --- runs through the core -----------------------------------------------------------------------------------


def _entry(asset: str) -> dict:
    entry = resolved("ITEM_A", asset, href=sources.url(asset), scale=0.0001, offset=-0.1)
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


def _step(**params: object) -> dict:
    return {"op": "mask_values", "op_version": 1, "params": params}


def _run(data: dict, workdir: Path):
    from earthx.processing.recipe import recipe_from_data

    return run(recipe_from_data(data, REGISTRY), workdir=workdir, progress=lambda done, total: None, operators=REGISTRY)


def _read(path: Path) -> numpy.ma.MaskedArray:
    with rasterio.open(path) as dataset:
        return dataset.read(masked=True)


@pytest.fixture(scope="module")
def bands(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    root = tmp_path_factory.mktemp("mask-values")
    return {
        "red": sources.build_band_cog(root / "red.tif", sources.ramp(WIDTH, HEIGHT, 1200)),
        "nir": sources.build_band_cog(root / "nir.tif", sources.ramp(WIDTH, HEIGHT, 3400)),
    }


@pytest.fixture
def served(bands: dict[str, Path], monkeypatch: pytest.MonkeyPatch) -> list[str]:
    return sources.serve({sources.url(name): path for name, path in bands.items()}, monkeypatch)


@pytest.fixture(scope="module")
def physical(bands: dict[str, Path]) -> dict[str, numpy.ma.MaskedArray]:
    """The bands in physical values as rio-tiler unscales them: what the thresholds are compared with."""
    result = {}
    for name in ("red", "nir"):
        with Reader(str(bands[name])) as reader:
            result[name] = reader.read(unscale=True).array[0]
    return result


@pytest.mark.usefixtures("served")
class TestRunsThroughTheCore:
    def test_ndvi_below_a_threshold_hides_every_band_where_an_independent_ndvi_is_below_it(
        self, tmp_path: Path, physical: dict
    ) -> None:
        result = _run(_recipe([NDVI, _step(band="NDVI", condition="lt", values=[0.5])], ["NDVI", "red"]), tmp_path)
        red, nir = (physical[name].astype("float64") for name in ("red", "nir"))
        ndvi = ((nir - red) / (nir + red)).astype("float32")
        expected = numpy.ma.getmaskarray(red) | (ndvi < numpy.float32(0.5))
        data = _read(result.path)
        assert 0 < expected.sum() < expected.size
        numpy.testing.assert_array_equal(numpy.ma.getmaskarray(data[0]), expected)
        numpy.testing.assert_array_equal(numpy.ma.getmaskarray(data[1]), expected)
        numpy.testing.assert_array_equal(data[0].compressed(), numpy.ma.getdata(ndvi)[~expected])
        assert result.valid_pixels == int((~expected).sum())
        assert result.properties["earthx:mask_values"] == {"band": "NDVI", "condition": "lt", "values": [0.5]}
        assert result.properties["processing:lineage"].endswith("mask values: NDVI < 0.5")

    def test_a_band_of_the_data_decides_just_the_same(self, tmp_path: Path, physical: dict) -> None:
        result = _run(_recipe([_step(band="red", condition="gt", values=[0.2])], ["red", "nir"]), tmp_path)
        red = physical["red"]
        expected = numpy.ma.getmaskarray(red) | (numpy.ma.getdata(red) > numpy.float32(0.2))
        data = _read(result.path)
        numpy.testing.assert_array_equal(numpy.ma.getmaskarray(data[0]), expected)
        numpy.testing.assert_array_equal(numpy.ma.getmaskarray(data[1]), expected)
        assert 0 < expected.sum() < expected.size

    def test_the_band_may_stay_out_of_the_file_but_still_decides(self, tmp_path: Path, physical: dict) -> None:
        kept = _run(_recipe([_step(band="red", condition="gt", values=[0.2])], ["nir"]), tmp_path)
        data = _read(kept.path)
        assert data.shape[0] == 1 and [band.name for band in kept.meta.bands] == ["nir"]
        red = physical["red"]
        expected = numpy.ma.getmaskarray(red) | (numpy.ma.getdata(red) > numpy.float32(0.2))
        numpy.testing.assert_array_equal(numpy.ma.getmaskarray(data[0]), expected)

    def test_before_or_after_the_result_the_same_pixels_stay(self, tmp_path: Path) -> None:
        for name in ("a", "b"):
            (tmp_path / name).mkdir()
        mask = _step(band="red", condition="gt", values=[0.2])
        before = _run(_recipe([mask, NDVI], ["NDVI", "red"]), tmp_path / "a")
        after = _run(_recipe([NDVI, mask], ["NDVI", "red"]), tmp_path / "b")
        first, second = _read(before.path), _read(after.path)
        numpy.testing.assert_array_equal(numpy.ma.getmaskarray(first), numpy.ma.getmaskarray(second))
        numpy.testing.assert_array_equal(first.compressed(), second.compressed())

    def test_two_masks_hide_what_either_hides(self, tmp_path: Path, physical: dict) -> None:
        low, high = _step(band="red", condition="lt", values=[0.1]), _step(band="red", condition="gt", values=[0.3])
        result = _run(_recipe([low, high], ["red"]), tmp_path)
        red = physical["red"]
        values = numpy.ma.getdata(red)
        expected = numpy.ma.getmaskarray(red) | (values < numpy.float32(0.1)) | (values > numpy.float32(0.3))
        numpy.testing.assert_array_equal(numpy.ma.getmaskarray(_read(result.path)[0]), expected)
        assert [entry["condition"] for entry in result.properties["earthx:mask_values"]] == ["lt", "gt"]

    def test_dropping_what_is_not_needed_changes_no_value(self, tmp_path: Path) -> None:
        for name in ("a", "b"):
            (tmp_path / name).mkdir()
        steps = [NDVI, _step(band="NDVI", condition="between", values=[0.2, 0.6])]
        dropped = _run(_recipe(steps, ["NDVI"]), tmp_path / "a")
        everything = _run(_recipe(steps, ["red", "nir", "NDVI"]), tmp_path / "b")
        only, wide = _read(dropped.path)[0], _read(everything.path)[2]
        numpy.testing.assert_array_equal(numpy.ma.getmaskarray(only), numpy.ma.getmaskarray(wide))
        numpy.testing.assert_array_equal(only.compressed(), wide.compressed())

    def test_the_same_bytes_twice(self, tmp_path: Path) -> None:
        for name in ("a", "b"):
            (tmp_path / name).mkdir()
        recipe = _recipe([NDVI, _step(band="NDVI", condition="lt", values=[0.5])], ["NDVI", "red"])
        first, second = _run(recipe, tmp_path / "a"), _run(recipe, tmp_path / "b")
        assert hashlib.sha256(first.path.read_bytes()).digest() == hashlib.sha256(second.path.read_bytes()).digest()

    def test_the_band_missing_from_the_stock_stops_before_the_first_block(self, tmp_path: Path) -> None:
        ticks: list[int] = []
        from earthx.processing.recipe import recipe_from_data

        recipe = recipe_from_data(_recipe([_step(band="NDVI", condition="lt", values=[0.5])], ["red"]), REGISTRY)
        with pytest.raises(RecipeInvalid, match="not among the bands"):
            run(recipe, workdir=tmp_path, progress=lambda done, total: ticks.append(done), operators=REGISTRY)
        assert ticks == [] and list(tmp_path.iterdir()) == []

    def test_a_result_of_a_later_step_is_not_there_yet(self, tmp_path: Path) -> None:
        with pytest.raises(RecipeInvalid, match="not among the bands"):
            _run(_recipe([_step(band="NDVI", condition="lt", values=[0.5]), NDVI], ["red"]), tmp_path)

    def test_everything_hidden_gives_a_file_with_no_valid_pixel(self, tmp_path: Path) -> None:
        result = _run(_recipe([_step(band="red", condition="gt", values=[-1])], ["red", "nir"]), tmp_path)
        assert result.valid_pixels == 0 and _read(result.path).mask.all()

    def test_the_lineage_names_the_mask_beside_the_other_steps(self, tmp_path: Path) -> None:
        result = _run(_recipe([NDVI, _step(band="NDVI", condition="lt", values=[0.5])], ["NDVI"]), tmp_path)
        assert result.properties["processing:lineage"] == (
            "band math: NDVI = (nir - red) / (nir + red); mask values: NDVI < 0.5"
        )


# --- bit-stability across CPU levels (adr/0016 §12a) -----------------------------------------------------------

_PROBE = textwrap.dedent(
    """
    import hashlib, json
    import numpy
    from rio_tiler.models import ImageData
    from earthx.processing.operators import MASK_VALUES, MaskValuesParams

    rng = numpy.random.default_rng(11)
    a = rng.uniform(-0.3, 1.6, (512, 512))
    out = {}
    for dtype in ("float32", "float64", "uint16"):
        values = (a * 1000).astype(dtype) if dtype == "uint16" else a.astype(dtype)
        image = ImageData(
            numpy.ma.stack([numpy.ma.masked_array(values), numpy.ma.masked_array(values * 2)]),
            bounds=(0, 0, 1, 1), crs="EPSG:32632", band_names=["a", "b"],
        )
        for name, (condition, wanted) in {
            "lt": ("lt", [0.2]), "gt": ("gt", [0.77]), "between": ("between", [0.2, 0.8]),
            "eq": ("eq", [0.0, 3.0, 500.0]),
        }.items():
            result = MASK_VALUES.run(image, MaskValuesParams(band="a", condition=condition, values=wanted)).array
            out[f"{dtype}: {name}"] = hashlib.sha256(numpy.ma.getdata(result).tobytes() + result.mask.tobytes()).hexdigest()
    print(json.dumps(out))
    """
)


def _probe(env_extra: dict[str, str]) -> dict[str, str]:
    backend = str(Path(__file__).resolve().parents[3])
    done = subprocess.run(
        [sys.executable, "-c", _PROBE],
        capture_output=True,
        text=True,
        env={**os.environ, **env_extra, "PYTHONPATH": backend},
        timeout=300,
        check=False,
    )
    assert done.returncode == 0, done.stderr[-2000:]
    return json.loads(done.stdout.strip().splitlines()[-1])


class TestBitStabilityAcrossCpuLevels:
    def test_the_four_conditions_give_the_same_bytes_under_settings_a_and_d(self) -> None:
        if not _glibc_masks_features():
            pytest.skip("GLIBC_TUNABLES does not change the CPU features this loader reports: setting D is not one")
        setting_a, setting_d = _probe({}), _probe(_SETTING_D)
        assert len(setting_a) == 3 * 4
        assert sorted(key for key in setting_a if setting_a[key] != setting_d[key]) == []
        assert hashlib.sha256(b"").hexdigest() not in setting_a.values()
