"""``sar_db`` (DS-05a, adr/0030 F2): the table of exact values, the kernel, the checks against the registry and a job.

The expected values are an independent computation: Python's ``decimal`` for the table, and ``math.log10`` in double
precision, compared to the last float32 digit, for the kernel.
"""

from __future__ import annotations

import json
import math
from dataclasses import replace
from pathlib import Path

import numpy
import pytest
import rasterio
from affine import Affine
from pydantic import ValidationError
from rasterio.crs import CRS
from rio_tiler.models import ImageData

from earthx.api.processing_docs import order_schema
from earthx.catalog.datasets import registry
from earthx.catalog.registry import ConfigError
from earthx.processing import core as core_module
from earthx.processing import run
from earthx.processing.errors import RecipeInvalid
from earthx.processing.operators import REGISTRY, SAR_DB, BandMeta, RasterMeta, SarDbParams, Tier, applicable
from earthx.processing.operators.base import Look
from earthx.processing.operators.sar_db import db_table, exact_db_table
from tests.earthx.processing import sources
from tests.earthx.processing.recipes import recipe_of_data

S1 = registry().get("sentinel-1-grd")
VV = {"bands": ["vv"], "quantity": "amplitude", "name": "vv_db"}
WIDTH, HEIGHT = 300, 260


def _params(**changes: object) -> SarDbParams:
    return SarDbParams.model_validate({**VV, **changes}, strict=True)


def _image(values: numpy.ndarray, mask: numpy.ndarray | None = None, name: str = "vv") -> ImageData:
    data = numpy.ma.MaskedArray(values[None], mask=numpy.zeros((1, *values.shape), bool) if mask is None else mask[None])
    return ImageData(data, bounds=(0, 0, values.shape[1], values.shape[0]), crs=CRS.from_epsg(32632), band_names=[name])


def _independent(numbers: numpy.ndarray, factor: int) -> numpy.ndarray:
    return numpy.array([factor * math.log10(n) for n in numbers.ravel()], dtype="float64").reshape(numbers.shape)


class TestTable:
    def test_every_entry_is_the_one_decimal_gives(self) -> None:
        fast, exact = db_table(), exact_db_table()
        assert fast.dtype == exact.dtype == numpy.float32 and fast.shape == (65536,)
        assert numpy.isnan(fast[0]) and numpy.isnan(exact[0])
        assert fast[1:].tobytes() == exact[1:].tobytes()

    def test_entries_whose_rounding_numpy_could_get_wrong_are_taken_from_decimal(self, monkeypatch) -> None:
        # numpy off by far more than any libm is: every entry is then checked, and decimal still gives the table.
        real = numpy.log10
        monkeypatch.setattr(numpy, "log10", lambda values: real(values) * (1 + 1e-13))
        db_table.cache_clear()
        try:
            assert db_table()[1:].tobytes() == exact_db_table()[1:].tobytes()
        finally:
            db_table.cache_clear()

    def test_the_table_cannot_be_changed(self) -> None:
        with pytest.raises(ValueError):
            db_table()[5] = 0


