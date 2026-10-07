"""``band_math`` through ``processing.run``: scaling, nested grids, refusals, the Zarr path (plan M4-09 §3.2, §3.5).

Synthetic COGs and the CF Mini-Zarr of the other core tests, served through the real `readers`; the
expected values are formulas, not a second implementation of the core.
"""

from __future__ import annotations

from pathlib import Path

import numpy
import pytest
import rasterio
from rio_tiler.io import Reader

from earthx.processing import run
from earthx.processing.errors import GridMismatch, RecipeInvalid, ScalingMismatch, UnsupportedRecipe
from earthx.processing.operators import REGISTRY
from earthx.processing.recipe import recipe_from_data
from tests.earthx.processing import sources
from tests.earthx.processing.recipes import resolved
from tests.earthx.readers import mini_zarr_cf

WIDTH, HEIGHT = 1300, 1100
NDVI = {"op": "band_math", "op_version": 1, "params": {"expression": "(nir - red) / (nir + red)"}}


def _recipe(steps: list, *, assets=("red", "nir"), dtype="float32", **entry_options) -> dict:
    entries = [resolved("ITEM_A", asset, href=sources.url(asset), **entry_options) for asset in assets]
    return {
        "recipe_version": 1,
        "inputs": [
            {"name": "s2", "dataset": "synthetic", "groups": [["ITEM_A"]], "assets": list(assets), "resolved": entries}
        ],
        "aoi": sources.whole(WIDTH, HEIGHT),
        "steps": steps,
        "output": {"kind": "raster", "format": "cog", "dtype": dtype},
    }


def _run(data: dict, workdir: Path, progress=lambda done, total: None):
    return run(recipe_from_data(data, REGISTRY), workdir=workdir, progress=progress, operators=REGISTRY)


def _read(path: Path) -> numpy.ma.MaskedArray:
    with rasterio.open(path) as dataset:
        return dataset.read(masked=True)


