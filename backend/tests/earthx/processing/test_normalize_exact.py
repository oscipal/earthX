"""``normalize`` version 4: the numbers of a statistical method are measured in the run, exactly (NM4-71, adr/0014 Nachtrag NM4-71).

The oracle is never the code under test: the numbers a run reports in ``earthx:normalize`` are held against numpy over the
pixels the mask marks, taken from a second run of the same recipe *up to* the measuring step with ``float64`` as the output
type (that file holds the very values the pass before the step writes). The bytes of a run with version 4 are held
against a run with version 3 and the numbers the first one reported, and against the formula of the method.
"""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import math
import os
import subprocess
import sys
import textwrap
from fractions import Fraction
from pathlib import Path

import numpy
import pytest
import rasterio
from pydantic import ValidationError
from rasterio.transform import Affine
from rasterio.warp import transform_geom
from rio_tiler.models import ImageData

from earthx.logging import JsonFormatter
from earthx.processing import run
from earthx.processing.core import area_statistics
from earthx.processing.errors import RecipeInvalid, RunCancelled
from earthx.processing.operators import (
    NORMALIZE,
    NORMALIZE_V2,
    NORMALIZE_V3,
    NORMALIZE_V4,
    REGISTRY,
    BandMeta,
    NormalizeParams,
    NormalizeParamsV2,
    NormalizeParamsV3,
    NormalizeParamsV4,
    RasterMeta,
    Tier,
)
from earthx.processing.operators.normalize import BandValues, Measured, MeasuredNormalizeV4
from earthx.processing.recipe import recipe_from_data
from earthx.processing.statistics import MEASURE_PERCENTILES
from tests.earthx.processing import sources
from tests.earthx.processing.test_band_math import _SETTING_D, _glibc_masks_features
from tests.earthx.processing.version_1_cases import HEIGHT, WIDTH, scl_layer

BOTH = ["red", "nir"]
_TARGET = {"out_min": 0.0, "out_max": 1.0, "clip": True}
LINEAR = {
    "method": "linear",
    "bands": BOTH,
    "in_min": 0.0,
    "in_max": 0.5,
    "out_min": 0.0,
    "out_max": 255.0,
    "clip": True,
}
PERCENTILE = {"method": "percentile", "bands": BOTH, "low": 2, "high": 98, **_TARGET}
ZSCORE = {"method": "zscore", "bands": BOTH}
ROBUST = {"method": "robust", "bands": BOTH}
METHODS = {"linear": LINEAR, "percentile": PERCENTILE, "zscore": ZSCORE, "robust": ROBUST}
STATISTICAL = ["percentile", "zscore", "robust"]

NDVI = {"op": "band_math", "op_version": 2, "params": {"expression": "(nir - red) / (nir + red)", "name": "NDVI"}}
DIFF = {"op": "band_math", "op_version": 2, "params": {"expression": "nir - 2 * red", "name": "Diff"}}
MASK = {"op": "mask", "op_version": 2, "params": {"source": "scl", "classes": [3, 8, 9, 10]}}
REPROJECT = {
    "op": "reproject",
    "op_version": 4,
    "params": {"crs": "EPSG:3035", "resolution": 20.0, "resampling": "bilinear", "align": True},
}


def step(params: dict, version: int = 4) -> dict:
    return {"op": "normalize", "op_version": version, "params": params}


def _with(params: dict, **change) -> dict:
    changed = copy.deepcopy(params)
    changed.update(change)
    return {key: value for key, value in changed.items() if value is not ...}


# --- the oracle ---------------------------------------------------------------------------------------------------