class TestKernel:
    def test_an_amplitude_is_twenty_times_its_logarithm(self) -> None:
        numbers = numpy.array([[1, 2, 10, 87], [250, 1000, 4095, 65535]], dtype="uint16")
        added = SAR_DB.run(_image(numbers), _params()).array[1]
        assert added.dtype == numpy.float32
        numpy.testing.assert_allclose(added, _independent(numbers, 20), rtol=6e-8, atol=0)
        assert added[0, 0] == 0 and added[0, 2] == 20

    def test_an_intensity_is_ten_times_its_logarithm_and_half_the_amplitude_to_the_bit(self) -> None:
        numbers = numpy.arange(1, 4001, dtype="uint16").reshape(40, 100)
        amplitude = SAR_DB.run(_image(numbers), _params()).array[1]
        intensity = SAR_DB.run(_image(numbers), _params(quantity="intensity")).array[1]
        numpy.testing.assert_allclose(intensity, _independent(numbers, 10), rtol=6e-8, atol=0)
        assert (intensity * numpy.float32(2)).astype("float32").tobytes() == amplitude.tobytes()

    def test_zero_and_masked_pixels_are_empty_and_the_stock_keeps_its_values(self) -> None:
        numbers = numpy.array([[0, 5], [7, 9]], dtype="uint16")
        hidden = numpy.array([[False, False], [True, False]])
        result = SAR_DB.run(_image(numbers, hidden), _params())
        assert list(result.band_names) == ["vv", "vv_db"]
        assert numpy.ma.getmaskarray(result.array[1]).tolist() == [[True, False], [True, False]]
        assert numpy.ma.getdata(result.array[0]).tolist() == [[0, 5], [7, 9]]

    def test_whole_numbers_in_floating_point_are_read_as_well(self) -> None:
        # A stock that holds a band of floating point holds every band so (a second sar_db after a first).
        numbers = numpy.array([[1.0, 300.0], [65535.0, numpy.nan]], dtype="float32")
        hidden = numpy.array([[False, False], [False, True]])
        added = SAR_DB.run(_image(numbers, hidden), _params()).array[1]
        integers = SAR_DB.run(_image(numpy.array([[1, 300], [65535, 1]], dtype="uint16")), _params()).array[1]
        assert added[:1].tobytes() == integers[:1].tobytes() and added[1, 0] == integers[1, 0]

    @pytest.mark.parametrize("value", [0.5, -1.0, 65536.0, numpy.inf], ids=["fraction", "negative", "too large", "inf"])
    def test_any_other_number_refuses_the_step(self, value: float) -> None:
        with pytest.raises(RecipeInvalid, match="whole numbers from 0 to 65535"):
            SAR_DB.run(_image(numpy.array([[3.0, value]], dtype="float32")), _params())

    def test_a_masked_fraction_is_no_reason_to_refuse(self) -> None:
        numbers = numpy.array([[3.0, 0.5]], dtype="float32")
        result = SAR_DB.run(_image(numbers, numpy.array([[False, True]])), _params())
        assert numpy.ma.getmaskarray(result.array[1]).tolist() == [[False, True]]

    def test_a_band_it_is_not_given_is_refused(self) -> None:
        with pytest.raises(RecipeInvalid, match="reads vv, which the input does not have: vh"):
            SAR_DB.run(_image(numpy.ones((2, 2), "uint16"), name="vh"), _params())


class TestParameters:
    @pytest.mark.parametrize(
        ("changes", "field"),
        [
            ({"bands": []}, "bands"),
            ({"bands": ["vv", "vh"]}, "bands"),
            ({"quantity": "sigma0"}, "quantity"),
            ({"name": "1db"}, "name"),
            ({"name": "lambda"}, "name"),
            ({"factor": 20}, "factor"),
        ],
    )
    def test_a_form_that_does_not_fit_is_refused(self, changes: dict, field: str) -> None:
        with pytest.raises(ValidationError, match=field):
            _params(**changes)

    def test_the_quantity_is_never_left_out(self) -> None:
        with pytest.raises(ValidationError, match="quantity"):
            SarDbParams.model_validate({"bands": ["vv"], "name": "vv_db"}, strict=True)


def _meta(*bands: BandMeta) -> RasterMeta:
    return RasterMeta("EPSG:32632", Affine.identity(), 4, 4, bands)


class TestTransform:
    def test_the_new_band_is_float32_in_db_and_keeps_the_resampled_flag(self) -> None:
        meta = SAR_DB.transform(_meta(BandMeta("vv", "uint16", 0, "DN", resampled=True)), _params())
        assert [band.name for band in meta.bands] == ["vv", "vv_db"]
        added = meta.bands[1]
        assert (added.data_type, added.unit, added.resampled) == ("float32", "dB", True)
        assert math.isnan(added.nodata)  # type: ignore[arg-type]

    def test_a_missing_band_and_a_name_taken_are_refused_before_any_read(self) -> None:
        with pytest.raises(RecipeInvalid, match="which the input does not have"):
            SAR_DB.transform(_meta(BandMeta("vh", "uint16", 0, "DN")), _params())
        with pytest.raises(RecipeInvalid, match="VV_DB is used twice"):
            SAR_DB.transform(_meta(BandMeta("vv", "uint16", 0, "DN"), BandMeta("vv_db", "float32", None)), _params(name="VV_DB"))


