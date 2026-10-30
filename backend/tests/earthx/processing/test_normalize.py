"""The ``normalize`` operator: parameters, kernel against the formula, a run, and bit-stability across CPU levels.

Plan M4-18 §3.3, §3.6; adr/0014 §15c, §15m; adr/0016 §12a.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import textwrap
from dataclasses import replace
from pathlib import Path

import numpy
import pytest
import rasterio
from pydantic import ValidationError
from rasterio.transform import Affine
from rio_tiler.io import Reader
from rio_tiler.models import ImageData

from earthx.catalog.datasets import COP_DEM_GLO_30, SENTINEL_2_L2A
from earthx.processing import run
from earthx.processing.operators import NORMALIZE, REGISTRY, BandMeta, NormalizeParams, RasterMeta, applicable
from tests.earthx.processing import sources
from tests.earthx.processing.recipes import recipe_of_data, resolved
from tests.earthx.processing.test_band_math import _SETTING_D, _glibc_masks_features

WIDTH, HEIGHT = 700, 600


def _params(in_min=0.0, in_max=1.0, out_min=0.0, out_max=255.0, clip=True) -> NormalizeParams:
    return NormalizeParams(in_min=in_min, in_max=in_max, out_min=out_min, out_max=out_max, clip=clip)


def _image(*arrays: numpy.ndarray, mask=None) -> ImageData:
    stack = numpy.ma.stack([numpy.ma.masked_array(a, mask=mask) for a in arrays])
    return ImageData(stack, bounds=(0, 0, 1, 1), crs="EPSG:32632", band_names=[f"b{i}" for i in range(len(arrays))])


GOOD = {"in_min": 0.0, "in_max": 1.0, "out_min": 0.0, "out_max": 255.0, "clip": True}


class TestParameters:
    def test_a_valid_range_from_json(self) -> None:
        params = NormalizeParams.model_validate_json(json.dumps({**GOOD, "in_min": -1, "in_max": 1}), strict=True)
        assert (params.in_min, params.in_max) == (-1.0, 1.0)

    @pytest.mark.parametrize(
        "change",
        [
            {"in_min": 1.0},  # in_min equals in_max
            {"in_min": 2.0},  # in_min above in_max
            {"out_max": 0.0},  # out_min equals out_max
            {"in_min": "0"},
            {"clip": 1},
            {"clip": "true"},
            {"in_min": None},
            {"in_max": 1e308, "in_min": -1e308},  # the span overflows
            {"out_max": 1e308, "out_min": -1e308},
            {"extra": 1},
        ],
    )
    def test_misuse_is_refused(self, change: dict) -> None:
        with pytest.raises(ValidationError):
            NormalizeParams.model_validate_json(json.dumps({**GOOD, **change}), strict=True)

    @pytest.mark.parametrize("missing", list(GOOD))
    def test_every_field_is_given(self, missing: str) -> None:
        data = {key: value for key, value in GOOD.items() if key != missing}
        with pytest.raises(ValidationError):
            NormalizeParams.model_validate_json(json.dumps(data), strict=True)

    @pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity"])
    def test_a_non_finite_number_is_refused(self, token: str) -> None:
        text = json.dumps(GOOD).replace('"in_max": 1.0', f'"in_max": {token}')
        with pytest.raises(ValidationError):
            NormalizeParams.model_validate_json(text, strict=True)

    def test_a_reversed_target_range_is_allowed(self) -> None:
        assert _params(out_min=1.0, out_max=0.0).out_max == 0.0


class TestKernel:
    def test_it_is_the_formula(self) -> None:
        values = numpy.array([[-0.5, 0.0, 0.25], [0.5, 1.0, 1.5]], dtype="float32")
        result = NORMALIZE.run(_image(values), _params(0.0, 1.0, 0.0, 255.0, clip=False))
        expected = (values.astype("float64") - 0.0) / 1.0 * 255.0 + 0.0
        assert result.array.dtype == numpy.float32
        numpy.testing.assert_array_equal(result.array.data[0], expected.astype("float32"))

    def test_clip_limits_to_the_target_range_and_without_it_the_line_continues(self) -> None:
        values = numpy.array([[-1.0, 0.5, 2.0]])
        clipped = NORMALIZE.run(_image(values), _params(0.0, 1.0, 0.0, 10.0, clip=True)).array.data[0]
        open_ = NORMALIZE.run(_image(values), _params(0.0, 1.0, 0.0, 10.0, clip=False)).array.data[0]
        numpy.testing.assert_array_equal(clipped, [[0.0, 5.0, 10.0]])
        numpy.testing.assert_array_equal(open_, [[-10.0, 5.0, 20.0]])

    def test_a_reversed_target_range_flips_and_clips_inside_it(self) -> None:
        values = numpy.array([[-1.0, 0.0, 1.0, 2.0]])
        result = NORMALIZE.run(_image(values), _params(0.0, 1.0, 1.0, 0.0, clip=True)).array.data[0]
        numpy.testing.assert_array_equal(result, [[1.0, 1.0, 0.0, 0.0]])

    def test_every_band_gets_the_same_range(self) -> None:
        a, b = numpy.array([[0.0, 1.0]]), numpy.array([[0.5, 2.0]])
        result = NORMALIZE.run(_image(a, b), _params(0.0, 2.0, 0.0, 1.0, clip=False))
        numpy.testing.assert_array_equal(result.array.data[:, 0], [[0.0, 0.5], [0.25, 1.0]])
        assert list(result.band_names) == ["b0", "b1"]

    def test_the_mask_is_kept_and_an_overflow_is_added(self) -> None:
        values = numpy.array([[0.5, 0.5, 1e300]])
        masked = numpy.array([[False, True, False]])
        result = NORMALIZE.run(_image(values, mask=masked), _params(0.0, 1.0, 0.0, 1e30, clip=False)).array
        numpy.testing.assert_array_equal(result.mask[0], [[False, True, True]])  # 1e300 * 1e30 overflows
        assert numpy.isnan(result.data[0, 0, 1]) and numpy.isnan(result.data[0, 0, 2])
        assert result.data[0, 0, 0] == numpy.float32(5e29)

    def test_it_does_not_look_at_the_other_pixels(self) -> None:
        """No statistic of the scene (F5): the same pixel gives the same value in any neighbourhood."""
        one = NORMALIZE.run(_image(numpy.array([[0.3]])), _params()).array.data
        many = NORMALIZE.run(_image(numpy.array([[0.3, 100.0, -50.0]])), _params()).array.data
        assert one[0, 0, 0] == many[0, 0, 0]


class TestMetadata:
    def test_all_bands_become_float32_with_nan(self) -> None:
        meta = RasterMeta("EPSG:32632", Affine(10, 0, 0, 0, -10, 0), 4, 4, (BandMeta("a", "uint16", 0), BandMeta("b", "uint8", 0)), True)
        result = NORMALIZE.transform(meta, _params())
        assert [(b.name, b.data_type) for b in result.bands] == [("a", "float32"), ("b", "float32")]
        assert all(numpy.isnan(b.nodata) for b in result.bands) and result.resampled is True

    def test_the_cost_factor_is_the_measured_one(self) -> None:
        assert NORMALIZE.cost_factor(_params()) == 0.3

    @pytest.mark.parametrize(
        ("clip", "outside"),
        [(True, "limited to the target range"), (False, "continued along the same line")],
    )
    def test_the_sentence_of_the_methods_text_says_what_happens_outside_the_range(self, clip, outside) -> None:
        sentence = NORMALIZE.method(_params(0.0, 0.5, 0.0, 255.0, clip=clip))
        assert sentence == (
            "Every band was mapped linearly from the range 0 to 0.5 onto the range 0 to 255, "
            f"values outside the source range {outside}, in 32-bit floating point."
        )

    def test_lineage(self) -> None:
        assert NORMALIZE.lineage(_params(-1, 1, 0, 255)) == "normalize: [-1, 1] to [0, 255], clipped"
        assert NORMALIZE.lineage(_params(clip=False)) == "normalize: [0, 1] to [0, 255]"


class TestApplicable:
    def test_every_registry_entry_allows_it(self) -> None:
        for config in (SENTINEL_2_L2A, COP_DEM_GLO_30):
            assert applicable(NORMALIZE, config, _params()) == []

    def test_an_entry_that_does_not_switch_it_on_refuses_it(self) -> None:
        off = replace(SENTINEL_2_L2A, capabilities=replace(SENTINEL_2_L2A.capabilities, normalization=False))
        assert applicable(NORMALIZE, off, _params()) == ["sentinel-2-c1-l2a does not allow normalization"]


# --- a run, and the tile reading the same result -------------------------------------------------


@pytest.fixture(scope="module")
def red(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return sources.build_band_cog(
        tmp_path_factory.mktemp("normalize") / "red.tif", sources.ramp(WIDTH, HEIGHT, 1200)
    )


def test_a_run_gives_the_formula_on_physical_values(red: Path, tmp_path: Path, monkeypatch) -> None:
    sources.serve({sources.url("red"): red}, monkeypatch)
    data = {
        "recipe_version": 1,
        "inputs": [
            {
                "name": "s2",
                "dataset": "synthetic",
                "groups": [["ITEM_A"]],
                "assets": ["red"],
                "resolved": [resolved("ITEM_A", "red", href=sources.url("red"))],
            }
        ],
        "aoi": sources.whole(WIDTH, HEIGHT),
        "steps": [{"op": "normalize", "op_version": 1, "params": {**GOOD, "in_max": 0.5}}],
        "output": {"kind": "raster", "format": "cog", "dtype": "float32"},
    }
    result = run(recipe_of_data(data, REGISTRY), workdir=tmp_path, progress=lambda done, total: None, operators=REGISTRY)
    with Reader(str(red)) as reader:
        physical = reader.read(unscale=True).array[0]
    expected = numpy.clip((physical.astype("float64") - 0.0) / 0.5 * 255.0, 0.0, 255.0).astype("float32")
    with rasterio.open(result.path) as dataset:
        got = dataset.read(1, masked=True)
    numpy.testing.assert_array_equal(numpy.ma.getmaskarray(got), numpy.ma.getmaskarray(physical))
    numpy.testing.assert_array_equal(got.compressed(), numpy.ma.getdata(expected)[~numpy.ma.getmaskarray(physical)])
    assert result.properties["processing:lineage"] == "normalize: [0, 0.5] to [0, 255], clipped of red"
    assert result.meta.resampled is False


# --- bit-stability across CPU levels (adr/0016 §12a) -----------------------------------------------

_PROBE = textwrap.dedent(
    """
    import hashlib, json, sys
    import numpy
    from rio_tiler.models import ImageData
    from earthx.processing.operators import MASK, NORMALIZE, MaskParams, NormalizeParams

    rng = numpy.random.default_rng(7)
    a = rng.uniform(-0.3, 1.6, (512, 512))
    out = {}
    for dtype in ("float32", "float64"):
        image = ImageData(
            numpy.ma.stack([numpy.ma.masked_array(a.astype(dtype)), numpy.ma.masked_array((a * 7).astype(dtype))]),
            bounds=(0, 0, 1, 1), crs="EPSG:32632", band_names=["a", "b"],
        )
        for name, params in json.loads(sys.argv[1]).items():
            result = NORMALIZE.run(image, NormalizeParams(**params)).array
            out[f"{dtype}: {name}"] = hashlib.sha256(numpy.ma.getdata(result).tobytes() + result.mask.tobytes()).hexdigest()
    classes = rng.integers(0, 12, (512, 512)).astype("uint8")
    layer = ImageData(
        numpy.ma.stack([numpy.ma.masked_array(a.astype("float32")), numpy.ma.masked_array(classes)]),
        bounds=(0, 0, 1, 1), crs="EPSG:32632", band_names=["a", "scl"],
    )
    masked = MASK.run(layer, MaskParams(source="scl", classes=[3, 8, 9, 10])).array
    out["mask"] = hashlib.sha256(numpy.ma.getdata(masked).tobytes() + masked.mask.tobytes()).hexdigest()
    print(json.dumps(out))
    """
)

_RANGES = {
    "unit to byte": {**GOOD},
    "unclipped": {**GOOD, "clip": False},
    "reversed": {**GOOD, "out_min": 1.0, "out_max": 0.0},
    "odd range": {"in_min": -0.3, "in_max": 1.7, "out_min": -1.0, "out_max": 1.0, "clip": False},
}


def _probe(env_extra: dict[str, str]) -> dict[str, str]:
    backend = str(Path(__file__).resolve().parents[3])
    done = subprocess.run(
        [sys.executable, "-c", _PROBE, json.dumps(_RANGES)],
        capture_output=True,
        text=True,
        env={**os.environ, **env_extra, "PYTHONPATH": backend},
        timeout=300,
        check=False,
    )
    assert done.returncode == 0, done.stderr[-2000:]
    return json.loads(done.stdout.strip().splitlines()[-1])


class TestBitStabilityAcrossCpuLevels:
    def test_normalize_and_mask_give_the_same_bytes_under_settings_a_and_d(self) -> None:
        if not _glibc_masks_features():
            pytest.skip("GLIBC_TUNABLES does not change the CPU features this loader reports: setting D is not one")
        setting_a, setting_d = _probe({}), _probe(_SETTING_D)
        assert len(setting_a) == 2 * len(_RANGES) + 1
        assert sorted(key for key in setting_a if setting_a[key] != setting_d[key]) == []
        assert hashlib.sha256(b"").hexdigest() not in setting_a.values()
