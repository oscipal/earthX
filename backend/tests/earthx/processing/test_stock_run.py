"""``processing.run`` on a stock of named bands (recipe version 2, adr/0020 §4–§8, NM4-43c).

Synthetic COGs served through the real `readers`: ``red`` and ``nir`` at 10 m, ``swir`` and the layer ``scl`` at 20 m,
nested on the same extent. The expected values are formulas on the physical values, not a second implementation.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy
import pytest
import rasterio
from rio_tiler.io import Reader

from earthx.processing import run
from earthx.processing.errors import RecipeInvalid, UnsupportedRecipe
from earthx.processing.operators import REGISTRY
from earthx.processing.recipe import recipe_from_data
from tests.earthx.processing import sources
from tests.earthx.processing.recipes import resolved
from tests.earthx.processing.version_1_cases import HEIGHT, WIDTH, scl_layer

NDVI = {"op": "band_math", "op_version": 2, "params": {"expression": "(nir - red) / (nir + red)", "name": "NDVI"}}
NDWI = {"op": "band_math", "op_version": 2, "params": {"expression": "(swir - nir) / (swir + nir)", "name": "NDWI"}}
MASK = {"op": "mask", "op_version": 2, "params": {"source": "scl", "classes": [3, 8, 9, 10]}}
NORMALIZE = {
    "op": "normalize",
    "op_version": 2,
    "params": {"bands": ["red"], "in_min": 0.0, "in_max": 0.5, "out_min": 0.0, "out_max": 255.0, "clip": True},
}
REPROJECT = {
    "op": "reproject",
    "op_version": 4,
    "params": {"crs": "EPSG:3035", "resolution": 20.0, "resampling": "bilinear", "align": True},
}


def _entry(asset: str) -> dict:
    coarse, layer = asset in ("swir", "scl"), asset == "scl"
    entry = resolved(
        "ITEM_A", asset, href=sources.url(asset), scale=None if layer else 0.0001, offset=None if layer else -0.1
    )
    entry["bands"] = (
        [{"data_type": "uint8", "nodata": 0, "scale": None, "offset": None}] if layer else entry["bands"]
    )
    entry["gsd"] = 20.0 if coarse else 10.0
    if not layer:
        entry["bands"][0]["unit"] = "1"
    return entry


def _recipe(steps: list, bands: list[str], assets=("red", "nir", "swir", "scl"), dtype="float32") -> dict:
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
        "output": {"kind": "raster", "format": "cog", "dtype": dtype, "bands": bands},
    }


def _run(data: dict, workdir: Path, progress=lambda done, total: None):
    return run(recipe_from_data(data, REGISTRY), workdir=workdir, progress=progress, operators=REGISTRY)


def _read(path: Path) -> numpy.ma.MaskedArray:
    with rasterio.open(path) as dataset:
        return dataset.read(masked=True)


@pytest.fixture(scope="module")
def bands(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    root = tmp_path_factory.mktemp("stock")
    return {
        "red": sources.build_band_cog(root / "red.tif", sources.ramp(WIDTH, HEIGHT, 1200)),
        "nir": sources.build_band_cog(root / "nir.tif", sources.ramp(WIDTH, HEIGHT, 3400)),
        "swir": sources.build_band_cog(root / "swir.tif", sources.ramp(WIDTH // 2, HEIGHT // 2, 2200), resolution=20.0),
        "scl": sources.build_band_cog(
            root / "scl.tif", scl_layer(WIDTH // 2, HEIGHT // 2), scale=None, offset=None, resolution=20.0
        ),
    }


@pytest.fixture
def served(bands: dict[str, Path], monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """The addresses that passed ``check_url``: the files the core opened."""
    return sources.serve({sources.url(name): path for name, path in bands.items()}, monkeypatch)


@pytest.fixture(scope="module")
def physical(bands: dict[str, Path]) -> dict[str, numpy.ma.MaskedArray]:
    result = {}
    for name in ("red", "nir"):
        with Reader(str(bands[name])) as reader:
            result[name] = reader.read(unscale=True).array[0]
    return result


@pytest.mark.usefixtures("served")
class TestTwoResultsBesideTheData:
    def test_ndvi_and_ndwi_are_two_bands_of_one_file_in_the_order_of_the_output(self, tmp_path: Path) -> None:
        result = _run(_recipe([NDVI, NDWI], ["NDWI", "NDVI"]), tmp_path)
        data = _read(result.path)
        assert data.shape == (2, HEIGHT, WIDTH) and data.dtype == numpy.float32
        with rasterio.open(result.path) as dataset:
            assert dataset.descriptions == ("NDWI", "NDVI")
        assert [band.name for band in result.meta.bands] == ["NDWI", "NDVI"]
        assert [band["name"] for band in result.properties["bands"]] == ["NDWI", "NDVI"]

    def test_the_values_are_the_formulas_on_physical_values(self, tmp_path: Path, physical: dict) -> None:
        result = _run(_recipe([NDVI], ["NDVI"]), tmp_path)
        red, nir = (physical[name].astype("float64") for name in ("red", "nir"))
        expected = numpy.ma.masked_array(
            ((nir - red) / (nir + red)).astype("float32"),
            mask=numpy.ma.getmaskarray(red) | numpy.ma.getmaskarray(nir),
        )
        data = _read(result.path)[0]
        numpy.testing.assert_array_equal(data.mask, expected.mask)
        numpy.testing.assert_array_equal(data.compressed(), expected.compressed())

    def test_a_band_of_the_data_may_be_in_the_output_beside_a_result(self, tmp_path: Path, physical: dict) -> None:
        result = _run(_recipe([NDVI], ["red", "NDVI"]), tmp_path)
        data = _read(result.path)
        numpy.testing.assert_array_equal(data[0].compressed(), physical["red"].astype("float32").compressed())
        assert [band.name for band in result.meta.bands] == ["red", "NDVI"]

    def test_a_second_result_may_use_the_first(self, tmp_path: Path) -> None:
        twice = {"op": "band_math", "op_version": 2, "params": {"expression": "NDVI * 2 + 1", "name": "Twice"}}
        result = _run(_recipe([NDVI, twice], ["NDVI", "Twice"]), tmp_path)
        data = _read(result.path)
        numpy.testing.assert_allclose(data[1].compressed(), (data[0].astype("float64") * 2 + 1).astype("float32").compressed(), rtol=1e-6)

    def test_the_layer_of_a_mask_is_in_the_file_only_where_the_output_says_so(self, tmp_path: Path) -> None:
        (tmp_path / "a").mkdir()
        (tmp_path / "b").mkdir()
        without = _run(_recipe([MASK], ["red", "nir"]), tmp_path / "a")
        within = _run(_recipe([MASK], ["red", "nir", "scl"]), tmp_path / "b")
        assert [band.name for band in without.meta.bands] == ["red", "nir"]
        assert [band.name for band in within.meta.bands] == ["red", "nir", "scl"]
        # The layer is masked at its own hidden classes like every other band (adr/0020 §4).
        layer = _read(within.path)[2]
        assert numpy.isin(layer.compressed(), [3, 8, 9, 10]).sum() == 0 and layer.mask.sum() > 0

    def test_the_properties_and_the_file_say_the_same_names_and_nodata(self, tmp_path: Path) -> None:
        result = _run(_recipe([NDVI], ["red", "NDVI"]), tmp_path)
        with rasterio.open(result.path) as dataset:
            assert dataset.descriptions == ("red", "NDVI")
            assert all(numpy.isnan(nodata) for nodata in dataset.nodatavals)
        red, ndvi = result.properties["bands"]
        assert (red["name"], red["data_type"], red["nodata"]) == ("red", "float32", "nan")
        assert (ndvi["name"], ndvi["data_type"], ndvi["nodata"]) == ("NDVI", "float32", "nan")

    def test_the_unit_of_a_band_is_in_the_properties_and_a_formula_has_none(self, tmp_path: Path) -> None:
        result = _run(_recipe([NDVI], ["red", "NDVI"]), tmp_path)
        red, ndvi = result.properties["bands"]
        assert red["unit"] == "1" and "unit" not in ndvi
        assert [band.unit for band in result.meta.bands] == ["1", None]

    def test_the_lineage_and_the_expressions_name_every_result(self, tmp_path: Path) -> None:
        result = _run(_recipe([NDVI, NDWI], ["NDVI", "NDWI"]), tmp_path)
        assert result.properties["processing:lineage"] == (
            "band math: NDVI = (nir - red) / (nir + red); band math: NDWI = (swir - nir) / (swir + nir)"
        )
        assert [entry["name"] for entry in result.properties["processing:expression"]] == ["NDVI", "NDWI"]


@pytest.mark.usefixtures("served")
class TestDroppingWhatIsNotNeededChangesNoValue:
    """Each chain with the planner's drops against the same chain that keeps every band (adr/0020 §4)."""

    @pytest.mark.parametrize(
        ("name", "steps", "kept"),
        [
            ("band_math", [NDVI], ["NDVI"]),
            ("two results", [NDVI, NDWI], ["NDWI"]),
            ("mask", [MASK, NDVI], ["NDVI"]),
            ("normalize", [NORMALIZE], ["red"]),
            ("normalize and mask", [MASK, NORMALIZE, NDVI], ["NDVI", "red"]),
            ("reproject", [REPROJECT], ["red"]),
            ("results before reproject", [NDVI, REPROJECT], ["NDVI"]),
            ("results after reproject", [REPROJECT, NDVI], ["NDVI"]),
            ("mask before reproject", [MASK, REPROJECT], ["red", "nir"]),
        ],
    )
    def test_the_kept_bands_are_the_same_bytes(self, name: str, steps: list, kept: list[str], tmp_path: Path) -> None:
        for sub in ("dropped", "everything"):
            (tmp_path / sub).mkdir()
        dropped = _run(_recipe(steps, kept), tmp_path / "dropped")
        everything_in_the_stock = [band.name for band in _stock(steps)]
        full = _run(_recipe(steps, everything_in_the_stock), tmp_path / "everything")
        a, b = _read(dropped.path), _read(full.path)
        for index, band in enumerate(kept):
            other = everything_in_the_stock.index(band)
            assert a[index].data.tobytes() == b[other].data.tobytes(), band
            assert a[index].mask.tobytes() == b[other].mask.tobytes(), band

    def test_a_file_of_fewer_bands_is_smaller_and_reads_fewer_blocks(self, tmp_path: Path) -> None:
        for sub in ("one", "four"):
            (tmp_path / sub).mkdir()
        one = _run(_recipe([NDVI], ["NDVI"]), tmp_path / "one")
        four = _run(_recipe([NDVI], ["red", "nir", "swir", "NDVI"]), tmp_path / "four")
        assert one.path.stat().st_size < four.path.stat().st_size
        assert one.meta.width == four.meta.width