@pytest.fixture(scope="module")
def bands(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    root = tmp_path_factory.mktemp("bands")
    return {
        "red": sources.build_band_cog(root / "red.tif", sources.ramp(WIDTH, HEIGHT, 1200)),
        "nir": sources.build_band_cog(root / "nir.tif", sources.ramp(WIDTH, HEIGHT, 3400)),
    }


@pytest.fixture(scope="module")
def physical(bands: dict[str, Path]) -> dict[str, numpy.ma.MaskedArray]:
    """rio-tiler's ``unscale`` of each band: the arithmetic the tile has always had."""
    result = {}
    for name, path in bands.items():
        with Reader(str(path)) as reader:
            result[name] = reader.read(unscale=True).array[0]
    return result


@pytest.fixture
def served(bands: dict[str, Path], monkeypatch: pytest.MonkeyPatch) -> list[str]:
    return sources.serve({sources.url(name): path for name, path in bands.items()}, monkeypatch)


def _formula(physical: dict, expression) -> numpy.ma.MaskedArray:
    red, nir = (physical[name].astype("float64") for name in ("red", "nir"))
    mask = numpy.ma.getmaskarray(red) | numpy.ma.getmaskarray(nir)
    return numpy.ma.masked_array(expression(red, nir).astype("float32"), mask=mask)


@pytest.mark.usefixtures("served")
class TestOnCogs:
    def test_ndvi_is_the_formula_on_physical_values_not_on_raw_counts(self, tmp_path: Path, physical: dict) -> None:
        result = _run(_recipe([NDVI]), tmp_path)
        data = _read(result.path)
        expected = _formula(physical, lambda red, nir: (nir - red) / (nir + red))
        assert data.shape == (1, HEIGHT, WIDTH) and data.dtype == numpy.float32
        numpy.testing.assert_array_equal(data[0].mask, expected.mask)
        numpy.testing.assert_array_equal(data[0].compressed(), expected.compressed())
        raw = (sources.ramp(WIDTH, HEIGHT, 3400).astype("float64") - sources.ramp(WIDTH, HEIGHT, 1200)) / (
            sources.ramp(WIDTH, HEIGHT, 3400).astype("float64") + sources.ramp(WIDTH, HEIGHT, 1200)
        )
        assert not numpy.allclose(data[0].compressed(), raw[~data[0].mask], atol=1e-3)

    def test_a_second_step_may_use_the_result_of_the_first(self, tmp_path: Path, physical: dict) -> None:
        twice = {"op": "band_math", "op_version": 1, "params": {"expression": "band_math * 2 + 1"}}
        result = _run(_recipe([NDVI, twice]), tmp_path)
        expected = _formula(physical, lambda red, nir: ((nir - red) / (nir + red)).astype("float32") * 2 + 1)
        numpy.testing.assert_allclose(_read(result.path)[0].compressed(), expected.compressed(), rtol=1e-6)

    def test_the_result_says_what_was_computed(self, tmp_path: Path) -> None:
        result = _run(_recipe([NDVI]), tmp_path)
        assert [(band.name, band.data_type) for band in result.meta.bands] == [("band_math", "float32")]
        assert result.properties["processing:expression"] == {
            "format": "numexpr",
            "expression": "(nir - red) / (nir + red)",
        }
        assert result.properties["processing:lineage"] == "band math: (nir - red) / (nir + red)"
        assert result.properties["earthx:resampled"] is False
        assert result.meta.resampled is False
        assert [band["name"] for band in result.properties["bands"]] == ["band_math"]

    def test_two_expressions_list_both(self, tmp_path: Path) -> None:
        second = {"op": "band_math", "op_version": 1, "params": {"expression": "band_math + 1"}}
        result = _run(_recipe([NDVI, second]), tmp_path)
        assert [entry["expression"] for entry in result.properties["processing:expression"]] == [
            "(nir - red) / (nir + red)",
            "band_math + 1",
        ]

    def test_the_valid_pixels_are_those_where_both_bands_are(self, tmp_path: Path) -> None:
        result = _run(_recipe([NDVI]), tmp_path)
        assert result.valid_pixels == WIDTH * HEIGHT - 64  # the 8 × 8 nodata corner both bands share

    def test_the_result_is_the_same_bytes_twice(self, tmp_path: Path) -> None:
        for name in ("a", "b"):
            (tmp_path / name).mkdir()
        first = _run(_recipe([NDVI]), tmp_path / "a")
        second = _run(_recipe([NDVI]), tmp_path / "b")
        assert _read(first.path).tobytes() == _read(second.path).tobytes()

    def test_an_unknown_band_fails_before_the_first_block_and_leaves_nothing(self, tmp_path: Path) -> None:
        ticks: list[int] = []
        data = _recipe([{"op": "band_math", "op_version": 1, "params": {"expression": "swir - red"}}])
        with pytest.raises(RecipeInvalid, match="unknown band"):
            _run(data, tmp_path, progress=lambda done, total: ticks.append(done))
        assert ticks == [] and list(tmp_path.iterdir()) == []

    def test_a_refused_expression_never_reaches_the_core(self, tmp_path: Path) -> None:
        data = _recipe([{"op": "band_math", "op_version": 1, "params": {"expression": "log(red)"}}])
        with pytest.raises(RecipeInvalid):
            _run(data, tmp_path)

    def test_an_integer_output_has_no_nodata_to_put_a_nan_in(self, tmp_path: Path) -> None:
        with pytest.raises(UnsupportedRecipe, match="nodata"):
            _run(_recipe([NDVI], dtype="uint16"), tmp_path)
        assert list(tmp_path.iterdir()) == []

    def test_a_scaling_the_item_states_differently_from_the_file_stops_the_run(self, tmp_path: Path) -> None:
        with pytest.raises(ScalingMismatch):
            _run(_recipe([NDVI], scale=0.0002), tmp_path)

    def test_item_scaling_that_matches_the_file_is_applied_and_reported(self, tmp_path: Path, physical: dict) -> None:
        """F7: scale, offset and nodata come from the item; the file's tags are only compared."""
        result = _run(_recipe([NDVI], scale=sources.SCALE, offset=sources.OFFSET), tmp_path)
        expected = _formula(physical, lambda red, nir: (nir - red) / (nir + red))
        numpy.testing.assert_array_equal(_read(result.path)[0].compressed(), expected.compressed())
        assert {entry.source for entry in result.scaling} == {"item"}


class TestNestedGrids:
    """Plan M4-09, F2: a coarser asset on the same extent is read onto the finest grid with ``nearest``."""

    @pytest.fixture
    def coarse(self, bands: dict[str, Path], tmp_path_factory: pytest.TempPathFactory, monkeypatch) -> Path:
        path = sources.build_band_cog(
            tmp_path_factory.mktemp("coarse") / "b11.tif", sources.ramp(WIDTH // 2, HEIGHT // 2, 800), resolution=20.0
        )
        sources.serve({sources.url(n): p for n, p in bands.items()} | {sources.url("b11"): path}, monkeypatch)
        return path

    def test_the_result_is_on_the_finest_grid_with_repeated_pixels_and_is_marked(
        self, tmp_path: Path, coarse: Path, physical: dict
    ) -> None:
        step = {"op": "band_math", "op_version": 1, "params": {"expression": "b11 - red"}}
        result = _run(_recipe([step], assets=("red", "b11")), tmp_path)
        with Reader(str(coarse)) as reader:
            small = reader.read(unscale=True).array[0]
        repeated = numpy.repeat(numpy.repeat(small, 2, axis=0), 2, axis=1)
        red = physical["red"]
        expected_mask = numpy.ma.getmaskarray(repeated) | numpy.ma.getmaskarray(red)
        expected = (repeated.astype("float64").data - red.astype("float64").data).astype("float32")
        data = _read(result.path)[0]
        assert (data.shape, result.meta.resampled) == ((HEIGHT, WIDTH), True)
        assert result.properties["earthx:resampled"] is True
        numpy.testing.assert_array_equal(data.mask, expected_mask)
        numpy.testing.assert_array_equal(data.compressed(), expected[~expected_mask])
        assert sources.RESOLUTION == result.properties["gsd"]

    @pytest.mark.parametrize("other", [("b11", 15.0, 866, 733), ("b11", 20.0, 643, 550)])
    def test_other_grids_are_not_nested(
        self, tmp_path: Path, bands: dict[str, Path], monkeypatch, other: tuple[str, float, int, int]
    ) -> None:
        name, resolution, width, height = other
        odd = sources.build_band_cog(
            tmp_path / "odd.tif", sources.ramp(width, height, 800), resolution=resolution
        )
        sources.serve({sources.url(n): p for n, p in bands.items()} | {sources.url(name): odd}, monkeypatch)
        work = tmp_path / "work"
        work.mkdir()
        step = {"op": "band_math", "op_version": 1, "params": {"expression": "b11 - red"}}
        with pytest.raises(GridMismatch):
            _run(_recipe([step], assets=("red", "b11")), work)
        assert list(work.iterdir()) == []


@pytest.fixture(scope="module")
def cf_store(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return mini_zarr_cf.build_mini_zarr_cf(tmp_path_factory.mktemp("cf") / "mini.zarr")


def _zarr_recipe(scale: float | None, offset: float | None, expression: str) -> dict:
    key = "r10m:b04,b08"
    entry = resolved(
        "ITEM_Z", key, reader="zarr", scale=scale, offset=offset, href=mini_zarr_cf.GROUP_URL, variable="b04,b08"
    )
    entry["bands"] = entry["bands"] * 2
    step = {"op": "band_math", "op_version": 1, "params": {"expression": expression}}
    return {
        "recipe_version": 1,
        "inputs": [{"name": "z", "dataset": "synthetic", "groups": [["ITEM_Z"]], "assets": [key], "resolved": [entry]}],
        "aoi": sources.whole(mini_zarr_cf.SIZE, mini_zarr_cf.SIZE),
        "steps": [step],
        "output": {"kind": "raster", "format": "cog", "dtype": "float32"},
    }


def _zarr_formula() -> numpy.ma.MaskedArray:
    raw = {name: mini_zarr_cf.raw_band(name) for name in ("b04", "b08")}
    physical = {}
    for name, values in raw.items():
        data = values.astype("float32")
        numpy.multiply(data, numpy.array([mini_zarr_cf.SCALE]), out=data, casting="unsafe")
        numpy.add(data, numpy.array([mini_zarr_cf.OFFSET]), out=data, casting="unsafe")
        physical[name] = data.astype("float64")
    mask = (raw["b04"] == mini_zarr_cf.FILL) | (raw["b08"] == mini_zarr_cf.FILL)
    result = (physical["b08"] - physical["b04"]) / (physical["b08"] + physical["b04"])
    return numpy.ma.masked_array(result.astype("float32"), mask=mask)


class TestOnZarr:
    def test_the_variables_are_the_bands_and_the_item_scaling_applies(
        self, tmp_path: Path, cf_store: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sources.serve({}, monkeypatch, zarr_root=cf_store)
        result = _run(_zarr_recipe(mini_zarr_cf.SCALE, mini_zarr_cf.OFFSET, "(b08 - b04) / (b08 + b04)"), tmp_path)
        data = _read(result.path)[0]
        expected = _zarr_formula()
        numpy.testing.assert_array_equal(data.mask, expected.mask)
        numpy.testing.assert_array_equal(data.compressed(), expected.compressed())
        assert [entry.source for entry in result.scaling] == ["item"]

    def test_without_item_scaling_the_stores_own_cf_decoding_applies(
        self, tmp_path: Path, cf_store: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sources.serve({}, monkeypatch, zarr_root=cf_store)
        result = _run(_zarr_recipe(None, None, "(b08 - b04) / (b08 + b04)"), tmp_path)
        expected = _zarr_formula()
        data = _read(result.path)[0]
        numpy.testing.assert_array_equal(data.mask, expected.mask)
        numpy.testing.assert_allclose(data.compressed(), expected.compressed(), rtol=1e-5)
        assert [entry.source for entry in result.scaling] == ["store-cf"]

    def test_a_name_the_store_does_not_have_stops_the_run(
        self, tmp_path: Path, cf_store: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sources.serve({}, monkeypatch, zarr_root=cf_store)
        with pytest.raises(RecipeInvalid, match="b11"):
            _run(_zarr_recipe(None, None, "b11 - b04"), tmp_path)