class TestRegistry:
    def test_sentinel_1_offers_it_for_its_radar_bands_and_no_other_dataset_does(self) -> None:
        # HH and HV too (Otto, 27.11.2026): a scene of them has no preset, but the step runs on them.
        for band in ("vv", "vh", "hh", "hv"):
            assert applicable(SAR_DB, S1, _params(bands=[band], name=f"{band}_db")) == []
        others = [config for config in registry() if config.dataset_id != S1.dataset_id]
        assert others and all("does not allow sar_backscatter" in " ".join(applicable(SAR_DB, c)) for c in others)

    def test_a_quantity_other_than_the_registrys_is_refused(self) -> None:
        assert applicable(SAR_DB, S1, _params(quantity="intensity")) == ["vv of sentinel-1-grd is an amplitude, not an intensity"]

    def test_a_band_without_a_quantity_is_refused(self) -> None:
        assert applicable(SAR_DB, S1, _params(bands=["thumbnail"])) == [
            "thumbnail is no radar band of sentinel-1-grd with a stated quantity"
        ]

    def test_the_flag_without_a_quantity_and_a_quantity_without_the_flag_are_refused(self) -> None:
        with pytest.raises(ConfigError, match="sar_backscatter and a non-empty sar_quantity go together"):
            replace(S1, sar_quantity={})
        off = replace(S1.capabilities, sar_backscatter=False)
        with pytest.raises(ConfigError, match="go together"):
            replace(S1, capabilities=off)

    @pytest.mark.parametrize(
        ("quantity", "reason"),
        [
            ({"vv": "amplitude", "vh": "amplitude", "hh": "amplitude"}, "no quantity for hv"),
            ({**S1.sar_quantity, "thumbnail": "amplitude"}, "names 'thumbnail', which is no band"),
            ({**S1.sar_quantity, "vv": "sigma0"}, "the quantity of 'vv' is one of amplitude, intensity"),
        ],
    )
    def test_the_quantities_name_every_radar_band_and_nothing_else(self, quantity: dict, reason: str) -> None:
        with pytest.raises(ConfigError, match=reason):
            replace(S1, sar_quantity=quantity)

    def test_the_description_of_sentinel_1_fixes_the_quantity_and_others_lack_the_step(self) -> None:
        schema = order_schema(REGISTRY, S1)
        quantity = schema["$defs"]["step_sar_db_v1"]["properties"]["params"]["properties"]["quantity"]
        assert quantity["const"] == "amplitude" and "enum" not in quantity
        assert "x-earthx-looks" in schema["$defs"]["step_sar_db_v1"]
        sentinel_2 = json.dumps(order_schema(REGISTRY, registry().get("sentinel-2-c1-l2a")))
        assert "sar_db" not in sentinel_2

    def test_without_a_dataset_both_quantities_stay_offered(self) -> None:
        text = json.dumps(order_schema(REGISTRY))
        assert '"enum": ["amplitude", "intensity"]' in text

    def test_it_is_a_pixel_step_of_both_tiers_drawn_grey_on_the_usual_scale(self) -> None:
        assert REGISTRY[("sar_db", 1)] is SAR_DB
        assert SAR_DB.kind == "pixel" and SAR_DB.tiers == frozenset({Tier.T1, Tier.T2})
        assert SAR_DB.looks is not None
        assert {SAR_DB.looks.of(_params(quantity=q)) for q in ("amplitude", "intensity")} == {Look("greys_r")}

    def test_its_description_says_the_values_are_uncalibrated_digital_numbers(self) -> None:
        assert "uncalibrated digital numbers (DN)" in SAR_DB.description and "not calibrated backscatter (σ⁰)" in SAR_DB.description

    def test_the_result_names_what_was_computed(self) -> None:
        assert SAR_DB.lineage(_params()) == "sar_db: vv_db = 20·log10(vv) (amplitude)"
        assert "10·log10(vv), the intensity in vv in decibels" in SAR_DB.method(_params(quantity="intensity"))
        assert SAR_DB.properties(_params()) == {"earthx:sar_db": VV}


# --- a job through the core ---------------------------------------------------------------------------------------


def _numbers() -> numpy.ndarray:
    rows, cols = numpy.indices((HEIGHT, WIDTH))
    numbers = (1 + (rows * 7919 + cols * 104729) % 65535).astype("uint16")
    numbers[100:104, 150:160] = 0  # no data
    return numbers


def _recipe(steps: list, bands: list[str], nodata: int | None = 0) -> dict:
    entry = {
        "asset": {
            "dataset_id": "synthetic",
            "item_id": "ITEM_A",
            "asset": "vv",
            "reader": "cog",
            "href": sources.url("vv"),
            "variable": None,
            "crs": sources.CRS,
        },
        "version": {"kind": "file:checksum", "value": "1220ITEM_Avv"},
        "bands": [{"data_type": "uint16", "nodata": nodata, "scale": None, "offset": None, "unit": "DN"}],
        "scaling": "none",
        "gsd": 10.0,
    }
    return {
        "recipe_version": 2,
        "inputs": [{"name": "vv", "dataset": "synthetic", "groups": [["ITEM_A"]], "assets": ["vv"], "resolved": [entry]}],
        "aoi": sources.whole(WIDTH, HEIGHT),
        "steps": steps,
        "output": {"kind": "raster", "format": "cog", "dtype": "float32", "bands": bands},
    }