def _stock(steps: list) -> list:
    """The bands the chain has in the end if nothing is dropped: the data and what each ``band_math`` adds."""
    from earthx.processing.operators import BandMeta

    names = ["red", "nir", "swir", "scl"] + [s["params"]["name"] for s in steps if s["op"] == "band_math"]
    return [BandMeta(name, "float32", float("nan")) for name in names]


@pytest.mark.usefixtures("served")
class TestWhatIsRead:
    def test_the_core_opens_the_assets_of_the_recipe_and_no_other(self, tmp_path: Path, served: list[str]) -> None:
        _run(_recipe([NDVI], ["NDVI"], assets=("red", "nir")), tmp_path)
        assert sorted(set(served)) == sorted([sources.url("red"), sources.url("nir")])

    def test_an_asset_that_is_in_the_recipe_but_nobody_needs_is_read_and_dropped(self, tmp_path: Path) -> None:
        """What `api` derives is exact; a recipe someone wrote by hand may carry more, and the result is the same."""
        (tmp_path / "exact").mkdir()
        (tmp_path / "more").mkdir()
        exact = _run(_recipe([NDVI], ["NDVI"], assets=("red", "nir")), tmp_path / "exact")
        more = _run(_recipe([NDVI], ["NDVI"], assets=("red", "nir", "swir", "scl")), tmp_path / "more")
        assert _read(exact.path).tobytes() == _read(more.path).tobytes()