def nearest_rank(values: numpy.ndarray, percent: int) -> float:
    ordered = numpy.sort(values)
    return float(ordered[max(1, -(-percent * ordered.size // 100)) - 1])


def expected_numbers(values: numpy.ndarray, method: str, params: dict) -> dict[str, float]:
    """What the method needs of the pixels ``values`` (one dimension, float64), by plain numpy and sorting."""
    if method == "percentile":
        low, high = params["low"], params["high"]
        return {
            "p_low": float(values.min()) if low == 0 else nearest_rank(values, low),
            "p_high": float(values.max()) if high == 100 else nearest_rank(values, high),
        }
    if method == "zscore":
        return {"mean": float(sum(map(Fraction, values.tolist())) / values.size), "stddev": float(values.std())}
    return {"p25": nearest_rank(values, 25), "median": nearest_rank(values, 50), "p75": nearest_rank(values, 75)}


_ROUNDED_DOWN = {"p_low", "p25", "median"}
_ROUNDED_UP = {"p_high", "p75"}


def assert_numbers(found: dict[str, float], expected: dict[str, float], *, float64_only: bool = False) -> None:
    """``found`` is ``expected``; the mean to the bit, the spread up to rounding.

    With ``float64_only`` the values were not float32 to begin with (a warp gives float64): a percentile is then the
    float32 below it, or for the upper ones above it, at most one float32 step away.
    """
    assert found.keys() == expected.keys()
    for name, value in expected.items():
        if name == "stddev":  # GDAL's merge of blocks, not a sum in one go: equal up to rounding
            assert found[name] == pytest.approx(value, rel=1e-9)
        elif float64_only and name in _ROUNDED_DOWN | _ROUNDED_UP:
            step = abs(float(numpy.spacing(numpy.float32(value))))
            distance = value - found[name] if name in _ROUNDED_DOWN else found[name] - value
            assert 0 <= distance <= step, name
        else:
            assert found[name] == value, name


# --- the recipes --------------------------------------------------------------------------------------------------


def _entry(asset: str) -> dict:
    from tests.earthx.processing.recipes import resolved

    layer, coarse = asset == "scl", asset in ("swir", "scl")
    entry = resolved(
        "ITEM_A", asset, href=sources.url(asset), scale=None if layer else 0.0001, offset=None if layer else -0.1
    )
    if layer:
        entry["bands"] = [{"data_type": "uint8", "nodata": 0, "scale": None, "offset": None}]
    else:
        entry["bands"][0]["unit"] = "1"
    entry["gsd"] = 20.0 if coarse else 10.0
    return entry


def diamond(width: int, height: int, inset: int = 40) -> dict:
    """A diamond inside the raster whose box is the raster less ``inset`` pixels: about half of the box is inside."""
    x0, y0 = sources.ORIGIN_X, sources.ORIGIN_Y
    ring = [
        [x0 + inset * 10, y0 - height * 5],
        [x0 + width * 5, y0 - inset * 10],
        [x0 + (width - inset) * 10, y0 - height * 5],
        [x0 + width * 5, y0 - (height - inset) * 10],
        [x0 + inset * 10, y0 - height * 5],
    ]
    return transform_geom(sources.CRS, "EPSG:4326", {"type": "Polygon", "coordinates": [ring]})


def recipe(
    steps: list,
    bands: list[str],
    *,
    assets=("red", "nir"),
    aoi: dict | None = None,
    dtype: str = "float32",
    size: tuple[int, int] = (WIDTH, HEIGHT),
) -> dict:
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
        "aoi": aoi or sources.whole(*size),
        "steps": steps,
        "output": {"kind": "raster", "format": "cog", "dtype": dtype, "bands": bands},
    }


def do_run(data: dict, workdir: Path, progress=lambda done, total: None):
    workdir.mkdir(exist_ok=True, parents=True)
    return run(recipe_from_data(data, REGISTRY), workdir=workdir, progress=progress, operators=REGISTRY)


def pixels_before(data: dict, steps: list, bands: list[str], workdir: Path) -> dict[str, numpy.ndarray]:
    """The valid, finite values of ``bands`` inside the mask after ``steps`` only: the pass before a measuring step wrote them."""
    prefix = {**data, "steps": steps, "output": {**data["output"], "dtype": "float64", "bands": bands}}
    result = do_run(prefix, workdir)
    with rasterio.open(result.path) as file, rasterio.open(result.mask_path) as mask:
        values, inside = file.read(), mask.read(1) == 1
    return {name: values[i][inside & numpy.isfinite(values[i])] for i, name in enumerate(bands)}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def as_version_3(data: dict, result) -> dict:
    """The same recipe with every measuring step of version 4 replaced by version 3 with the numbers the run reported."""
    swapped = copy.deepcopy(data)
    reported = {entry["step"]: entry for entry in result.properties.get("earthx:normalize", [])}
    for index, entry in reported.items():
        params = swapped["steps"][index]["params"]
        params["bands"] = list(entry["bands"])
        params["measured"] = {"factor": 1, "bands": entry["bands"]}
        swapped["steps"][index]["op_version"] = 3
    for entry in swapped["steps"]:
        if entry["op"] == "normalize" and entry["op_version"] == 4:
            entry["op_version"] = 3
    return swapped


@pytest.fixture(scope="module")
def files(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    root = tmp_path_factory.mktemp("normalize-exact")
    return {
        "red": sources.build_band_cog(root / "red.tif", sources.ramp(WIDTH, HEIGHT, 1200)),
        "nir": sources.build_band_cog(root / "nir.tif", sources.ramp(WIDTH, HEIGHT, 3400)),
        "swir": sources.build_band_cog(root / "swir.tif", sources.ramp(WIDTH // 2, HEIGHT // 2, 2200), resolution=20.0),
        "scl": sources.build_band_cog(
            root / "scl.tif", scl_layer(WIDTH // 2, HEIGHT // 2), scale=None, offset=None, resolution=20.0
        ),
    }


@pytest.fixture
def served(files: dict[str, Path], monkeypatch: pytest.MonkeyPatch) -> list[str]:
    return sources.serve({sources.url(name): path for name, path in files.items()}, monkeypatch)


# --- the operator -------------------------------------------------------------------------------------------------


def _params(data: dict) -> NormalizeParamsV4:
    return NormalizeParamsV4.model_validate_json(json.dumps(data), strict=True)


def _level(percent: int) -> float:
    return 0.05 + 0.9 * percent / 100


def _numbers(method: str, bands: list[str] = BOTH) -> dict[str, dict]:
    """Statistics of the kind a count gives (``minimum`` … ``percentile_<n>``) for ``bands``."""
    summary = {"count": 100, "minimum": 0.05, "maximum": 0.95, "mean": 0.5, "stddev": 0.25}
    summary |= {f"percentile_{p}": _level(p) for p in (1, 2, 5, 25, 50, 75, 95, 98, 99)}
    return {name: dict(summary) for name in bands}


class TestTheParameters:
    @pytest.mark.parametrize("method", list(METHODS))
    def test_each_method_reads_from_json(self, method: str) -> None:
        assert _params(METHODS[method]).method == method

    @pytest.mark.parametrize(
        ("name", "base", "change"),
        [
            (
                "measured on linear",
                LINEAR,
                {"measured": {"factor": 1, "bands": {"red": {"p_low": 0.1, "p_high": 0.2}}}},
            ),
            (
                "measured on percentile",
                PERCENTILE,
                {"measured": {"factor": 1, "bands": {"red": {"p_low": 0.1, "p_high": 0.9}}}},
            ),
            ("measured on zscore", ZSCORE, {"measured": {"factor": 1, "bands": {"red": {"mean": 0.5, "stddev": 0.2}}}}),
            ("unknown method", LINEAR, {"method": "minmax"}),
            ("no method", LINEAR, {"method": ...}),
            ("linear with low", LINEAR, {"low": 2}),
            ("linear without in_max", LINEAR, {"in_max": ...}),
            ("linear with in_min at in_max", LINEAR, {"in_min": 0.5}),
            ("percentile with in_min", PERCENTILE, {"in_min": 0.0}),
            ("percentile without clip", PERCENTILE, {"clip": ...}),
            ("percentile with a low that is no choice", PERCENTILE, {"low": 3}),
            ("percentile with a high that is no choice", PERCENTILE, {"high": 97}),
            ("percentile with a flat target range", PERCENTILE, {"out_max": 0.0}),
            ("zscore with clip", ZSCORE, {"clip": True}),
            ("zscore with a target range", ZSCORE, {"out_min": 0.0}),
            ("zscore with a percent", ZSCORE, {"low": 2}),
            ("robust with in_max", ROBUST, {"in_max": 1.0}),
            ("empty bands", LINEAR, {"bands": []}),
            ("a band twice, case ignored", LINEAR, {"bands": ["red", "RED"]}),
            ("extra field", LINEAR, {"extra": 1}),
        ],
        ids=lambda value: value if isinstance(value, str) else None,
    )
    def test_misuse_is_refused(self, name: str, base: dict, change: dict) -> None:
        with pytest.raises(ValidationError):
            _params(_with(base, **change))

    def test_the_schema_has_no_measured_and_names_the_methods(self) -> None:
        schema = REGISTRY.params_schema("normalize", 4)
        assert "measured" not in schema["properties"] and schema["required"] == ["method", "bands"]
        assert schema["properties"]["method"]["enum"] == ["linear", "percentile", "zscore", "robust"]

    def test_the_model_with_the_numbers_is_no_recipe_parameter(self) -> None:
        """It is the operator's own: nothing in the registry names it, so no recipe can bring numbers of its own."""
        assert all(operator.params is not MeasuredNormalizeV4 for operator in REGISTRY.values())
        with pytest.raises(ValidationError):
            NORMALIZE_V4.params.model_validate_json(
                json.dumps({**ZSCORE, "measured": {"factor": 1, "bands": {}}}), strict=True
            )


class TestTheRegistration:
    def test_only_the_job_runs_it_and_it_is_listed_instead_of_version_3(self) -> None:
        assert NORMALIZE_V4.tiers == frozenset({Tier.T2}) and NORMALIZE_V4.kind == "pixel"
        assert NORMALIZE_V4.listed is True and NORMALIZE_V3.listed is False
        assert NORMALIZE_V3.tiers == frozenset({Tier.T1, Tier.T2})
        assert REGISTRY.operator("normalize", 4) is NORMALIZE_V4 and REGISTRY.operator("normalize", 3) is NORMALIZE_V3

    def test_a_step_that_measures_is_a_pixel_step_of_the_job_only(self) -> None:
        import dataclasses

        for change in ({"tiers": frozenset({Tier.T1, Tier.T2})}, {"with_measured": None}, {"measured_report": None}):
            with pytest.raises(ValueError, match="a step that measures"):
                dataclasses.replace(NORMALIZE_V4, **change)

    def test_the_other_operators_measure_nothing(self) -> None:
        defaults = [operator for operator in REGISTRY.values() if operator is not NORMALIZE_V4]
        assert all(operator.measures(None) == frozenset() for operator in defaults if operator.op != "normalize")
        assert all(operator.measures(_params(LINEAR)) == frozenset() for operator in (NORMALIZE_V4,))

    def test_what_a_method_asks_the_run_to_measure(self) -> None:
        both = frozenset(BOTH)
        assert [NORMALIZE_V4.measures(_params(METHODS[m])) for m in METHODS] == [frozenset(), both, both, both]
        assert NORMALIZE_V4.measure_percents(_params(LINEAR)) == ()
        assert NORMALIZE_V4.measure_percents(_params(PERCENTILE)) == (2, 98)
        assert NORMALIZE_V4.measure_percents(_params(_with(PERCENTILE, low=0, high=100))) == ()
        assert NORMALIZE_V4.measure_percents(_params(_with(PERCENTILE, low=5, high=100))) == (5,)
        assert NORMALIZE_V4.measure_percents(_params(ZSCORE)) == ()
        assert NORMALIZE_V4.measure_percents(_params(ROBUST)) == (25, 50, 75)

    def test_the_planner_sees_the_bands_it_acts_on_and_narrows_it_without_numbers(self) -> None:
        params = _params(_with(ZSCORE, bands=["a", "b"]))
        assert NORMALIZE_V4.bands_used(params).acts_on == frozenset({"a", "b"})
        narrowed = NORMALIZE_V4.restrict(params, frozenset({"b", "z"}))
        assert narrowed.bands == ["b"] and NORMALIZE_V4.measures(narrowed) == frozenset({"b"})

    def test_the_transform_is_that_of_version_3(self) -> None:
        meta = RasterMeta(
            "EPSG:32632",
            Affine(10, 0, 0, 0, -10, 0),
            4,
            4,
            (BandMeta("red", "uint16", 0), BandMeta("scl", "uint8", 0)),
            False,
        )
        four = NORMALIZE_V4.transform(meta, _params(_with(ZSCORE, bands=["red"])))
        numbers = Measured(factor=1, bands={"red": BandValues(mean=0.0, stddev=1.0)})
        three = NORMALIZE_V3.transform(meta, NormalizeParamsV3(method="zscore", bands=["red"], measured=numbers))
        shown = [(band.name, band.data_type, str(band.nodata)) for band in four.bands]
        assert shown == [(band.name, band.data_type, str(band.nodata)) for band in three.bands]
        assert shown == [("red", "float32", "nan"), ("scl", "uint8", "0")]
        with pytest.raises(RecipeInvalid, match="unknown band.*nir"):
            NORMALIZE_V4.transform(meta, _params(_with(LINEAR, bands=["nir"])))


class TestGivingTheStepItsNumbers:
    def test_each_method_takes_its_numbers_from_the_statistics(self) -> None:
        resolved = NORMALIZE_V4.with_measured(_params(PERCENTILE), _numbers("percentile"))
        assert isinstance(resolved, MeasuredNormalizeV4) and resolved.measured.factor == 1
        assert resolved.measured.bands["red"] == BandValues(p_low=_level(2), p_high=_level(98))
        zscore = NORMALIZE_V4.with_measured(_params(ZSCORE), _numbers("zscore"))
        assert zscore.measured.bands["nir"] == BandValues(mean=0.5, stddev=0.25)
        robust = NORMALIZE_V4.with_measured(_params(ROBUST), _numbers("robust"))
        assert robust.measured.bands["red"] == BandValues(
            p25=0.05 + 0.9 * 0.25, median=0.05 + 0.9 * 0.5, p75=0.05 + 0.9 * 0.75
        )

    def test_the_ends_of_a_stretch_at_zero_and_a_hundred_are_the_minimum_and_the_maximum(self) -> None:
        resolved = NORMALIZE_V4.with_measured(_params(_with(PERCENTILE, low=0, high=100)), _numbers("percentile"))
        assert resolved.measured.bands["red"] == BandValues(p_low=0.05, p_high=0.95)
        mixed = NORMALIZE_V4.with_measured(_params(_with(PERCENTILE, low=0, high=99)), _numbers("percentile"))
        assert mixed.measured.bands["red"] == BandValues(p_low=0.05, p_high=_level(99))

    @pytest.mark.parametrize("method", STATISTICAL)
    def test_a_band_without_a_valid_value_is_refused_by_name(self, method: str) -> None:
        numbers = _numbers(method)
        numbers["nir"] = {"count": 0, "valid_percent": 0.0}
        with pytest.raises(RecipeInvalid, match="^normalize: band nir has no valid value over the AOI$"):
            NORMALIZE_V4.with_measured(_params(METHODS[method]), numbers)

    def test_a_spread_that_is_not_finite_is_refused_with_its_own_reason(self) -> None:
        numbers = _numbers("zscore")
        del numbers["red"]["stddev"]
        with pytest.raises(RecipeInvalid, match="^normalize: band red has no finite standard deviation over the AOI$"):
            NORMALIZE_V4.with_measured(_params(ZSCORE), numbers)

    def test_an_end_of_minus_zero_is_reported_as_zero(self) -> None:
        numbers = _numbers("percentile")
        numbers["red"]["minimum"] = -0.0
        resolved = NORMALIZE_V4.with_measured(_params(_with(PERCENTILE, low=0, high=100)), numbers)
        assert math.copysign(1.0, resolved.measured.bands["red"].p_low) == 1.0

    def test_numbers_that_cannot_be_a_stretch_are_refused(self) -> None:
        numbers = _numbers("percentile")
        numbers["red"]["percentile_98"] = -1.0
        with pytest.raises(RecipeInvalid, match="do not fit the step"):
            NORMALIZE_V4.with_measured(_params(PERCENTILE), numbers)

    def test_the_model_with_numbers_keeps_the_checks_of_version_3(self) -> None:
        with pytest.raises(ValidationError):
            MeasuredNormalizeV4(
                **_params(PERCENTILE).model_dump(),
                measured=Measured(factor=2, bands={name: BandValues(p_low=0.1, p_high=0.9) for name in BOTH}),
            )
        with pytest.raises(ValidationError, match="measures nothing"):
            MeasuredNormalizeV4(
                **_params(LINEAR).model_dump(), measured=Measured(factor=1, bands={"red": BandValues()})
            )

    def test_what_the_result_reports_is_the_numbers_of_the_method_by_band(self) -> None:
        report = NORMALIZE_V4.measured_report(NORMALIZE_V4.with_measured(_params(ZSCORE), _numbers("zscore")))
        assert report == {
            "method": "zscore",
            "bands": {"red": {"mean": 0.5, "stddev": 0.25}, "nir": {"mean": 0.5, "stddev": 0.25}},
        }
        report = NORMALIZE_V4.measured_report(NORMALIZE_V4.with_measured(_params(PERCENTILE), _numbers("percentile")))
        assert list(report["bands"]["red"]) == ["p_low", "p_high"]
        report = NORMALIZE_V4.measured_report(NORMALIZE_V4.with_measured(_params(ROBUST), _numbers("robust")))
        assert list(report["bands"]["nir"]) == ["p25", "median", "p75"]

    def test_the_step_does_not_run_without_its_numbers(self) -> None:
        image = ImageData(
            numpy.ma.masked_array(numpy.ones((2, 3, 3))), bounds=(0, 0, 1, 1), crs="EPSG:32632", band_names=BOTH
        )
        with pytest.raises(RuntimeError, match="only with the numbers"):
            NORMALIZE_V4.run(image, _params(ZSCORE))


def _image(seed: int = 3) -> ImageData:
    values = numpy.random.default_rng(seed).uniform(-0.4, 1.4, (2, 40, 50))
    mask = numpy.zeros(values.shape, dtype=bool)
    mask[:, 3, 4] = True
    return ImageData(
        numpy.ma.masked_array(values.astype("float32"), mask=mask),
        bounds=(0, 0, 1, 1),
        crs="EPSG:32632",
        band_names=BOTH,
    )


def _same(one: ImageData, other: ImageData) -> bool:
    return (
        numpy.ma.getdata(one.array).tobytes() == numpy.ma.getdata(other.array).tobytes()
        and numpy.ma.getmaskarray(one.array).tobytes() == numpy.ma.getmaskarray(other.array).tobytes()
    )


class TestTheKernelIsThatOfVersion3:
    @pytest.mark.parametrize("method", STATISTICAL)
    def test_with_the_same_numbers_the_same_bits(self, method: str) -> None:
        image = _image()
        resolved = NORMALIZE_V4.with_measured(_params(METHODS[method]), _numbers(method))
        numbers = {
            band: BandValues(**{k: v for k, v in values.model_dump().items() if v is not None})
            for band, values in resolved.measured.bands.items()
        }
        third = NormalizeParamsV3(**_params(METHODS[method]).model_dump(), measured=Measured(factor=1, bands=numbers))
        assert _same(NORMALIZE_V4.run(image, resolved), NORMALIZE_V3.run(image, third))

    def test_linear_is_the_line_of_version_1_to_4_to_the_bit(self) -> None:
        image = _image()
        fields = {key: value for key, value in LINEAR.items() if key not in ("method", "bands")}
        one = NORMALIZE.run(
            ImageData(image.array[:1], bounds=image.bounds, crs=image.crs, band_names=["red"]),
            NormalizeParams(**fields),
        )
        two = NORMALIZE_V2.run(image, NormalizeParamsV2(bands=BOTH, **fields))
        three = NORMALIZE_V3.run(image, NormalizeParamsV3(**LINEAR))
        four = NORMALIZE_V4.run(image, _params(LINEAR))
        assert _same(four, three) and _same(four, two)
        assert numpy.ma.getdata(four.array)[0].tobytes() == numpy.ma.getdata(one.array)[0].tobytes()


class TestTheTexts:
    def test_the_sentence_of_the_recipe_has_no_numbers_and_says_where_they_come_from(self) -> None:
        text = NORMALIZE_V4.method(_params(_with(PERCENTILE, bands=["red"])))
        assert text == (
            "The band red was stretched from the 2nd to the 98th percentile (measured in the run over the AOI at full "
            "resolution) onto the range 0 to 1, values outside limited to the target range, in 32-bit "
            "floating point."
        )
        assert "as measured before the run" not in text
        assert "measured in the run over the AOI at full resolution" in NORMALIZE_V4.method(_params(ZSCORE))
        assert "measured in the run over the AOI at full resolution" in NORMALIZE_V4.method(_params(ROBUST))

    def test_the_linear_sentence_is_that_of_version_3(self) -> None:
        assert NORMALIZE_V4.method(_params(LINEAR)) == NORMALIZE_V3.method(NormalizeParamsV3(**LINEAR))

    def test_with_its_numbers_the_sentence_names_them_and_the_constant_band(self) -> None:
        numbers = _numbers("zscore", ["red"])
        numbers["red"]["stddev"] = 0.0
        resolved = NORMALIZE_V4.with_measured(_params(_with(ZSCORE, bands=["red"])), numbers)
        assert NORMALIZE_V4.method(resolved) == (
            "The band red was standardised, (x - mean) / standard deviation, with the mean and the population standard "
            "deviation of the band (red: mean 0.5, standard deviation 0; measured in the run over the AOI at full "
            "resolution), in 32-bit floating point. A band that is constant (standard deviation 0) was "
            "only centred."
        )
        stretch = NORMALIZE_V4.with_measured(_params(_with(PERCENTILE, bands=["red"])), _numbers("percentile", ["red"]))
        assert "(red: 0.068 to 0.932; measured in the run over the AOI at full resolution)" in NORMALIZE_V4.method(
            stretch
        )

    def test_lineage_is_that_of_version_3_with_or_without_the_numbers(self) -> None:
        assert (
            NORMALIZE_V4.lineage(_params(PERCENTILE)) == "normalize: percentiles 2 to 98 to [0, 1], clipped of red, nir"
        )
        resolved = NORMALIZE_V4.with_measured(_params(PERCENTILE), _numbers("percentile"))
        assert NORMALIZE_V4.lineage(resolved) == NORMALIZE_V4.lineage(_params(PERCENTILE))
        assert NORMALIZE_V4.lineage(_params(ZSCORE)) == "normalize: zscore of red, nir"


# --- a run --------------------------------------------------------------------------------------------------------


@pytest.mark.usefixtures("served")
class TestARunMeasuresExactly:
    @pytest.mark.parametrize("method", STATISTICAL)
    def test_the_numbers_are_those_of_numpy_over_the_pixels_of_the_mask(self, method: str, tmp_path: Path) -> None:
        data = recipe([step(METHODS[method])], BOTH, aoi=diamond(WIDTH, HEIGHT))
        result = do_run(data, tmp_path / "job")
        (entry,) = result.properties["earthx:normalize"]
        assert list(entry) == ["step", "method", "bands", "exact"]
        assert (entry["step"], entry["method"], entry["exact"]) == (0, method, True)
        assert list(entry["bands"]) == BOTH
        values = pixels_before(data, [], BOTH, tmp_path / "before")
        assert 0 < values["red"].size < WIDTH * HEIGHT, "the diamond leaves pixels outside the mask"
        for band in BOTH:
            assert_numbers(entry["bands"][band], expected_numbers(values[band], method, METHODS[method]))
            assert all(type(number) is float for number in entry["bands"][band].values())

    @pytest.mark.parametrize(("low", "high"), [(0, 100), (1, 99), (5, 95), (0, 95), (2, 100)])
    def test_the_ends_of_a_stretch(self, low: int, high: int, tmp_path: Path) -> None:
        params = _with(PERCENTILE, low=low, high=high)
        data = recipe([step(params)], BOTH)
        result = do_run(data, tmp_path / "job")
        values = pixels_before(data, [], BOTH, tmp_path / "before")
        for band in BOTH:
            assert_numbers(
                result.properties["earthx:normalize"][0]["bands"][band],
                expected_numbers(values[band], "percentile", params),
            )

    @pytest.mark.parametrize("method", STATISTICAL)
    def test_the_bytes_are_those_of_version_3_with_the_numbers_it_reported(self, method: str, tmp_path: Path) -> None:
        data = recipe([step(METHODS[method])], BOTH, aoi=diamond(WIDTH, HEIGHT))
        measured = do_run(data, tmp_path / "four")
        third = do_run(as_version_3(data, measured), tmp_path / "three")
        assert sha(measured.path) == sha(third.path) and sha(measured.mask_path) == sha(third.mask_path)
        assert "earthx:normalize" not in third.properties

    def test_the_bytes_are_those_of_the_formula_on_the_values_before_the_step(self, tmp_path: Path) -> None:
        data = recipe([step(_with(ZSCORE, bands=["red"]))], BOTH)
        result = do_run(data, tmp_path / "job")
        numbers = result.properties["earthx:normalize"][0]["bands"]["red"]
        before = do_run({**data, "steps": [], "output": {**data["output"], "dtype": "float64"}}, tmp_path / "before")
        with rasterio.open(before.path) as file:
            red = file.read(1, masked=True)
        expected = ((red.filled(numpy.nan) - numbers["mean"]) / numbers["stddev"]).astype("float32")
        with rasterio.open(result.path) as file:
            got = file.read(1)
        numpy.testing.assert_array_equal(got, numpy.where(red.mask, numpy.float32("nan"), expected))

    def test_linear_measures_nothing_and_gives_the_bytes_of_versions_2_and_3(self, tmp_path: Path) -> None:
        four = do_run(recipe([step(LINEAR)], BOTH), tmp_path / "4")
        two = do_run(recipe([step({k: v for k, v in LINEAR.items() if k != "method"}, 2)], BOTH), tmp_path / "2")
        three = do_run(recipe([step(LINEAR, 3)], BOTH), tmp_path / "3")
        assert sha(four.path) == sha(three.path) == sha(two.path)
        assert "earthx:normalize" not in four.properties
        assert four.blocks == three.blocks, "no extra pass: linear does not cut the chain"

    def test_two_runs_give_the_same_bytes_and_the_same_numbers(self, tmp_path: Path) -> None:
        data = recipe([step(PERCENTILE)], BOTH, aoi=diamond(WIDTH, HEIGHT))
        one, other = do_run(data, tmp_path / "a"), do_run(data, tmp_path / "b")
        assert sha(one.path) == sha(other.path)
        assert one.properties == other.properties

    def test_the_lineage_and_the_statistics_of_the_result(self, tmp_path: Path) -> None:
        result = do_run(recipe([step(_with(PERCENTILE, bands=["red"]))], ["red"]), tmp_path)
        assert result.properties["processing:lineage"] == "normalize: percentiles 2 to 98 to [0, 1], clipped of red"
        statistics = result.properties["bands"][0]["statistics"]
        assert 0.0 <= statistics["minimum"] <= statistics["maximum"] <= 1.0

    def test_nothing_of_the_numbers_goes_to_the_log(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.DEBUG):
            result = do_run(recipe([step(ZSCORE)], BOTH), tmp_path)
        text = " ".join(JsonFormatter().format(record) for record in caplog.records)
        assert "earthx:normalize" not in text
        for band in result.properties["earthx:normalize"][0]["bands"].values():
            assert not any(repr(number) in text for number in band.values())
        assert "processing run finished" in text

    def test_progress_counts_the_second_look_too(self, tmp_path: Path) -> None:
        seen: list[tuple[int, int]] = []
        do_run(recipe([step(ROBUST)], BOTH), tmp_path, progress=lambda done, total: seen.append((done, total)))
        blocks = 4  # 2 × 2 blocks of 1024 px
        assert seen[-1][0] == seen[-1][1] == 3 * blocks, "an empty pass, the pass of the step, and the second look"
        zscore = []
        do_run(recipe([step(ZSCORE)], BOTH), tmp_path / "z", progress=lambda done, total: zscore.append((done, total)))
        assert zscore[-1][0] == zscore[-1][1] == 2 * blocks, "a z-score needs no second look"


@pytest.mark.usefixtures("served")
class TestBandsAndValuesTheRefinementMeets:
    def test_a_band_with_no_valid_value_over_the_aoi_fails_the_run_and_names_it(self, tmp_path: Path) -> None:
        """The nodata corner of the ramps is 8 × 8 pixels: an AOI inside it holds no valid value."""
        corner = sources.aoi_around(
            sources.ORIGIN_X + 10, sources.ORIGIN_Y - 70, sources.ORIGIN_X + 70, sources.ORIGIN_Y - 10
        )
        for method in STATISTICAL:
            with pytest.raises(RecipeInvalid, match="^normalize: band red has no valid value over the AOI$"):
                do_run(
                    recipe([step(_with(METHODS[method], bands=["red", "nir"]))], BOTH, aoi=corner), tmp_path / method
                )
            assert list((tmp_path / method).iterdir()) == []

    def test_negative_values(self, tmp_path: Path) -> None:
        data = recipe([DIFF, step(_with(ROBUST, bands=["Diff"]))], ["Diff"])
        result = do_run(data, tmp_path / "job")
        values = pixels_before(data, [DIFF], ["Diff"], tmp_path / "before")["Diff"]
        assert values.min() < 0 < values.max()
        assert_numbers(
            result.properties["earthx:normalize"][0]["bands"]["Diff"], expected_numbers(values, "robust", ROBUST)
        )

    def test_a_band_without_scale_stays_whole_numbers(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        raw = (sources.ramp(WIDTH, HEIGHT, 100) % 3000) + 1
        path = sources.build_band_cog(tmp_path / "raw.tif", raw, scale=None, offset=None)
        sources.serve({sources.url("raw"): path}, monkeypatch)
        entry = _entry("red")
        entry["asset"]["asset"] = "raw"
        entry["asset"]["href"] = sources.url("raw")
        entry["scaling"], entry["bands"] = "none", [{"data_type": "uint16", "nodata": 0, "scale": None, "offset": None}]
        data = recipe([step(_with(PERCENTILE, bands=["raw"]))], ["raw"], assets=("red",))
        data["inputs"][0]["assets"], data["inputs"][0]["resolved"] = ["raw"], [entry]
        result = do_run(data, tmp_path / "job")
        found = result.properties["earthx:normalize"][0]["bands"]["raw"]
        valid = raw[raw != 0].astype("float64")
        assert found == {"p_low": nearest_rank(valid, 2), "p_high": nearest_rank(valid, 98)}
        assert float(found["p_low"]).is_integer() and float(found["p_high"]).is_integer()

    def test_a_constant_band_divides_by_one(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        raw = numpy.full((HEIGHT, WIDTH), 1234, dtype="uint16")
        path = sources.build_band_cog(tmp_path / "flat.tif", raw)
        sources.serve({sources.url("red"): path}, monkeypatch)
        for method in STATISTICAL:
            data = recipe([step(_with(METHODS[method], bands=["red"]))], ["red"], assets=("red",))
            result = do_run(data, tmp_path / method)
            numbers = result.properties["earthx:normalize"][0]["bands"]["red"]
            assert len(set(numbers.values()) - {0.0}) <= 1, "one level, and a spread of 0"
            with rasterio.open(result.path) as file:
                out = file.read(1)
            assert set(numpy.unique(out).tolist()) == {0.0}, "centred only: a spread of 0 divides as 1"

    def test_integers_of_thirty_two_bits_are_rounded_outwards(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        raw = (numpy.random.default_rng(5).integers(2**26, 2**27, (HEIGHT, WIDTH))).astype("int32")
        path = sources.build_band_cog(tmp_path / "big.tif", raw, scale=None, offset=None, nodata=0)
        sources.serve({sources.url("red"): path}, monkeypatch)
        entry = _entry("red")
        entry["scaling"], entry["bands"] = "none", [{"data_type": "int32", "nodata": 0, "scale": None, "offset": None}]
        data = recipe([step(_with(PERCENTILE, bands=["red"], clip=False))], ["red"], assets=("red",))
        data["inputs"][0]["resolved"] = [entry]
        found = do_run(data, tmp_path / "job").properties["earthx:normalize"][0]["bands"]["red"]
        values = raw.astype("float64").ravel()
        low, high = nearest_rank(values, 2), nearest_rank(values, 98)
        assert (
            found["p_low"] <= low
            and low - found["p_low"] <= 2**3
            and found["p_high"] >= high
            and found["p_high"] - high <= 2**3
        )


@pytest.mark.usefixtures("served")
class TestInAChain:
    def test_after_band_math(self, tmp_path: Path) -> None:
        data = recipe([NDVI, step(_with(PERCENTILE, bands=["NDVI"]))], ["NDVI"])
        result = do_run(data, tmp_path / "job")
        (entry,) = result.properties["earthx:normalize"]
        assert entry["step"] == 1 and list(entry["bands"]) == ["NDVI"]
        values = pixels_before(data, [NDVI], ["NDVI"], tmp_path / "before")["NDVI"]
        assert_numbers(entry["bands"]["NDVI"], expected_numbers(values, "percentile", PERCENTILE))
        three = do_run(as_version_3(data, result), tmp_path / "three")
        assert sha(result.path) == sha(three.path)

    def test_after_mask_only_the_pixels_that_remain_count(self, tmp_path: Path) -> None:
        data = recipe([MASK, step(_with(ZSCORE, bands=["red"]))], ["red"], assets=("red", "nir", "scl"))
        result = do_run(data, tmp_path / "job")
        masked = pixels_before(data, [MASK], ["red"], tmp_path / "before")["red"]
        everything = pixels_before(data, [], ["red"], tmp_path / "all")["red"]
        assert masked.size < everything.size
        assert_numbers(
            result.properties["earthx:normalize"][0]["bands"]["red"], expected_numbers(masked, "zscore", ZSCORE)
        )
        assert result.properties["earthx:normalize"][0]["bands"]["red"]["mean"] != pytest.approx(
            everything.mean(), rel=1e-9
        )

    def test_after_reproject_on_the_grid_of_the_result(self, tmp_path: Path) -> None:
        data = recipe([REPROJECT, step(_with(ROBUST, bands=["red"]))], ["red"], assets=("red", "nir"))
        result = do_run(data, tmp_path / "job")
        values = pixels_before(data, [REPROJECT], ["red"], tmp_path / "before")["red"]
        assert_numbers(
            result.properties["earthx:normalize"][0]["bands"]["red"],
            expected_numbers(values, "robust", ROBUST),
            float64_only=True,
        )
        assert result.properties["proj:code"] == "EPSG:3035"
        three = do_run(as_version_3(data, result), tmp_path / "three")
        assert sha(result.path) == sha(three.path)

    def test_two_measuring_steps_are_two_cuts_and_the_second_sees_the_first(self, tmp_path: Path) -> None:
        first = step(_with(ZSCORE, bands=["red"]))
        second = step(_with(PERCENTILE, bands=["red"]))
        data = recipe([first, second], ["red"])
        result = do_run(data, tmp_path / "job")
        one, two = result.properties["earthx:normalize"]
        assert (one["step"], one["method"], two["step"], two["method"]) == (0, "zscore", 1, "percentile")
        raw = pixels_before(data, [], ["red"], tmp_path / "raw")["red"]
        assert_numbers(one["bands"]["red"], expected_numbers(raw, "zscore", ZSCORE))
        after_first = {**data, "steps": [step(_with(ZSCORE, bands=["red"]), 3)]}
        after_first["steps"][0]["params"]["measured"] = {"factor": 1, "bands": {"red": one["bands"]["red"]}}
        centred = pixels_before(after_first, after_first["steps"], ["red"], tmp_path / "centred")["red"]
        assert_numbers(two["bands"]["red"], expected_numbers(centred, "percentile", PERCENTILE))
        assert result.properties["processing:lineage"] == (
            "normalize: zscore of red; normalize: percentiles 2 to 98 to [0, 1], clipped of red"
        )

    def test_a_band_the_planner_drops_is_not_measured_and_not_reported(self, tmp_path: Path) -> None:
        data = recipe([step(_with(ZSCORE, bands=["red", "nir"]))], ["nir"])
        result = do_run(data, tmp_path / "job")
        (entry,) = result.properties["earthx:normalize"]
        assert list(entry["bands"]) == ["nir"]
        values = pixels_before(data, [], ["nir"], tmp_path / "before")["nir"]
        assert_numbers(entry["bands"]["nir"], expected_numbers(values, "zscore", ZSCORE))

    def test_a_step_whose_bands_are_all_dropped_does_not_run_and_is_not_reported(self, tmp_path: Path) -> None:
        result = do_run(recipe([step(_with(ZSCORE, bands=["red"]))], ["nir"]), tmp_path)
        assert "earthx:normalize" not in result.properties
        assert "normalize" not in result.properties["processing:lineage"]

    def test_a_measuring_first_step_reads_the_inputs_in_an_empty_pass_of_its_own(self, tmp_path: Path) -> None:
        seen: list[int] = []
        do_run(recipe([step(ZSCORE)], BOTH), tmp_path, progress=lambda done, total: seen.append(total))
        assert seen[-1] == 2 * 4

    def test_a_measuring_step_with_no_valid_value_after_a_mask_fails_the_run(self, tmp_path: Path) -> None:
        allmasked = {"op": "mask", "op_version": 2, "params": {"source": "scl", "classes": list(range(1, 12))}}
        data = recipe([allmasked, step(_with(ZSCORE, bands=["red"]))], ["red"], assets=("red", "scl"))
        with pytest.raises(RecipeInvalid, match="band red has no valid value over the AOI"):
            do_run(data, tmp_path)
        assert list(tmp_path.iterdir()) == []

    def test_a_chain_without_a_measuring_step_has_no_property_and_the_bytes_of_before(self, tmp_path: Path) -> None:
        result = do_run(recipe([NDVI], ["NDVI"]), tmp_path)
        assert "earthx:normalize" not in result.properties


@pytest.mark.usefixtures("served")
class TestVersion3Stays:
    """Version 3 keeps its numbers in the recipe: accepted, run as before, the hash of its recipes unchanged."""

    V3 = {
        "method": "percentile",
        "bands": BOTH,
        "low": 2,
        "high": 98,
        **_TARGET,
        "measured": {
            "factor": 1,
            "bands": {"red": {"p_low": 0.12, "p_high": 0.3}, "nir": {"p_low": 0.35, "p_high": 0.5}},
        },
    }

    def test_the_hash_of_a_fixed_recipe_is_the_one_it_always_had(self) -> None:
        from earthx.processing.recipe import recipe_hash

        data = recipe([step(self.V3, 3)], BOTH)
        assert recipe_hash(recipe_from_data(data, REGISTRY)) == (
            "c1:46d9b97b27ce29fbbae917ea38583f8bae5ea9ed1b48203ade165a51243c82c8"
        )

    def test_a_run_uses_the_numbers_of_the_recipe_and_measures_nothing(self, tmp_path: Path) -> None:
        result = do_run(recipe([step(self.V3, 3)], BOTH), tmp_path / "job")
        assert "earthx:normalize" not in result.properties
        before = do_run(
            {**recipe([], BOTH), "output": {**recipe([], BOTH)["output"], "dtype": "float64"}}, tmp_path / "x"
        )
        with rasterio.open(before.path) as red, rasterio.open(result.path) as out:
            line = numpy.clip((red.read(1) - 0.12) / (0.3 - 0.12), 0.0, 1.0).astype("float32")
            numpy.testing.assert_array_equal(
                out.read(1), numpy.where(numpy.isnan(red.read(1)), numpy.float32("nan"), line)
            )

    def test_the_numbers_of_the_recipe_are_not_the_numbers_of_the_run(self, tmp_path: Path) -> None:
        """The counter-sample of the pair: version 3 and 4 differ exactly where the numbers differ."""
        three = do_run(recipe([step(self.V3, 3)], BOTH), tmp_path / "three")
        four = do_run(recipe([step({k: v for k, v in self.V3.items() if k != "measured"})], BOTH), tmp_path / "four")
        assert sha(three.path) != sha(four.path)
        assert four.properties["earthx:normalize"][0]["bands"]["red"] != self.V3["measured"]["bands"]["red"]


@pytest.mark.usefixtures("served")
class TestBeforeAGridStep:
    """The panel puts Normalize above Reproject: the numbers are those of the raster before the warp (NM4-71, Otto)."""

    @pytest.mark.parametrize("method", ["percentile", "zscore"])
    def test_the_numbers_are_those_of_the_start_of_the_chain_over_the_aoi_on_the_raster_before_the_warp(
        self, method: str, tmp_path: Path
    ) -> None:
        aoi = diamond(WIDTH, HEIGHT)
        data = recipe([step(_with(METHODS[method], bands=["red"])), REPROJECT], ["red"], aoi=aoi)
        result = do_run(data, tmp_path / "job")
        (entry,) = result.properties["earthx:normalize"]
        assert (entry["step"], entry["method"], entry["exact"]) == (0, method, True)
        found = entry["bands"]["red"]
        assert result.properties["proj:code"] == "EPSG:3035"
        # What the preview measures: the start of the chain up to the step, the route's own code without a limit.
        start = recipe([], ["red"], aoi=aoi, dtype="float64")
        route = area_statistics(
            recipe_from_data(start, REGISTRY), max_pixels=10**12, extra_percentiles=MEASURE_PERCENTILES
        )
        assert route.factor == 1
        statistics = route.bands[0]["statistics"]
        if method == "zscore":
            assert (found["mean"], found["stddev"]) == (statistics["mean"], statistics["stddev"])
        else:
            # The route's percentiles are the edges of the bins of the histogram: the exact ones lie inside them.
            assert statistics["percentile_2"] <= found["p_low"] < found["p_high"] <= statistics["percentile_98"]
        values = pixels_before(data, [], ["red"], tmp_path / "before")["red"]
        assert values.size == statistics["count"] < WIDTH * HEIGHT
        assert statistics["minimum"] == values.min() and statistics["maximum"] == values.max()
        assert_numbers(found, expected_numbers(values, method, METHODS[method]))

    @pytest.mark.parametrize("method", ["percentile", "zscore"])
    def test_version_3_with_those_numbers_gives_the_bytes_of_version_4(self, method: str, tmp_path: Path) -> None:
        data = recipe([step(_with(METHODS[method], bands=["red"])), REPROJECT], ["red"], aoi=diamond(WIDTH, HEIGHT))
        measured = do_run(data, tmp_path / "four")
        third = do_run(as_version_3(data, measured), tmp_path / "three")
        assert sha(measured.path) == sha(third.path) and sha(measured.mask_path) == sha(third.mask_path)

    def test_a_cut_before_and_one_after_the_warp_each_count_on_their_own_raster(self, tmp_path: Path) -> None:
        aoi = diamond(WIDTH, HEIGHT)
        data = recipe(
            [step(_with(ZSCORE, bands=["red"])), REPROJECT, step(_with(ROBUST, bands=["red"]))], ["red"], aoi=aoi
        )
        result = do_run(data, tmp_path / "job")
        before, after = result.properties["earthx:normalize"]
        assert (before["step"], after["step"]) == (0, 2)
        raw = pixels_before(data, [], ["red"], tmp_path / "raw")["red"]
        assert_numbers(before["bands"]["red"], expected_numbers(raw, "zscore", ZSCORE))
        first = step(_with(ZSCORE, bands=["red"]), 3)
        first["params"]["measured"] = {"factor": 1, "bands": {"red": before["bands"]["red"]}}
        warped = pixels_before({**data, "steps": [first, REPROJECT]}, [first, REPROJECT], ["red"], tmp_path / "warped")
        assert_numbers(after["bands"]["red"], expected_numbers(warped["red"], "robust", ROBUST), float64_only=True)
        assert sha(result.path) == sha(do_run(as_version_3(data, result), tmp_path / "three").path)

    def test_the_files_of_the_work_directory_are_still_two_at_most(self, tmp_path: Path) -> None:
        snapshots: list[list[str]] = []
        tmp_path.mkdir(exist_ok=True)
        data = recipe([step(_with(ZSCORE, bands=["red"])), REPROJECT], ["red"])
        do_run(data, tmp_path, progress=lambda done, total: snapshots.append(_names(tmp_path)))
        assert max(len([n for n in names if n.startswith("pass-")]) for names in snapshots) == 2
        assert _names(tmp_path) == ["mask.tif", "result.tif"]


# --- the work directory ---------------------------------------------------------------------------------------------


def _names(directory: Path) -> list[str]:
    return sorted(path.name for path in directory.iterdir())


@pytest.mark.usefixtures("served")
class TestWorkFilesAreDeletedAsSoonAsTheirReaderIsDone:
    def test_a_finished_run_leaves_only_the_result_and_the_mask(self, tmp_path: Path) -> None:
        do_run(recipe([step(PERCENTILE)], BOTH), tmp_path)
        assert _names(tmp_path) == ["mask.tif", "result.tif"]

    def test_at_most_two_pass_files_lie_there_at_once_and_none_survives_its_reader(self, tmp_path: Path) -> None:
        snapshots: list[list[str]] = []
        tmp_path.mkdir(exist_ok=True)
        data = recipe(
            [
                step(_with(ZSCORE, bands=["red"])),
                step(_with(PERCENTILE, bands=["red"])),
                step(_with(ROBUST, bands=["nir"])),
            ],
            BOTH,
        )
        do_run(data, tmp_path, progress=lambda done, total: snapshots.append(_names(tmp_path)))
        passes = [[name for name in names if name.startswith("pass-")] for names in snapshots]
        assert max(len(names) for names in passes) == 2
        seen = {name for names in passes for name in names}
        assert seen == {"pass-1.tif", "pass-2.tif", "pass-3.tif", "pass-4.tif"}
        assert _names(tmp_path) == ["mask.tif", "result.tif"]
        # A file is gone before the pass after the next one writes: pass-1 never lies beside pass-3.
        assert not any(
            {"pass-1.tif", "pass-3.tif"} <= set(names) or {"pass-2.tif", "pass-4.tif"} <= set(names) for names in passes
        )

    def test_a_run_without_a_measuring_step_deletes_its_pass_files_too(self, tmp_path: Path) -> None:
        snapshots: list[list[str]] = []
        tmp_path.mkdir(exist_ok=True)
        data = recipe([REPROJECT, step(LINEAR, 3)], ["red"], assets=("red", "nir"))
        do_run(data, tmp_path, progress=lambda done, total: snapshots.append(_names(tmp_path)))
        assert max(len([n for n in names if n.startswith("pass-")]) for names in snapshots) <= 2
        assert _names(tmp_path) == ["mask.tif", "result.tif"]

    @pytest.mark.parametrize("method", ["zscore", "percentile"])
    def test_an_error_in_the_second_pass_leaves_nothing(self, method: str, tmp_path: Path) -> None:
        first_pass = 4
        looks = 0 if method == "zscore" else 4

        def fail(done: int, total: int) -> None:
            if done == 2 * first_pass + looks - 1:
                raise RuntimeError("the disk is full")

        tmp_path.mkdir(exist_ok=True)
        with pytest.raises(RuntimeError, match="disk is full"):
            do_run(recipe([step(METHODS[method])], BOTH), tmp_path, progress=fail)
        assert _names(tmp_path) == []

    @pytest.mark.parametrize("method", ["zscore", "percentile"])
    def test_a_cancel_in_the_second_pass_leaves_nothing(self, method: str, tmp_path: Path) -> None:
        looks = 0 if method == "zscore" else 4

        def cancel(done: int, total: int) -> None:
            if done == 4 + looks + 2:
                raise RunCancelled()

        tmp_path.mkdir(exist_ok=True)
        with pytest.raises(RunCancelled):
            do_run(recipe([step(METHODS[method])], BOTH), tmp_path, progress=cancel)
        assert _names(tmp_path) == []

    def test_a_cancel_during_the_second_look_leaves_nothing(self, tmp_path: Path) -> None:
        def cancel(done: int, total: int) -> None:
            if done == 4 + 2:
                raise RunCancelled()

        tmp_path.mkdir(exist_ok=True)
        with pytest.raises(RunCancelled):
            do_run(recipe([step(ROBUST)], BOTH), tmp_path, progress=cancel)
        assert _names(tmp_path) == []


# --- bit-stability across CPU levels (adr/0016 §3.3) --------------------------------------------------------------

_MEASURE_PROBE = textwrap.dedent(
    """
    import json
    import numpy
    from earthx.processing.statistics import BandStatistics

    rng = numpy.random.default_rng(11)
    out = {}
    for name, values in {
        "float64 normal": rng.normal(0.3, 0.2, 700_000),
        "float32 gamma": rng.gamma(2.0, 0.1, 700_000).astype("float32").astype("float64"),
        "float64 wide": rng.standard_cauchy(700_000) * 1e3,
    }.items():
        statistics = BandStatistics("float64")
        blocks = numpy.array_split(values, 7)
        for block in blocks:
            statistics.add(block)
        refinement = statistics.refine_targets((2, 25, 50, 75, 98))
        for block in blocks:
            refinement.add(block)
        summary = statistics.summary(values.size)
        out[name] = {key: repr(summary[key]) for key in ("minimum", "maximum", "mean", "stddev")}
        out[name]["percentiles"] = {str(k): repr(v) for k, v in refinement.values().items()}
    print(json.dumps(out))
    """
)


def _measure_probe(env_extra: dict[str, str]) -> dict:
    backend = str(Path(__file__).resolve().parents[3])
    done = subprocess.run(
        [sys.executable, "-c", _MEASURE_PROBE],
        capture_output=True,
        text=True,
        env={**os.environ, **env_extra, "PYTHONPATH": backend},
        timeout=300,
        check=False,
    )
    assert done.returncode == 0, done.stderr[-2000:]
    return json.loads(done.stdout.strip().splitlines()[-1])


class TestTheMeasureIsBitStableAcrossCpuLevels:
    """The numbers enter the bytes of the result: a sum that numpy orders differently on another CPU would move them."""

    def test_the_numbers_are_the_same_under_settings_a_and_d(self) -> None:
        if not _glibc_masks_features():
            pytest.skip("GLIBC_TUNABLES does not change the CPU features this loader reports: setting D is not one")
        setting_a, setting_d = _measure_probe({}), _measure_probe(_SETTING_D)
        assert set(setting_a) == {"float64 normal", "float32 gamma", "float64 wide"}
        assert setting_a == setting_d
