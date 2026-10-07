"""``processing.run`` end to end on synthetic COGs and a Zarr store (adr/0014 §5.4, §5.6, §7; plan M4-07a §8)."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy
import pytest
import rasterio
from rasterio.warp import transform_geom
from rio_cogeo.cogeo import cog_validate
from rio_tiler.io import Reader

from earthx.processing import RunCancelled, run
from earthx.processing import core as core_module
from earthx.processing.errors import AoiOutsideInputs, GridMismatch, UnsupportedRecipe
from earthx.processing.recipe import recipe_from_data, recipe_hash
from earthx.readers import AssetRejected
from tests.earthx.processing import sources
from tests.earthx.processing.recipes import resolved
from tests.earthx.processing.testops import OPERATORS

WIDTH, HEIGHT = 1300, 1100  # more than one 1024 block in each direction


def _recipe(steps: list, *, aoi: dict | None = None, assets=("red", "nir"), dtype="float32", **entry_options) -> dict:
    entries = [resolved("ITEM_A", asset, href=sources.url(asset), **entry_options) for asset in assets]
    return {
        "recipe_version": 1,
        "inputs": [
            {"name": "s2", "dataset": "synthetic", "groups": [["ITEM_A"]], "assets": list(assets), "resolved": entries}
        ],
        "aoi": aoi or sources.whole(WIDTH, HEIGHT),
        "steps": steps,
        "output": {"kind": "raster", "format": "cog", "dtype": dtype},
    }


SCALE_2 = {"op": "scale", "op_version": 1, "params": {"factor": 2.0}}
COARSEN_2 = {"op": "coarsen", "op_version": 1, "params": {"factor": 2}}


@pytest.fixture(scope="module")
def bands(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    root = tmp_path_factory.mktemp("bands")
    return {
        "red": sources.build_band_cog(root / "red.tif", sources.ramp(WIDTH, HEIGHT, 1200)),
        "nir": sources.build_band_cog(root / "nir.tif", sources.ramp(WIDTH, HEIGHT, 3400)),
    }


@pytest.fixture
def served(bands: dict[str, Path], monkeypatch: pytest.MonkeyPatch) -> list[str]:
    return sources.serve({sources.url(name): path for name, path in bands.items()}, monkeypatch)


@pytest.fixture(scope="module")
def physical(bands: dict[str, Path]) -> dict[str, numpy.ma.MaskedArray]:
    """What rio-tiler's own ``unscale`` makes of each band — the tile path's arithmetic (§6.3)."""
    result = {}
    for name, path in bands.items():
        with Reader(str(path)) as reader:
            result[name] = reader.read(unscale=True).array[0]
    return result


def _run(data: dict, workdir: Path, progress=lambda done, total: None):
    return run(recipe_from_data(data, OPERATORS), workdir=workdir, progress=progress, operators=OPERATORS)


def _read(path: Path) -> numpy.ma.MaskedArray:
    with rasterio.open(path) as dataset:
        return dataset.read(masked=True)


@pytest.mark.usefixtures("served")
class TestAPixelRun:
    def test_the_result_is_the_formula_on_physical_values(self, tmp_path: Path, physical: dict) -> None:
        result = _run(_recipe([SCALE_2]), tmp_path)
        data = _read(result.path)
        for index, name in enumerate(("red", "nir")):
            expected = physical[name] * numpy.float32(2.0)
            numpy.testing.assert_array_equal(data[index].mask, expected.mask)
            numpy.testing.assert_array_equal(data[index].compressed(), expected.astype("float32").compressed())

    def test_the_result_is_a_valid_cog_with_a_mask_beside_it(self, tmp_path: Path) -> None:
        result = _run(_recipe([SCALE_2]), tmp_path)
        assert cog_validate(str(result.path), quiet=True)[0]
        assert sorted(path.name for path in tmp_path.iterdir()) == ["mask.tif", "result.tif"]
        with rasterio.open(result.path) as data, rasterio.open(result.mask_path) as mask:
            assert (data.width, data.height, data.crs, data.transform) == (
                mask.width,
                mask.height,
                mask.crs,
                mask.transform,
            )
            assert data.dtypes == ("float32", "float32")
            assert mask.read(1).min() == 1

    def test_metadata_and_scaling_are_reported(self, tmp_path: Path) -> None:
        result = _run(_recipe([SCALE_2]), tmp_path)
        assert (result.meta.width, result.meta.height) == (WIDTH, HEIGHT)
        assert [band.name for band in result.meta.bands] == ["red", "nir"]
        assert result.properties["proj:code"] == "EPSG:32632"
        assert result.properties["gsd"] == sources.RESOLUTION
        assert result.properties["bands"] == [
            {"name": "red", "data_type": "float32", "nodata": "nan"},
            {"name": "nir", "data_type": "float32", "nodata": "nan"},
        ]
        assert result.properties["processing:lineage"] == "scaled by 2.0"
        assert result.properties["earthx:resampled"] is False
        assert result.properties["processing:software"]["earthx"] == result.engine["earthx"]
        assert [(entry.asset, entry.source, entry.scales, entry.offsets) for entry in result.scaling] == [
            ("red", "item", [sources.SCALE], [sources.OFFSET]),
            ("nir", "item", [sources.SCALE], [sources.OFFSET]),
        ]
        assert result.valid_pixels == WIDTH * HEIGHT - 64

    def test_the_block_size_does_not_change_the_result(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        (tmp_path / "a").mkdir()
        (tmp_path / "b").mkdir()
        big = _read(_run(_recipe([SCALE_2]), tmp_path / "a").path)
        monkeypatch.setattr(core_module, "BLOCK_SIZE", 256)
        small = _read(_run(_recipe([SCALE_2]), tmp_path / "b").path)
        numpy.testing.assert_array_equal(big.filled(-1), small.filled(-1))

    def test_every_address_passed_check_url_once(self, tmp_path: Path, served: list[str]) -> None:
        _run(_recipe([SCALE_2]), tmp_path)
        assert served == [sources.url("red"), sources.url("nir")]


@pytest.mark.usefixtures("served")
class TestProgressAndCancel:
    def test_progress_counts_every_block_up_to_the_total(self, tmp_path: Path) -> None:
        calls: list[tuple[int, int]] = []
        result = _run(_recipe([SCALE_2]), tmp_path, progress=lambda done, total: calls.append((done, total)))
        assert calls == [(n, 4) for n in range(1, 5)]
        assert result.blocks == 4

    def test_a_grid_pass_adds_its_blocks(self, tmp_path: Path) -> None:
        calls: list[tuple[int, int]] = []
        _run(_recipe([SCALE_2, COARSEN_2]), tmp_path, progress=lambda done, total: calls.append((done, total)))
        assert calls[-1] == (5, 5)

    @pytest.mark.parametrize("stop_at", [1, 3, 5])
    def test_cancelling_leaves_nothing_behind(self, tmp_path: Path, stop_at: int) -> None:
        def progress(done: int, total: int) -> None:
            if done == stop_at:
                raise RunCancelled("dismissed")

        with pytest.raises(RunCancelled):
            _run(_recipe([SCALE_2, COARSEN_2]), tmp_path, progress=progress)
        assert list(tmp_path.iterdir()) == []

    def test_a_failure_leaves_nothing_behind_and_files_not_ours_stay(self, tmp_path: Path) -> None:
        (tmp_path / "theirs.txt").write_text("kept")

        def progress(done: int, total: int) -> None:
            raise RuntimeError("callback broke")

        with pytest.raises(RuntimeError):
            _run(_recipe([SCALE_2]), tmp_path, progress=progress)
        assert [path.name for path in tmp_path.iterdir()] == ["theirs.txt"]


@pytest.mark.usefixtures("served")
class TestGridSteps:
    def test_a_grid_step_after_a_pixel_step(self, tmp_path: Path, physical: dict) -> None:
        result = _run(_recipe([SCALE_2, COARSEN_2]), tmp_path)
        data = _read(result.path)
        assert data.shape == (2, HEIGHT // 2, WIDTH // 2)
        expected = (physical["red"] * numpy.float32(2.0)).astype("float32")[1::2, 1::2]
        numpy.testing.assert_array_equal(data[0].filled(numpy.nan)[8:, 8:], expected.filled(numpy.nan)[8:, 8:])
        assert result.meta.resampled is True
        assert result.properties["processing:lineage"] == "scaled by 2.0; coarsened by 2 (nearest)"

    def test_a_leading_grid_step_reads_a_native_crop(self, tmp_path: Path, physical: dict) -> None:
        result = _run(_recipe([COARSEN_2]), tmp_path)
        data = _read(result.path)
        numpy.testing.assert_array_equal(
            data[1].filled(numpy.nan)[8:, 8:], physical["nir"][1::2, 1::2].filled(numpy.nan)[8:, 8:]
        )
        assert sorted(path.name for path in tmp_path.iterdir()) == ["mask.tif", "result.tif"]


@pytest.mark.usefixtures("served")
class TestExtentAndMask:
    def test_the_extent_is_the_aoi_bbox_and_values_outside_the_polygon_stay(
        self, tmp_path: Path, physical: dict
    ) -> None:
        left, top = sources.ORIGIN_X + 1000.0, sources.ORIGIN_Y - 1000.0
        ring = [[left + 5, top - 4995], [left + 4995, top - 4995], [left + 2500, top - 5], [left + 5, top - 4995]]
        aoi = transform_geom(sources.CRS, "EPSG:4326", {"type": "Polygon", "coordinates": [ring]})
        result = _run(_recipe([SCALE_2], aoi=aoi), tmp_path)
        data = _read(result.path)
        assert data.shape == (2, 500, 500)
        mask = _read(result.mask_path)[0]
        assert mask[499, 250] == 1 and mask[0, 0] == 0 and mask[499, 0] == 1
        assert not data.mask[:, 0, 0].any()  # outside the triangle, but inside the box: kept
        expected = (physical["red"] * numpy.float32(2.0))[100:600, 100:600]
        numpy.testing.assert_array_equal(data[0], expected.astype("float32"))

    def test_an_aoi_beside_the_raster_is_named(self, tmp_path: Path) -> None:
        aoi = sources.aoi_around(
            sources.ORIGIN_X - 5000, sources.ORIGIN_Y - 2000, sources.ORIGIN_X - 1000, sources.ORIGIN_Y
        )
        with pytest.raises(AoiOutsideInputs):
            _run(_recipe([SCALE_2], aoi=aoi), tmp_path)
        assert list(tmp_path.iterdir()) == []


@pytest.mark.usefixtures("served")
class TestRefusals:
    def test_more_than_one_item_is_not_run_yet(self, tmp_path: Path) -> None:
        data = _recipe([SCALE_2], assets=("red",))
        data["inputs"][0]["groups"] = [["ITEM_A", "ITEM_B"]]
        data["inputs"][0]["resolved"].append(resolved("ITEM_B", "red", href=sources.url("red")))
        with pytest.raises(UnsupportedRecipe, match="one item"):
            _run(data, tmp_path)
        data["inputs"][0]["groups"] = [["ITEM_A"], ["ITEM_B"]]
        with pytest.raises(UnsupportedRecipe, match="one item"):
            _run(data, tmp_path)

    def test_a_crop_output_is_described_not_run(self, tmp_path: Path) -> None:
        data = _recipe([])
        data["output"] = {
            "kind": "crop",
            "format": "cog",
            "resolution_factor": 1,
            "extent": "bbox(aoi ∩ footprints)",
            "mask": "file",
        }
        with pytest.raises(UnsupportedRecipe):
            _run(data, tmp_path)

    def test_assets_on_different_grids(
        self, tmp_path: Path, bands: dict[str, Path], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        coarse = sources.build_band_cog(
            tmp_path / "b11.tif", sources.ramp(WIDTH // 2 - 7, HEIGHT // 2, 800), resolution=20.0
        )
        sources.serve({sources.url("red"): bands["red"], sources.url("b11"): coarse}, monkeypatch)
        work = tmp_path / "work"
        work.mkdir()
        with pytest.raises(GridMismatch):
            _run(_recipe([SCALE_2], assets=("red", "b11")), work)
        assert list(work.iterdir()) == []

    @pytest.mark.parametrize(
        "href",
        ["https://127.0.0.1/a.tif", "http://store.example.invalid/a.tif", "https://other.example.invalid:8443/a.tif"],
    )
    def test_an_address_the_gateway_refuses(self, tmp_path: Path, href: str) -> None:
        data = _recipe([SCALE_2], assets=("red",))
        data["inputs"][0]["resolved"][0]["asset"]["href"] = href
        with pytest.raises(AssetRejected):
            _run(data, tmp_path)

    def test_an_integer_output_needs_a_nodata(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        bare = sources.build_band_cog(tmp_path / "bare.tif", sources.ramp(64, 64, 100) + 1, nodata=None)
        sources.serve({sources.url("bare"): bare}, monkeypatch)
        work = tmp_path / "work"
        work.mkdir()
        data = _recipe([SCALE_2], assets=("bare",), dtype="uint16", aoi=sources.whole(64, 64))
        with pytest.raises(UnsupportedRecipe, match="nodata"):
            _run(data, work)
        assert list(work.iterdir()) == []


@pytest.mark.usefixtures("served")
def test_logs_name_no_address_no_aoi_and_no_hash(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    data = _recipe([SCALE_2])
    caplog.set_level(logging.DEBUG)
    _run(data, tmp_path)
    text = "\n".join(f"{record.getMessage()} {json.dumps(record.__dict__, default=str)}" for record in caplog.records)
    assert "processing run finished" in text
    assert sources.HOST not in text
    assert recipe_hash(recipe_from_data(data, OPERATORS)) not in text
    first = data["aoi"]["coordinates"][0][0]
    assert f"{first[0]}" not in text and f"{first[1]}" not in text