@pytest.mark.usefixtures("served")
class TestRefusals:
    def test_an_output_band_that_the_stock_does_not_hold_fails_before_the_first_block_and_leaves_nothing(
        self, tmp_path: Path
    ) -> None:
        ticks: list[int] = []
        with pytest.raises(RecipeInvalid, match="output.bands names unknown band.*: NDWI;"):
            _run(_recipe([NDVI], ["NDVI", "NDWI"]), tmp_path, progress=lambda done, total: ticks.append(done))
        assert ticks == [] and list(tmp_path.iterdir()) == []

    def test_a_result_named_like_a_band_of_the_data_fails_before_the_first_block(self, tmp_path: Path) -> None:
        taken = {"op": "band_math", "op_version": 2, "params": {"expression": "nir - red", "name": "Red"}}
        with pytest.raises(RecipeInvalid, match="Red is used twice"):
            _run(_recipe([taken], ["Red"]), tmp_path)
        assert list(tmp_path.iterdir()) == []

    def test_a_step_of_version_1_is_no_step_of_a_stock(self, tmp_path: Path) -> None:
        old = {"op": "band_math", "op_version": 1, "params": {"expression": "nir - red"}}
        with pytest.raises(RecipeInvalid, match="replaces or removes bands"):
            _run(_recipe([old], ["band_math"]), tmp_path)

    def test_an_integer_output_needs_one_nodata_for_every_band_it_holds(self, tmp_path: Path) -> None:
        with pytest.raises(UnsupportedRecipe, match="integer output needs one nodata"):
            _run(_recipe([NDVI], ["red", "NDVI"], dtype="uint16"), tmp_path)

    def test_a_recipe_without_bands_in_the_output_is_not_a_recipe(self) -> None:
        data = _recipe([NDVI], ["NDVI"])
        data["output"].pop("bands")
        with pytest.raises(RecipeInvalid, match="bands: missing"):
            recipe_from_data(data, REGISTRY)
        data["output"]["bands"] = []
        with pytest.raises(RecipeInvalid, match="bands"):
            recipe_from_data(data, REGISTRY)
        data["output"]["bands"] = ["NDVI", "ndvi"]
        with pytest.raises(RecipeInvalid, match="invalid recipe: output.raster: value_error"):
            recipe_from_data(data, REGISTRY)

    def test_the_recipe_round_trips_through_json_with_its_bands(self) -> None:
        recipe = recipe_from_data(_recipe([NDVI], ["NDVI"]), REGISTRY)
        assert json.loads(recipe.model_dump_json())["output"]["bands"] == ["NDVI"]


