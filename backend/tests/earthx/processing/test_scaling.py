"""Scaling for band math: the four cases of F7a, the check against file and store, the arithmetic (adr/0014 §5.4).

Condition F7: a synthetic item with offset and nodata. Decision F7a: item scaling
applies to raw values; without it, a Zarr store's CF decoding applies; item and
file or store must agree; and (reading of 05.10.2026) a COG carrying a scaling
neither item nor store declares fails the run.
"""

from __future__ import annotations

from pathlib import Path

import numpy
import pytest
from rio_tiler.io import Reader
from rio_tiler.models import ImageData

from earthx.processing import run
from earthx.processing.errors import ScalingMismatch
from earthx.processing.recipe import Band, recipe_from_data
from earthx.processing.scaling import Scaling, apply_scaling, scaling_for_cog, scaling_for_zarr
from tests.earthx.processing import sources
from tests.earthx.processing.recipes import resolved
from tests.earthx.processing.testops import OPERATORS
from tests.earthx.readers import mini_zarr_cf

ITEM = [Band(data_type="uint16", nodata=0, scale=0.0001, offset=-0.1)]
PLAIN = [Band(data_type="uint16", nodata=0, scale=None, offset=None)]


class TestCog:
    def test_item_and_file_agree(self) -> None:
        scaling = scaling_for_cog("item", ITEM, (0.0001,), (-0.1,), "x")
        assert (scaling.scales, scaling.offsets, scaling.applied_by_core) == ((0.0001,), (-0.1,), True)

    def test_item_and_file_disagree(self) -> None:
        with pytest.raises(ScalingMismatch, match="band 1"):
            scaling_for_cog("item", ITEM, (0.0002,), (-0.1,), "x")
        with pytest.raises(ScalingMismatch):
            scaling_for_cog("item", ITEM, (0.0001,), (0.0,), "x")

    def test_item_scaling_applies_to_a_file_without_tags(self) -> None:
        assert scaling_for_cog("item", ITEM, (1.0,), (0.0,), "x").scales == (0.0001,)

    def test_a_band_count_that_does_not_fit(self) -> None:
        for scales, offsets in (((0.0001, 0.0001), (-0.1, -0.1)), ((1.0, 1.0), (0.0, 0.0))):
            with pytest.raises(ScalingMismatch, match="bands"):
                scaling_for_cog("item", ITEM, scales, offsets, "x")

    def test_no_scaling_anywhere_is_no_scaling(self) -> None:
        scaling = scaling_for_cog("none", PLAIN, (1.0,), (0.0,), "x")
        assert scaling.applied_by_core is False

    @pytest.mark.parametrize(("scales", "offsets"), [((0.0001,), (0.0,)), ((1.0,), (-0.1,))])
    def test_a_file_scaling_nothing_declares_fails(self, scales: tuple, offsets: tuple) -> None:
        with pytest.raises(ScalingMismatch, match="neither item nor store"):
            scaling_for_cog("none", PLAIN, scales, offsets, "x")

    def test_store_cf_does_not_exist_for_a_cog(self) -> None:
        with pytest.raises(ScalingMismatch):
            scaling_for_cog("store-cf", PLAIN, (1.0,), (0.0,), "x")


class TestZarr:
    CF = {"scale_factor": 0.0001, "add_offset": -0.1, "_FillValue": 0}

    def test_item_and_store_agree(self) -> None:
        assert scaling_for_zarr("item", ITEM, [self.CF], "x").applied_by_core is True

    def test_item_and_store_disagree(self) -> None:
        with pytest.raises(ScalingMismatch):
            scaling_for_zarr("item", [Band(data_type="uint16", nodata=0, scale=0.0002, offset=-0.1)], [self.CF], "x")

    def test_store_cf_reports_what_the_store_says_and_leaves_it_to_the_reader(self) -> None:
        scaling = scaling_for_zarr("store-cf", PLAIN, [self.CF, {}], "x")
        assert (scaling.scales, scaling.offsets, scaling.applied_by_core) == ((0.0001, 1.0), (-0.1, 0.0), False)

    def test_none_does_not_exist_for_zarr(self) -> None:
        with pytest.raises(ScalingMismatch):
            scaling_for_zarr("none", PLAIN, [{}], "x")


class TestApplyScaling:
    def test_it_computes_exactly_as_rio_tilers_unscale(self, tmp_path: Path) -> None:
        path = sources.build_band_cog(tmp_path / "b.tif", sources.ramp(300, 200, 1200))
        with Reader(str(path)) as reader:
            raw = reader.read()
            expected = reader.read(unscale=True)
        scaled = apply_scaling(raw, Scaling("item", (sources.SCALE,), (sources.OFFSET,), applied_by_core=True))
        assert scaled.array.dtype == numpy.float32
        numpy.testing.assert_array_equal(scaled.array.data, expected.array.data)
        numpy.testing.assert_array_equal(numpy.ma.getmaskarray(scaled.array), numpy.ma.getmaskarray(expected.array))

    def test_nothing_happens_when_the_reader_did_it_or_nothing_applies(self) -> None:
        image = ImageData(numpy.ma.masked_array(numpy.ones((1, 2, 2), dtype="uint16")))
        assert apply_scaling(image, Scaling("store-cf", (0.5,), (1.0,), applied_by_core=False)) is image

    def test_a_band_count_that_does_not_fit_the_data(self) -> None:
        image = ImageData(numpy.ma.masked_array(numpy.ones((2, 2, 2), dtype="uint16")))
        with pytest.raises(ScalingMismatch):
            apply_scaling(image, Scaling("item", (0.5,), (1.0,), applied_by_core=True))