@pytest.fixture(scope="module")
def scene(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("sar") / "vv.tif"
    return sources.build_band_cog(path, _numbers(), scale=None, offset=None, nodata=0)


@pytest.fixture(scope="module")
def undeclared(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The same scene, but its file does not say that 0 is no data."""
    path = tmp_path_factory.mktemp("sar-undeclared") / "vv.tif"
    return sources.build_band_cog(path, _numbers(), scale=None, offset=None, nodata=None)


@pytest.mark.usefixtures("scene")
class TestJob:
    @pytest.fixture(autouse=True)
    def _served(self, scene: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        sources.serve({sources.url("vv"): scene}, monkeypatch)

    def _run(self, data: dict, workdir: Path):
        workdir.mkdir(parents=True, exist_ok=True)
        return run(recipe_of_data(data, REGISTRY), workdir=workdir, progress=lambda done, total: None, operators=REGISTRY)

    def test_the_job_is_the_kernel_on_the_whole_scene_in_any_block_size(self, tmp_path: Path, monkeypatch) -> None:
        step = {"op": "sar_db", "op_version": 1, "params": VV}
        expected = SAR_DB.run(_image(numpy.ma.masked_equal(_numbers(), 0).data, _numbers() == 0), _params()).array[1]
        outputs = []
        for size in (64, 256):
            monkeypatch.setattr(core_module, "BLOCK_SIZE", size)
            result = self._run(_recipe([step], ["vv_db"]), tmp_path / str(size))
            with rasterio.open(result.path) as dataset:
                outputs.append(dataset.read(1, masked=True))
            assert result.meta.bands[0].unit == "dB"
        numpy.testing.assert_array_equal(numpy.ma.getmaskarray(outputs[0]), numpy.ma.getmaskarray(expected))
        assert outputs[0].compressed().tobytes() == expected.compressed().tobytes() == outputs[1].compressed().tobytes()

    def test_after_a_formula_with_fractions_the_job_fails_with_the_reason(self, tmp_path: Path) -> None:
        steps = [
            {"op": "band_math", "op_version": 2, "params": {"expression": "vv / 3", "name": "third"}},
            {"op": "sar_db", "op_version": 1, "params": {**VV, "bands": ["third"]}},
        ]
        with pytest.raises(RecipeInvalid, match="third holds others"):
            self._run(_recipe(steps, ["vv_db"]), tmp_path)


class TestZeroIsNoData:
    """DN 0 is no data at Sentinel-1 GRD (Otto, 27.11.2026): masked in the result and left out of its statistics, never −∞,
    NaN or a number, whether the file declares it or not."""

    def _run(self, data: dict, workdir: Path):
        workdir.mkdir(parents=True, exist_ok=True)
        return run(recipe_of_data(data, REGISTRY), workdir=workdir, progress=lambda done, total: None, operators=REGISTRY)

    @pytest.mark.parametrize("declared", [True, False], ids=["declared", "undeclared"])
    def test_the_job_masks_every_zero_and_its_statistics_count_only_the_others(
        self, scene: Path, undeclared: Path, declared: bool, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sources.serve({sources.url("vv"): scene if declared else undeclared}, monkeypatch)
        step = {"op": "sar_db", "op_version": 1, "params": VV}
        data = _recipe([step], ["vv_db"], nodata=0 if declared else None)
        result = self._run(data, tmp_path)
        with rasterio.open(result.path) as dataset:
            band = dataset.read(1, masked=True)
        source = _numbers()
        assert band.shape == source.shape
        assert numpy.ma.getmaskarray(band)[source == 0].all()
        assert numpy.isfinite(band.compressed()).all()
        (stats,) = [b["statistics"] for b in result.properties["bands"]]
        assert 0 <= stats["minimum"] < stats["maximum"] < 96.33
        assert stats["count"] == int((~numpy.ma.getmaskarray(band)).sum())
        area = core_module.area_statistics(recipe_of_data(data, REGISTRY), operators=REGISTRY)
        assert area.bands[0]["statistics"]["minimum"] == stats["minimum"]
        assert area.bands[0]["statistics"]["count"] == stats["count"]