@pytest.mark.usefixtures("served")
class TestTheHonestyFlag:
    """``earthx:resampled`` says so where values were brought onto another grid, not where only a layer was (backlog 51)."""

    def test_a_layer_that_only_hides_pixels_does_not_mark_the_result(self, tmp_path: Path) -> None:
        result = _run(_recipe([MASK, NDVI], ["NDVI"]), tmp_path)
        assert result.properties["earthx:resampled"] is False and result.meta.resampled is False

    def test_a_band_read_from_a_coarser_asset_marks_the_result(self, tmp_path: Path) -> None:
        result = _run(_recipe([NDWI], ["NDWI"]), tmp_path)
        assert result.properties["earthx:resampled"] is True and result.meta.resampled is True

    def test_a_coarser_band_that_the_output_does_not_keep_does_not_mark_it(self, tmp_path: Path) -> None:
        result = _run(_recipe([NDWI, NDVI], ["NDVI"]), tmp_path)
        assert result.properties["earthx:resampled"] is False

    def test_a_coarser_band_in_the_output_marks_it_the_layer_included(self, tmp_path: Path) -> None:
        assert _run(_recipe([], ["red", "swir"]), tmp_path).properties["earthx:resampled"] is True

    def test_reproject_marks_the_result_as_before(self, tmp_path: Path) -> None:
        assert _run(_recipe([REPROJECT], ["red"]), tmp_path).properties["earthx:resampled"] is True

    def test_nothing_on_another_grid_leaves_it_unmarked(self, tmp_path: Path) -> None:
        assert _run(_recipe([], ["red", "nir"]), tmp_path).properties["earthx:resampled"] is False
