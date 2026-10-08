"""The ``band_math`` operator: R5 on the expression, the kernel, and bit-stability across CPU levels.

adr/0014 §3.2, §5.2, §15c; adr/0016 §3.3, §12a; plan M4-09 §3.1, §3.5. Nothing here reads a
file: the kernel runs on arrays, the check on text.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from dataclasses import replace
from pathlib import Path

import numpy
import pytest
from pydantic import ValidationError
from rasterio.transform import Affine
from rio_tiler.models import ImageData

from earthx.catalog.datasets import COP_DEM_GLO_30, SENTINEL_2_L2A, SENTINEL_2_L2A_ZARR3
from earthx.catalog.registry import LicenseTier
from earthx.processing.errors import RecipeInvalid
from earthx.processing.operators import BAND_MATH, REGISTRY, BandMathParams, BandMeta, RasterMeta, applicable
from earthx.processing.operators.band_math import FUNCTIONS, MAX_EXPONENT, MAX_EXPRESSION_CHARS, check_expression

NDVI = "(nir - red) / (nir + red)"


def _params(expression: str) -> BandMathParams:
    return BandMathParams(expression=expression)


def _image(**bands: numpy.ndarray) -> ImageData:
    data = numpy.ma.stack([numpy.ma.masked_array(values) for values in bands.values()])
    return ImageData(data, bounds=(0, 0, 1, 1), crs="EPSG:32632", band_names=list(bands))


def _meta(*names: str) -> RasterMeta:
    bands = tuple(BandMeta(name, "float32", None) for name in names)
    return RasterMeta("EPSG:32632", Affine(10, 0, 0, 0, -10, 0), 4, 4, bands)


ALLOWED = [
    NDVI,
    "nir - red",
    "-red + 1",
    "red * 2.5e-1",
    "red ** 2",
    "red ** -3",
    f"red ** {MAX_EXPONENT}",
    "red ** -50",
    "red ** 0",
    "abs(red - nir)",
    "sqrt(abs(red))",
    "minimum(red, nir)",
    "maximum(red, 0.2)",
    "where(red > 0.1, nir, red)",
    "where((red > 0) & (nir > 0), (nir - red) / (nir + red), 0)",
    "where((red < 0) | (nir < 0), 0, 1)",
    "where(~(red > 0.3), red, nir)",
    "where((red > 0) & ~(nir > 1) | (nir == 0), 1, 0)",
    "red > nir",
    "(red >= 0) & (red != nir)",
]

REFUSED = {
    "a function outside the list: log": "log(red)",
    "a function outside the list: exp": "exp(red)",
    "a function outside the list: sin": "sin(red)",
    "a function outside the list: arctan2": "arctan2(red, nir)",
    "a function outside the list: copy": "copy(red)",
    "a function outside the list: sum": "sum(red)",
    "an attribute": "red.real",
    "a dunder attribute": "red.__class__",
    "a call through an attribute": "numpy.log(red)",
    "an import": "__import__('os')",
    "a name that starts with an underscore": "_red + 1",
    "a subscript": "red[0]",
    "a lambda": "(lambda: 1)()",
    "a conditional expression": "red if nir else 0",
    "a keyword argument": "where(c=red > 0, a=1, b=2)",
    "a call of a call": "abs(red)(nir)",
    "a call of a number": "(1)(red)",
    "a function as a name": "where + 1",
    "modulo": "red % 2",
    "floor division": "red // 2",
    "a shift": "red << 1",
    "xor": "(red > 0) ^ (nir > 0)",
    "a power above the limit": f"red ** {MAX_EXPONENT + 1}",
    "a negative power above the limit": f"red ** -{MAX_EXPONENT + 1}",
    "a fractional power": "red ** 0.5",
    "a fractional power written as a division": "red ** (1 / 2)",
    "a power of a power": "red ** (2 ** 2)",
    "a power by a band": "red ** nir",
    "a power with a base that is a number written out": "2 ** red",
    "a boolean exponent": "red ** True",
    "an exponent that is a float with a whole value": "red ** 2.0",
    "a boolean constant": "True",
    "a complex number": "1j * red",
    "a text": "'red'",
    "None": "None + red",
    "a number too large to be a float": "red * " + "9" * 400,
    "a chained comparison": "0 < red < 1",
    "a comparison with a non-comparison operator": "red is nir",
    "membership": "red in nir",
    "not": "not red",
    "& on numbers": "red & nir",
    "| on numbers": "red | nir",
    "~ on a number": "~red",
    "a number & a truth value": "red & (nir > 0)",
    "& binding tighter than the comparison": "red > 0 & nir > 0",
    "a sign on a truth value": "-(red > 0)",
    "arithmetic on a truth value": "(red > 0) + 1",
    "a comparison of truth values": "(red > 0) == (nir > 0)",
    "a number as the condition of where": "where(red, nir, red)",
    "a truth value as a number in where": "where(red > 0, red > 1, 0)",
    "where with two arguments": "where(red > 0, nir)",
    "abs with two arguments": "abs(red, nir)",
    "minimum with one argument": "minimum(red)",
    "sqrt of a truth value": "sqrt(red > 0)",
    "no band at all": "1 + 2",
    "an empty expression": "",
    "only blanks": "   ",
    "two expressions (rio-tiler's separator)": "red; nir",
    "a statement": "red = 1",
    "a newline": "red +\nnir",
    "a non-ASCII character": "rèd + 1",
    "a syntax error": "red +",
    "unbalanced brackets": "((red + 1)",
    "brackets nested deeper than Python parses": "(" * 250 + "red" + ")" * 250,
    "too long": "red + " * (MAX_EXPRESSION_CHARS // 6 + 1) + "red",
}


class TestAllowedExpressions:
    @pytest.mark.parametrize("expression", ALLOWED)
    def test_the_expression_passes_and_names_its_bands(self, expression: str) -> None:
        assert check_expression(expression) <= {"red", "nir"}
        assert _params(expression).expression == expression

    def test_the_longest_allowed_expression(self) -> None:
        expression = "red" + " + red" * ((MAX_EXPRESSION_CHARS - 3) // 6)
        assert len(expression) <= MAX_EXPRESSION_CHARS
        check_expression(expression)

    def test_the_list_of_functions_is_the_bit_stable_one(self) -> None:
        assert set(FUNCTIONS) == {"where", "abs", "minimum", "maximum", "sqrt"}


class TestRefusedExpressions:
    @pytest.mark.parametrize("expression", REFUSED.values(), ids=list(REFUSED))
    def test_the_check_refuses_with_a_value_error_and_never_an_error_out_of_numexpr(self, expression: str) -> None:
        with pytest.raises(ValueError, match="^expression: ") as caught:
            check_expression(expression)
        assert len(str(caught.value)) < 120  # a reason, not the expression back

    @pytest.mark.parametrize("expression", REFUSED.values(), ids=list(REFUSED))
    def test_the_parameter_model_refuses_it_as_a_validation_error(self, expression: str) -> None:
        with pytest.raises(ValidationError):
            BandMathParams.model_validate_json(json.dumps({"expression": expression}), strict=True)

    def test_a_text_that_is_not_a_string_is_refused(self) -> None:
        for value in (None, 1, ["red"], {"expression": "red"}):
            with pytest.raises(ValidationError):
                BandMathParams.model_validate_json(json.dumps({"expression": value}), strict=True)

    def test_an_extra_parameter_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            BandMathParams.model_validate_json('{"expression": "red", "unscale": false}', strict=True)

    def test_the_text_of_a_refusal_does_not_repeat_a_long_expression(self) -> None:
        secret = "band_that_should_not_be_echoed_back_anywhere"
        with pytest.raises(ValueError) as caught:
            check_expression(f"{secret} % 2")
        assert secret not in str(caught.value)


class TestTheSchema:
    def test_the_json_schema_is_the_panels_form_and_has_no_pattern(self) -> None:
        schema = REGISTRY.params_schema("band_math", 1)
        assert schema["$schema"].endswith("2020-12/schema")
        assert schema["additionalProperties"] is False
        assert schema["required"] == ["expression"]
        text = json.dumps(schema)
        assert '"pattern"' not in text
        assert schema["properties"]["expression"]["maxLength"] == MAX_EXPRESSION_CHARS

    def test_it_is_a_pixel_operator_for_the_tile_and_the_job(self) -> None:
        assert BAND_MATH.kind == "pixel"
        assert {tier.value for tier in BAND_MATH.tiers} == {"T1", "T2"}
        assert BAND_MATH.op_version == 1


class TestApplicability:
    def test_the_datasets_that_allow_band_math_get_it(self) -> None:
        for config in (SENTINEL_2_L2A, SENTINEL_2_L2A_ZARR3, COP_DEM_GLO_30):
            assert applicable(BAND_MATH, config, _params("a + b")) == []

    def test_a_dataset_without_the_capability_is_refused_by_name(self) -> None:
        config = replace(SENTINEL_2_L2A, capabilities=replace(SENTINEL_2_L2A.capabilities, band_math=False))
        reasons = applicable(BAND_MATH, config, _params("a + b"))
        assert reasons == [f"{config.dataset_id} does not allow band_math"]

    def test_a_licence_below_processing_is_refused(self) -> None:
        config = replace(SENTINEL_2_L2A, license=replace(SENTINEL_2_L2A.license, tier=LicenseTier.DISPLAY))
        assert any("processing" in reason for reason in applicable(BAND_MATH, config, _params("a + b")))


class TestTheKernel:
    def test_ndvi_is_the_formula_in_float32(self) -> None:
        red = numpy.array([[0.1, 0.2], [0.3, 0.4]])
        nir = numpy.array([[0.5, 0.6], [0.3, 0.1]])
        result = BAND_MATH.run(_image(red=red.astype("float32"), nir=nir.astype("float32")), _params(NDVI))
        assert result.array.dtype == numpy.float32
        assert result.band_names == ["band_math"]
        expected = ((nir.astype("float32").astype("float64") - red.astype("float32").astype("float64"))
                    / (nir.astype("float32").astype("float64") + red.astype("float32").astype("float64"))).astype("float32")
        numpy.testing.assert_array_equal(result.array[0].data, expected)
        assert not result.array.mask.any()

    def test_the_inputs_are_float64_so_integers_cannot_wrap_around(self) -> None:
        """numpy would give 12.9072 for uint16 ``n - r`` with r > n (adr/0014 §3.2); the kernel does not."""
        red = numpy.array([[3000]], dtype="uint16")
        nir = numpy.array([[2000]], dtype="uint16")
        result = BAND_MATH.run(_image(red=red, nir=nir), _params(NDVI))
        assert float(result.array[0, 0, 0]) == pytest.approx(-0.2, abs=1e-7)

    def test_a_division_by_zero_is_masked_not_a_valid_number(self) -> None:
        red = numpy.array([[0.0, 0.0, 1.0]])
        nir = numpy.array([[0.0, 1.0, 0.0]])
        result = BAND_MATH.run(_image(red=red, nir=nir), _params("nir / red"))
        assert result.array.mask[0, 0].tolist() == [True, True, False]

    def test_infinity_and_nan_are_masked(self) -> None:
        values = numpy.array([[1.0, 0.0, -1.0, 4.0]])
        result = BAND_MATH.run(_image(a=values), _params("1 / a"))
        assert result.array.mask[0, 0].tolist() == [False, True, False, False]
        assert numpy.isnan(numpy.ma.getdata(result.array)[0, 0, 1])
        result = BAND_MATH.run(_image(a=values), _params("sqrt(a)"))
        assert result.array.mask[0, 0].tolist() == [False, False, True, False]

    def test_a_pixel_is_masked_where_a_band_the_expression_names_is_masked(self) -> None:
        red = numpy.ma.masked_array([[1.0, 2.0]], mask=[[True, False]])
        nir = numpy.ma.masked_array([[1.0, 2.0]], mask=[[False, False]])
        other = numpy.ma.masked_array([[1.0, 2.0]], mask=[[False, True]])
        image = ImageData(
            numpy.ma.stack([red, nir, other]),
            bounds=(0, 0, 1, 1),
            crs="EPSG:32632",
            band_names=["red", "nir", "other"],
        )
        assert BAND_MATH.run(image, _params("red + nir")).array.mask[0, 0].tolist() == [True, False]
        assert BAND_MATH.run(image, _params("nir")).array.mask[0, 0].tolist() == [False, False]
        assert BAND_MATH.run(image, _params("nir + other")).array.mask[0, 0].tolist() == [False, True]

    def test_a_truth_value_becomes_one_and_zero(self) -> None:
        values = numpy.array([[0.5, 1.5]])
        result = BAND_MATH.run(_image(a=values), _params("a > 1"))
        assert result.array[0, 0].tolist() == [0.0, 1.0]

    @pytest.mark.parametrize(
        ("expression", "expected"),
        [
            ("where((a > 0) & (b > 0), a + b, -1)", [-1.0, -1.0, 3.0, -1.0]),
            ("where((a > 0) | (b > 0), 1, 0)", [0.0, 1.0, 1.0, 0.0]),
            ("where(~(a > 0), 1, 0)", [1.0, 0.0, 0.0, 1.0]),
            ("minimum(a, b)", [-1.0, 0.0, 1.0, 0.0]),
            ("maximum(a, b)", [0.0, 2.0, 2.0, 0.0]),
            ("abs(a - b)", [1.0, 2.0, 1.0, 0.0]),
        ],
    )
    def test_the_functions_and_combinations(self, expression: str, expected: list[float]) -> None:
        a = numpy.array([[-1.0, 2.0, 1.0, 0.0]])
        b = numpy.array([[0.0, 0.0, 2.0, 0.0]])
        result = BAND_MATH.run(_image(a=a, b=b), _params(expression)).array
        assert numpy.ma.getdata(result)[0, 0].tolist() == expected

    def test_a_power_is_exact_where_numpy_multiplication_is(self) -> None:
        a = numpy.linspace(0.5, 1.5, 1000).reshape(1, 1000)
        for exponent in (2, 3, 7):
            result = BAND_MATH.run(_image(a=a), _params(f"a ** {exponent}"))
            expected = numpy.ones_like(a)
            for _ in range(exponent):
                expected = expected * a
            numpy.testing.assert_array_equal(numpy.ma.getdata(result.array)[0], expected.astype("float32"))

    def test_the_kernel_is_deterministic_and_leaves_the_input_alone(self) -> None:
        image = _image(red=numpy.random.default_rng(1).uniform(0, 1, (8, 8)), nir=numpy.full((8, 8), 0.3))
        before = image.array.copy()
        first = BAND_MATH.run(image, _params(NDVI)).array
        second = BAND_MATH.run(image, _params(NDVI)).array
        assert first.tobytes() == second.tobytes()
        numpy.testing.assert_array_equal(image.array.data, before.data)

    def test_an_unknown_band_is_a_named_error_listing_the_bands(self) -> None:
        with pytest.raises(RecipeInvalid, match=r"unknown band\(s\): swir; the input has: red, nir"):
            BAND_MATH.run(_image(red=numpy.zeros((2, 2)), nir=numpy.zeros((2, 2))), _params("swir + red"))

    def test_the_kernel_checks_the_expression_again_itself(self) -> None:
        loose = BandMathParams.model_construct(expression="log(red)")
        with pytest.raises(ValueError, match="functions are"):
            BAND_MATH.run(_image(red=numpy.ones((2, 2))), loose)


class TestTransform:
    def test_one_float_band_with_a_nan_nodata_on_the_same_grid(self) -> None:
        meta = BAND_MATH.transform(_meta("red", "nir"), _params(NDVI))
        assert [(b.name, b.data_type) for b in meta.bands] == [("band_math", "float32")]
        assert numpy.isnan(meta.bands[0].nodata)
        assert (meta.crs, meta.transform, meta.width, meta.height) == ("EPSG:32632", Affine(10, 0, 0, 0, -10, 0), 4, 4)

    def test_the_honesty_flag_is_carried_through(self) -> None:
        resampled = RasterMeta("EPSG:32632", Affine(10, 0, 0, 0, -10, 0), 4, 4, _meta("a").bands, resampled=True)
        assert BAND_MATH.transform(resampled, _params("a")).resampled is True
        assert BAND_MATH.transform(_meta("a"), _params("a")).resampled is False

    def test_an_unknown_band_fails_before_any_pixel(self) -> None:
        with pytest.raises(RecipeInvalid, match="unknown band"):
            BAND_MATH.transform(_meta("red"), _params("red + swir"))

    def test_the_result_can_feed_another_band_math(self) -> None:
        first = BAND_MATH.transform(_meta("red", "nir"), _params(NDVI))
        BAND_MATH.transform(first, _params("band_math * 2"))

    def test_the_lineage_and_the_property_carry_the_expression(self) -> None:
        params = _params(NDVI)
        assert BAND_MATH.lineage(params) == f"band math: {NDVI}"
        assert BAND_MATH.properties(params) == {"processing:expression": {"format": "numexpr", "expression": NDVI}}
        assert BAND_MATH.cost_factor(params) == 1.0


# --- bit-stability across CPU levels (adr/0016 §3.3, §12a; plan M4-09, K7) ---------------------

_PROBE = textwrap.dedent(
    """
    import hashlib, json, sys
    import numpy
    from rio_tiler.models import ImageData
    from earthx.processing.operators import BAND_MATH, BandMathParams

    rng = numpy.random.default_rng(42)
    a = rng.uniform(-0.2, 1.5, (512, 512))
    b = rng.uniform(-0.2, 1.5, (512, 512))
    expressions = json.loads(sys.argv[1])
    out = {}
    for dtype in ("float32", "float64"):
        data = numpy.ma.stack([numpy.ma.masked_array(a.astype(dtype)), numpy.ma.masked_array(b.astype(dtype))])
        image = ImageData(data, bounds=(0, 0, 1, 1), crs="EPSG:32632", band_names=["a", "b"])
        for expression in expressions:
            result = BAND_MATH.run(image, BandMathParams(expression=expression)).array
            out[f"{dtype}: {expression}"] = hashlib.sha256(numpy.ma.getdata(result).tobytes() + result.mask.tobytes()).hexdigest()
    print(json.dumps(out))
    """
)

#: Every function R5 allows, and powers around the limits; the same list a user can write.
_BIT_STABLE = [
    "(b - a) / (b + a)",
    "where(a > 0.3, a, b)",
    "where((a > 0.3) & ~(b < 0.1), a * b, a - b)",
    "abs(a - b)",
    "minimum(a, b)",
    "maximum(a, b)",
    "sqrt(abs(a))",
    "a ** 2",
    "a ** 3",
    "a ** 7",
    "a ** -2",
    "a ** 49",
    f"a ** {MAX_EXPONENT}",
    "b ** -50",
]

#: The settings of adr/0016 §3.3: A leaves the CPU as it is, D is a CPU of the x86-64-v2 level.
_SETTING_D = {
    "NPY_DISABLE_CPU_FEATURES": "X86_V3 X86_V4 AVX512_ICL AVX512_SPR",
    "GLIBC_TUNABLES": "glibc.cpu.hwcaps=-AVX2,-FMA,-AVX512F,-AVX512CD,-AVX512BW,-AVX512DQ,-AVX512VL",
}


def _probe(env_extra: dict[str, str], expressions: list[str]) -> dict[str, str]:
    backend = str(Path(__file__).resolve().parents[3])
    done = subprocess.run(
        [sys.executable, "-c", _PROBE, json.dumps(expressions)],
        capture_output=True,
        text=True,
        env={**os.environ, **env_extra, "PYTHONPATH": backend},
        timeout=300,
        check=False,
    )
    assert done.returncode == 0, done.stderr[-2000:]
    return json.loads(done.stdout.strip().splitlines()[-1])


def _glibc_masks_features() -> bool:
    """Does ``GLIBC_TUNABLES`` change what the loader reports? If not, setting D means nothing here."""
    loader = Path("/lib64/ld-linux-x86-64.so.2")
    if not loader.exists():
        return False

    def active(extra: dict[str, str]) -> str:
        done = subprocess.run(
            [str(loader), "--list-diagnostics"], capture_output=True, text=True, env={**os.environ, **extra}, check=False
        )
        return "".join(line for line in done.stdout.splitlines() if "features[0x0].active[0x2]" in line)

    return active({}) != active({"GLIBC_TUNABLES": _SETTING_D["GLIBC_TUNABLES"]})


class TestBitStabilityAcrossCpuLevels:
    def test_every_allowed_function_gives_the_same_bytes_under_settings_a_and_d(self) -> None:
        if not _glibc_masks_features():
            pytest.skip("GLIBC_TUNABLES does not change the CPU features this loader reports: setting D is not one")
        setting_a = _probe({}, _BIT_STABLE)
        setting_d = _probe(_SETTING_D, _BIT_STABLE)
        assert set(setting_a) == {f"{dtype}: {e}" for dtype in ("float32", "float64") for e in _BIT_STABLE}
        different = sorted(key for key in setting_a if setting_a[key] != setting_d[key])
        assert different == []

    def test_the_probe_would_notice_a_function_that_is_not_bit_stable(self) -> None:
        """Gegenprobe: ``log`` is outside R5 because of this; the probe sees it (adr/0016 §12a).

        The kernel refuses ``log``, so the probe goes around the check on purpose, with numexpr
        directly, to show that the two settings really differ on this machine for what R5 refuses.
        """
        if not _glibc_masks_features():
            pytest.skip("GLIBC_TUNABLES does not change the CPU features this loader reports")
        program = textwrap.dedent(
            """
            import hashlib, numpy, numexpr
            a = numpy.random.default_rng(42).uniform(0.1, 1.5, (1024, 1024))
            print(hashlib.sha256(numexpr.evaluate("log(a) + exp(a) + a ** 51", optimization="aggressive").tobytes()).hexdigest())
            """
        )
        def run(extra: dict[str, str]) -> str:
            done = subprocess.run(
                [sys.executable, "-I", "-c", program], capture_output=True, text=True, env={**os.environ, **extra}, check=True
            )
            return done.stdout.strip()

        assert run({}) != run(_SETTING_D)
