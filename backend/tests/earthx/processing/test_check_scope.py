"""`check_scope`: what the core can run, asked before a job waits in the queue (M4-08b K3)."""

from __future__ import annotations

import copy

import pytest

from earthx.processing import check_scope
from earthx.processing.errors import UnsupportedRecipe
from earthx.processing.recipe import RasterOutput, recipe_from_data
from tests.earthx.processing.recipes import recipe_data, resolved
from tests.earthx.processing.testops import OPERATORS


def test_a_raster_of_one_item_is_in_scope() -> None:
    recipe = recipe_from_data(recipe_data(), OPERATORS)
    assert isinstance(check_scope(recipe), RasterOutput)


def test_a_crop_output_is_described_not_run() -> None:
    crop = {
        "kind": "crop",
        "format": "cog",
        "resolution_factor": 1,
        "extent": "bbox(aoi ∩ footprints)",
        "mask": "file",
    }
    recipe = recipe_from_data(recipe_data(steps=[], output=crop), OPERATORS)
    with pytest.raises(UnsupportedRecipe, match="crop"):
        check_scope(recipe)


@pytest.mark.parametrize("groups", [[["ITEM_A", "ITEM_B"]], [["ITEM_A"], ["ITEM_B"]]])
def test_several_items_come_with_m4_11_and_m4_12(groups: list[list[str]]) -> None:
    data = recipe_data()
    data["inputs"][0]["groups"] = copy.deepcopy(groups)
    data["inputs"][0]["resolved"] += [resolved("ITEM_B", "red"), resolved("ITEM_B", "nir")]
    recipe = recipe_from_data(data, OPERATORS)
    with pytest.raises(UnsupportedRecipe, match="one item"):
        check_scope(recipe)
