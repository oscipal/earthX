"""`check_scope`: what the core can run, asked before a job waits in the queue (M4-08b K3, M4-11a)."""

from __future__ import annotations

import copy

import pytest

from earthx.processing import check_scope
from earthx.processing.errors import ExportTooLarge, RecipeInvalid, UnsupportedRecipe
from earthx.processing.recipe import CropOutput, RasterOutput, recipe_from_data
from tests.earthx.processing.recipes import CROP, crop_data, recipe_data, resolved
from tests.earthx.processing.testops import OPERATORS


def test_a_raster_of_one_item_is_in_scope() -> None:
    recipe = recipe_from_data(recipe_data(), OPERATORS)
    assert isinstance(check_scope(recipe), RasterOutput)


def _two_scenes(groups: list[list[str]]) -> dict:
    data = recipe_data()
    data["inputs"][0]["groups"] = copy.deepcopy(groups)
    data["inputs"][0]["resolved"] += [resolved("ITEM_B", "red"), resolved("ITEM_B", "nir")]
    return data


def test_a_raster_of_the_scenes_of_one_overpass_is_in_scope() -> None:
    """One group of several items is a mosaic (M4-12a)."""
    recipe = recipe_from_data(_two_scenes([["ITEM_A", "ITEM_B"]]), OPERATORS)
    assert isinstance(check_scope(recipe), RasterOutput)


def test_a_raster_run_still_reads_one_group() -> None:
    recipe = recipe_from_data(_two_scenes([["ITEM_A"], ["ITEM_B"]]), OPERATORS)
    with pytest.raises(UnsupportedRecipe, match="one group"):
        check_scope(recipe)


def test_a_zarr_mosaic_in_one_crs_is_in_scope_and_over_two_crs_is_refused() -> None:
    data = _two_scenes([["ITEM_A", "ITEM_B"]])
    for entry in data["inputs"][0]["resolved"]:
        entry["asset"]["reader"] = "zarr"
        entry["asset"]["variable"] = entry["asset"]["asset"]
        entry["scaling"] = "item"
    assert isinstance(check_scope(recipe_from_data(copy.deepcopy(data), OPERATORS)), RasterOutput)
    data["inputs"][0]["resolved"][2]["asset"]["crs"] = "EPSG:32633"
    data["inputs"][0]["resolved"][3]["asset"]["crs"] = "EPSG:32633"
    with pytest.raises(UnsupportedRecipe, match="one CRS"):
        check_scope(recipe_from_data(data, OPERATORS))


@pytest.mark.parametrize("groups", [[["ITEM_A"]], [["ITEM_A", "ITEM_B"]], [["ITEM_A"], ["ITEM_B", "ITEM_C"]]])
def test_an_export_of_several_groups_and_items_is_in_scope(groups: list[list[str]]) -> None:
    recipe = recipe_from_data(crop_data(groups), OPERATORS)
    assert isinstance(check_scope(recipe), CropOutput)


def test_an_export_with_steps_is_refused() -> None:
    data = crop_data()
    data["steps"] = [{"op": "scale", "op_version": 1, "params": {"factor": 2.0}}]
    with pytest.raises(UnsupportedRecipe, match="no steps"):
        check_scope(recipe_from_data(data, OPERATORS))


def test_an_export_at_a_coarser_resolution_is_refused() -> None:
    data = crop_data()
    data["output"] = {**CROP, "resolution_factor": 2}
    with pytest.raises(UnsupportedRecipe, match="native resolution"):
        check_scope(recipe_from_data(data, OPERATORS))


def test_an_export_of_zarr_assets_is_refused() -> None:
    data = crop_data()
    data["inputs"][0]["resolved"] = [resolved("ITEM_A", "visual", reader="zarr", scale=None, offset=None)]
    with pytest.raises(UnsupportedRecipe, match="COG assets only"):
        check_scope(recipe_from_data(data, OPERATORS))


def test_an_export_over_the_cap_is_refused_by_the_estimate() -> None:
    data = crop_data()
    data["aoi"] = {"type": "Polygon", "coordinates": [[[9.0, 45.0], [14.0, 45.0], [14.0, 50.0], [9.0, 50.0], [9.0, 45.0]]]}
    for item in data["inputs"][0]["footprints"]:
        data["inputs"][0]["footprints"][item] = copy.deepcopy(data["aoi"])
    with pytest.raises(ExportTooLarge, match="more than the 5000 MB"):
        check_scope(recipe_from_data(data, OPERATORS))


def test_a_crop_without_footprints_is_not_a_recipe() -> None:
    data = crop_data()
    del data["inputs"][0]["footprints"]
    with pytest.raises(RecipeInvalid):
        recipe_from_data(data, OPERATORS)


def test_a_raster_recipe_carries_no_footprints() -> None:
    data = recipe_data()
    data["inputs"][0]["footprints"] = {"ITEM_A": None}
    with pytest.raises(RecipeInvalid):
        recipe_from_data(data, OPERATORS)


def test_footprints_name_exactly_the_items() -> None:
    data = crop_data([["ITEM_A", "ITEM_B"]])
    del data["inputs"][0]["footprints"]["ITEM_B"]
    with pytest.raises(RecipeInvalid):
        recipe_from_data(data, OPERATORS)


def test_two_assets_with_one_file_name_are_refused() -> None:
    data = crop_data(assets=("B04", "B04."))
    with pytest.raises(UnsupportedRecipe, match="same file name"):
        check_scope(recipe_from_data(data, OPERATORS))
