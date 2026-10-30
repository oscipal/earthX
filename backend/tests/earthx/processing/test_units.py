"""The unit of a band through the core: recipe, operators and the result (plan M4-19b §3.2, adr/0014 §15n).

Synthetic COGs served through the real `readers`, as in ``test_band_math_run``. The units are invented text:
what the registry or an item names is tested where they are read (``catalog/test_band_units``, ``api/test_intake``).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
import rasterio
from rasterio.transform import Affine

from earthx.processing import run
from earthx.processing.errors import UnsupportedRecipe
from earthx.processing.mosaic import check_alike
from earthx.processing.operators import MASK, NORMALIZE, REGISTRY, REPROJECT, BandMeta, RasterMeta
from earthx.processing.operators.band_math import BAND_MATH, BandMathParams
from earthx.processing.operators.mask import MaskParams
from earthx.processing.operators.normalize import NormalizeParams
from earthx.processing.plan import _input_meta
from earthx.processing.source import expected_band_names, units_of
from tests.earthx.processing import sources
from tests.earthx.processing.recipes import recipe_data, recipe_of_data, resolved
from tests.earthx.processing.test_reproject import _params
from tests.earthx.processing.testops import OPERATORS

WIDTH, HEIGHT = 300, 200
SCALE_STEP = {"op": "band_math", "op_version": 1, "params": {"expression": "red"}}
NDVI = {"op": "band_math", "op_version": 1, "params": {"expression": "(nir - red) / (nir + red)"}}


def _entry(asset: str, **options) -> dict:
    return resolved("ITEM_A", asset, href=sources.url(asset), **options)


def _recipe(entries: list[dict], steps: list[dict]) -> dict:
    assets = [entry["asset"]["asset"] for entry in entries]
    return {
        "recipe_version": 1,
        "inputs": [
            {"name": "s2", "dataset": "synthetic", "groups": [["ITEM_A"]], "assets": assets, "resolved": entries}
        ],
        "aoi": sources.whole(WIDTH, HEIGHT),
        "steps": steps,
        "output": {"kind": "raster", "format": "cog", "dtype": "float32"},
    }


def _run(data: dict, workdir: Path):
    return run(recipe_of_data(data, REGISTRY), workdir=workdir, progress=lambda done, total: None, operators=REGISTRY)


@pytest.fixture(scope="module")
def files(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    root = tmp_path_factory.mktemp("units")
    return {
        "red": sources.build_band_cog(root / "red.tif", sources.ramp(WIDTH, HEIGHT, 1200)),
        "nir": sources.build_band_cog(root / "nir.tif", sources.ramp(WIDTH, HEIGHT, 3400)),
        "plain": sources.build_band_cog(
            root / "plain.tif", sources.ramp(WIDTH, HEIGHT, 100), scale=None, offset=None
        ),
    }


@pytest.fixture
def served(files: dict[str, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    sources.serve(
        {sources.url("red"): files["red"], sources.url("nir"): files["nir"], sources.url("plain"): files["plain"]},
        monkeypatch,
    )


def _unit(entry: dict, unit: str | None) -> dict:
    entry["bands"][0]["unit"] = unit
    return entry


@pytest.mark.usefixtures("served")
class TestTheResult:
    def test_a_band_that_came_through_untouched_keeps_its_unit(self, tmp_path: Path) -> None:
        data = _recipe([_unit(_entry("red"), "1"), _unit(_entry("nir"), "1")], [])
        result = _run(data, tmp_path)
        assert [band.unit for band in result.meta.bands] == ["1", "1"]
        assert [band["unit"] for band in result.properties["bands"]] == ["1", "1"]

    def test_the_unit_stands_between_nodata_and_the_statistics(self, tmp_path: Path) -> None:
        data = _recipe([_unit(_entry("red"), "1")], [])
        keys = list(_run(data, tmp_path).properties["bands"][0])
        assert keys == ["name", "data_type", "nodata", "unit", "statistics"]

    def test_a_band_without_a_unit_says_nothing_about_it(self, tmp_path: Path) -> None:
        data = _recipe([_entry("red")], [])
        band = _run(data, tmp_path).properties["bands"][0]
        assert "unit" not in band

    def test_a_formula_has_no_known_unit(self, tmp_path: Path) -> None:
        data = _recipe([_unit(_entry("red"), "1"), _unit(_entry("nir"), "1")], [NDVI])
        result = _run(data, tmp_path)
        assert result.meta.bands[0].unit is None
        assert "unit" not in result.properties["bands"][0]

    def test_the_bare_name_of_a_band_is_that_band_again(self, tmp_path: Path) -> None:
        data = _recipe([_unit(_entry("red"), "1"), _unit(_entry("nir"), "percent")], [SCALE_STEP])
        result = _run(data, tmp_path)
        assert result.properties["bands"][0]["unit"] == "1"

    def test_a_unit_on_the_input_stands_for_the_bands_of_an_asset_the_item_left_undescribed(
        self, tmp_path: Path
    ) -> None:
        entry = _entry("plain", scale=None, offset=None)
        entry["bands"], entry["unit"] = [], "m"
        result = _run(_recipe([entry], []), tmp_path)
        assert [band["unit"] for band in result.properties["bands"]] == ["m"]

    def test_a_band_count_that_differs_from_the_file_is_not_believed(self, tmp_path: Path) -> None:
        entry = _unit(_entry("plain", scale=None, offset=None), "m")
        entry["bands"] = entry["bands"] * 2
        data = _recipe([entry], [])
        # The item names two bands, the file has one: a recipe of version 1 is rewritten with the names of the
        # item, so the output of version 2 names the band the file really has.
        data["recipe_version"], data["output"]["bands"] = 2, ["plain"]
        result = _run(data, tmp_path)
        assert "unit" not in result.properties["bands"][0]

    def test_a_unit_changes_nothing_in_the_pixels_or_their_statistics(self, tmp_path: Path) -> None:
        (tmp_path / "a").mkdir()
        (tmp_path / "b").mkdir()
        with_unit = _run(_recipe([_unit(_entry("red"), "1")], []), tmp_path / "a")
        without = _run(_recipe([_entry("red")], []), tmp_path / "b")
        with rasterio.open(with_unit.path) as one, rasterio.open(without.path) as other:
            assert one.read().tobytes() == other.read().tobytes()
        assert with_unit.valid_pixels == without.valid_pixels
        assert with_unit.properties["bands"][0]["statistics"] == without.properties["bands"][0]["statistics"]


class TestOperators:
    META = RasterMeta(
        "EPSG:32632",
        Affine(10, 0, 0, 0, -10, 0),
        4,
        4,
        (BandMeta("red", "float32", None, "1"), BandMeta("depth", "float32", None, "m")),
    )

    def test_reproject_passes_the_unit_through(self) -> None:
        out = REPROJECT.transform(self.META, _params())
        assert [band.unit for band in out.bands] == ["1", "m"]

    def test_normalize_states_no_unit_because_the_range_is_the_callers(self) -> None:
        params = NormalizeParams(in_min=0.0, in_max=1.0, out_min=0.0, out_max=255.0, clip=True)
        assert [band.unit for band in NORMALIZE.transform(self.META, params).bands] == [None, None]

    def test_mask_keeps_the_unit_of_what_stays(self) -> None:
        meta = RasterMeta(
            self.META.crs,
            self.META.transform,
            4,
            4,
            (*self.META.bands, BandMeta("scl", "uint8", 0, None)),
        )
        out = MASK.transform(meta, MaskParams(source="scl", classes=[9]))
        assert [(band.name, band.unit) for band in out.bands] == [("red", "1"), ("depth", "m")]

    @pytest.mark.parametrize(
        ("expression", "unit"),
        [("red", "1"), ("depth", "m"), ("(red)", None), ("red * 2", None), ("red + depth", None)],
    )
    def test_band_math_keeps_a_unit_only_for_a_bare_band_name(self, expression: str, unit: str | None) -> None:
        out = BAND_MATH.transform(self.META, BandMathParams(expression=expression))
        assert out.bands[0].unit == unit


def _undescribed() -> dict:
    """A recipe whose first input is a COG asset the item describes with no band, and the registry gives metres."""
    data = recipe_data()
    data["inputs"][0]["resolved"][0] = {
        **resolved("ITEM_A", "red", scale=None, offset=None),
        "bands": [],
        "unit": "m",
    }
    return data


class TestUnitsOf:
    def test_one_per_band_as_the_recipe_has_them(self) -> None:
        entry = recipe_of_data(recipe_data(), OPERATORS).inputs[0].resolved[0]
        assert units_of(entry, 1) == [None]
        data = recipe_data()
        data["inputs"][0]["resolved"][0]["bands"][0]["unit"] = "1"
        assert units_of(recipe_of_data(data, OPERATORS).inputs[0].resolved[0], 1) == ["1"]

    def test_the_unit_of_the_input_is_for_every_band_of_an_asset_without_a_description(self) -> None:
        entry = recipe_of_data(_undescribed(), OPERATORS).inputs[0].resolved[0]
        assert units_of(entry, 3) == ["m", "m", "m"]

    def test_a_description_of_another_length_than_the_file_is_not_believed(self) -> None:
        data = recipe_data()
        data["inputs"][0]["resolved"][0]["bands"][0]["unit"] = "1"
        assert units_of(recipe_of_data(data, OPERATORS).inputs[0].resolved[0], 3) == [None, None, None]

    def test_a_unit_on_the_input_does_not_count_as_a_band(self) -> None:
        assert expected_band_names(recipe_of_data(_undescribed(), OPERATORS).inputs[0].resolved[0]) is None


class TestThePlan:
    def test_the_bands_a_check_looks_at_carry_the_units(self) -> None:
        data = recipe_data()
        data["inputs"][0]["resolved"][0]["bands"][0]["unit"] = "1"
        meta = _input_meta(recipe_of_data(data, OPERATORS), names_known=False, sized=False)
        assert meta is not None
        assert [band.unit for band in meta.bands] == ["1", None]


class TestAMosaic:
    @staticmethod
    def _scene(unit: str | None):
        return SimpleNamespace(names=["red"], data_types=["uint16"], nodata=[0.0], units=[unit], scaling="same")

    def test_scenes_with_the_same_unit_agree(self) -> None:
        check_alike("red", [self._scene("1"), self._scene("1")])

    def test_scenes_with_another_unit_are_refused_by_name(self) -> None:
        with pytest.raises(UnsupportedRecipe, match="differ in the bands, data type, nodata or unit of 'red'"):
            check_alike("red", [self._scene("1"), self._scene("percent")])

    def test_a_scene_that_names_a_unit_and_one_that_does_not_differ(self) -> None:
        with pytest.raises(UnsupportedRecipe, match="unit"):
            check_alike("red", [self._scene("1"), self._scene(None)])