ZARR_KEY = "r10m:b04,b08"


@pytest.fixture(scope="module")
def cf_store(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return mini_zarr_cf.build_mini_zarr_cf(tmp_path_factory.mktemp("cf") / "mini.zarr")


def _zarr_recipe(scale: float | None, offset: float | None) -> dict:
    entry = resolved(
        "ITEM_Z", ZARR_KEY, reader="zarr", scale=scale, offset=offset, href=mini_zarr_cf.GROUP_URL, variable="b04,b08"
    )
    entry["bands"] = entry["bands"] * 2
    return {
        "recipe_version": 1,
        "inputs": [
            {"name": "z", "dataset": "synthetic", "groups": [["ITEM_Z"]], "assets": [ZARR_KEY], "resolved": [entry]}
        ],
        "aoi": sources.whole(mini_zarr_cf.SIZE, mini_zarr_cf.SIZE),
        "steps": [],
        "output": {"kind": "raster", "format": "cog", "dtype": "float32"},
    }


def _run(data: dict, workdir: Path):
    return run(
        recipe_from_data(data, OPERATORS), workdir=workdir, progress=lambda done, total: None, operators=OPERATORS
    )


def _expected(name: str, dtype: str) -> numpy.ma.MaskedArray:
    raw = mini_zarr_cf.raw_band(name)
    data = raw.astype(dtype)
    numpy.multiply(data, numpy.array([mini_zarr_cf.SCALE]), out=data, casting="unsafe")
    numpy.add(data, numpy.array([mini_zarr_cf.OFFSET]), out=data, casting="unsafe")
    return numpy.ma.masked_array(data, mask=raw == mini_zarr_cf.FILL)


class TestTheFourCasesOfF7a:
    def test_1_item_scaling_on_raw_zarr_values(
        self, tmp_path: Path, cf_store: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sources.serve({}, monkeypatch, zarr_root=cf_store)
        result = _run(_zarr_recipe(mini_zarr_cf.SCALE, mini_zarr_cf.OFFSET), tmp_path)
        with Reader(str(result.path)) as reader:
            data = reader.read().array
        for index, name in enumerate(("b04", "b08")):
            expected = _expected(name, "float32")
            numpy.testing.assert_array_equal(data[index].mask, expected.mask)
            numpy.testing.assert_array_equal(data[index].compressed(), expected.compressed())
        assert [entry.source for entry in result.scaling] == ["item"]

    def test_2_store_cf_without_item_scaling(
        self, tmp_path: Path, cf_store: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sources.serve({}, monkeypatch, zarr_root=cf_store)
        result = _run(_zarr_recipe(None, None), tmp_path)
        with Reader(str(result.path)) as reader:
            data = reader.read().array
        expected = _expected("b04", "float64").astype("float32")
        numpy.testing.assert_array_equal(data[0].mask, expected.mask)
        numpy.testing.assert_allclose(data[0].compressed(), expected.compressed(), rtol=1e-6)
        (entry,) = result.scaling
        assert (entry.source, entry.scales, entry.offsets) == (
            "store-cf",
            [mini_zarr_cf.SCALE] * 2,
            [mini_zarr_cf.OFFSET] * 2,
        )

    def test_3_item_and_store_disagree(self, tmp_path: Path, cf_store: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        sources.serve({}, monkeypatch, zarr_root=cf_store)
        with pytest.raises(ScalingMismatch):
            _run(_zarr_recipe(0.0002, mini_zarr_cf.OFFSET), tmp_path)
        assert list(tmp_path.iterdir()) == []

    def test_3_item_and_cog_disagree(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        cog = sources.build_band_cog(tmp_path / "red.tif", sources.ramp(64, 64, 1200))
        sources.serve({sources.url("red"): cog}, monkeypatch)
        data = _cog_recipe(scale=0.0002, offset=-0.1)
        work = tmp_path / "work"
        work.mkdir()
        with pytest.raises(ScalingMismatch):
            _run(data, work)

    def test_4_neither_item_nor_store_but_the_cog_carries_tags(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cog = sources.build_band_cog(tmp_path / "red.tif", sources.ramp(64, 64, 1200))
        sources.serve({sources.url("red"): cog}, monkeypatch)
        work = tmp_path / "work"
        work.mkdir()
        with pytest.raises(ScalingMismatch, match="neither item nor store"):
            _run(_cog_recipe(scale=None, offset=None), work)
        assert list(work.iterdir()) == []

    def test_4_neither_anywhere_reads_the_values_as_they_are(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cog = sources.build_band_cog(tmp_path / "dem.tif", sources.ramp(64, 64, 1200), scale=None, offset=None)
        sources.serve({sources.url("red"): cog}, monkeypatch)
        work = tmp_path / "work"
        work.mkdir()
        result = _run(_cog_recipe(scale=None, offset=None), work)
        with Reader(str(result.path)) as reader:
            data = reader.read().array[0]
        raw = sources.ramp(64, 64, 1200)
        numpy.testing.assert_array_equal(data.compressed(), raw[raw != 0].astype("float32"))


def _cog_recipe(scale: float | None, offset: float | None) -> dict:
    return {
        "recipe_version": 1,
        "inputs": [
            {
                "name": "s2",
                "dataset": "synthetic",
                "groups": [["ITEM_A"]],
                "assets": ["red"],
                "resolved": [resolved("ITEM_A", "red", href=sources.url("red"), scale=scale, offset=offset)],
            }
        ],
        "aoi": sources.whole(64, 64),
        "steps": [],
        "output": {"kind": "raster", "format": "cog", "dtype": "float32"},
    }
