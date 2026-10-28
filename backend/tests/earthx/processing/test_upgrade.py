"""Orders and recipes of version 1 written as version 2 (adr/0020 §11, NM4-43c): what the rewrite says and what it refuses."""

from __future__ import annotations

import copy
import json
from typing import Any

import pytest

from earthx.processing.errors import RecipeInvalid
from earthx.processing.operators import REGISTRY
from earthx.processing.upgrade import (
    is_version_1,
    key_names,
    recipe_of_any_version,
    reproject_changes_values,
    upgrade_order,
    upgrade_recipe,
)
from tests.earthx.processing.recipes import SQUARE, recipe_data, request_data, resolved

NORMALIZE = {"in_min": 0.0, "in_max": 1.0, "out_min": 0.0, "out_max": 255.0, "clip": True}


def _step(op: str, version: int, **params: Any) -> dict[str, Any]:
    return {"op": op, "op_version": version, "params": params}


def _order(steps: list[dict[str, Any]], assets: tuple[str, ...] = ("red", "nir", "scl")) -> dict[str, Any]:
    return {
        "recipe_version": 1,
        "inputs": [{"name": "s2", "dataset": "synthetic", "groups": [["ITEM_A"]], "assets": list(assets)}],
        "aoi": copy.deepcopy(SQUARE),
        "steps": steps,
        "output": {"kind": "raster", "format": "cog", "dtype": "float32"},
    }


def _bands(upgraded: dict[str, Any]) -> list[str]:
    return upgraded["output"]["bands"]


class TestAnOrder:
    def test_without_steps_the_output_is_every_asset_and_the_order_names_no_assets(self) -> None:
        upgraded = upgrade_order(_order([]))
        assert upgraded["recipe_version"] == 2
        assert _bands(upgraded) == ["red", "nir", "scl"]
        assert "assets" not in upgraded["inputs"][0]

    def test_the_last_expression_is_called_band_math_as_before_and_the_earlier_ones_band_math_n(self) -> None:
        steps = [_step("band_math", 1, expression="nir - red"), _step("band_math", 1, expression="band_math * 2")]
        upgraded = upgrade_order(_order(steps))
        assert [step["params"]["name"] for step in upgraded["steps"]] == ["band_math_1", "band_math"]
        assert upgraded["steps"][1]["params"]["expression"] == "band_math_1 * 2"
        assert [step["op_version"] for step in upgraded["steps"]] == [2, 2]
        assert _bands(upgraded) == ["band_math"]

    def test_one_expression_is_called_band_math(self) -> None:
        upgraded = upgrade_order(_order([_step("band_math", 1, expression="nir - red")]))
        assert upgraded["steps"][0]["params"] == {"expression": "nir - red", "name": "band_math"}

    def test_normalize_gets_the_bands_it_saw(self) -> None:
        upgraded = upgrade_order(_order([_step("mask", 1, source="scl", classes=[3]), _step("normalize", 1, **NORMALIZE)]))
        assert upgraded["steps"][1]["params"]["bands"] == ["red", "nir"]  # the layer was gone after the mask
        assert upgraded["steps"][1]["op_version"] == 2

    def test_normalize_before_the_mask_saw_the_layer_too(self) -> None:
        upgraded = upgrade_order(_order([_step("normalize", 1, **NORMALIZE), _step("mask", 1, source="scl", classes=[3])]))
        assert upgraded["steps"][0]["params"]["bands"] == ["red", "nir", "scl"]
        assert _bands(upgraded) == ["red", "nir"]

    def test_normalize_after_an_expression_saw_the_result_alone(self) -> None:
        upgraded = upgrade_order(_order([_step("band_math", 1, expression="nir - red"), _step("normalize", 1, **NORMALIZE)]))
        assert upgraded["steps"][1]["params"]["bands"] == ["band_math"]

    def test_the_layer_of_a_mask_is_no_longer_in_the_output(self) -> None:
        upgraded = upgrade_order(_order([_step("mask", 1, source="scl", classes=[3, 8])]))
        assert _bands(upgraded) == ["red", "nir"]
        assert upgraded["steps"][0] == _step("mask", 2, source="scl", classes=[3, 8])

    def test_reproject_keeps_its_version_and_its_place(self) -> None:
        reproject = _step("reproject", 3, crs="EPSG:3035", resolution=20.0, resampling="nearest", align=False)
        upgraded = upgrade_order(_order([reproject, _step("band_math", 1, expression="nir - red")]))
        assert upgraded["steps"][0] == reproject
        assert upgraded["steps"][1]["op_version"] == 2

    def test_a_word_that_only_looks_like_the_old_name_is_left_alone(self) -> None:
        steps = [
            _step("band_math", 1, expression="nir - red"),
            _step("band_math", 1, expression="band_math2 + band_math + 1e5"),
        ]
        upgraded = upgrade_order(_order(steps))
        assert upgraded["steps"][1]["params"]["expression"] == "band_math2 + band_math_1 + 1e5"

    def test_the_input_is_not_changed(self) -> None:
        order = _order([_step("band_math", 1, expression="nir - red")])
        before = copy.deepcopy(order)
        upgrade_order(order)
        assert order == before

    def test_a_zarr_key_is_named_by_its_variables(self) -> None:
        upgraded = upgrade_order(_order([], ("SR_10m:b04", "SR_20m:b05,b06")), key_names(":"))
        assert _bands(upgraded) == ["b04", "b05", "b06"]

    def test_the_bands_come_from_the_caller_where_he_knows_more(self) -> None:
        upgraded = upgrade_order(_order([], ("visual",)), lambda key: [f"{key}_1", f"{key}_2", f"{key}_3"])
        assert _bands(upgraded) == ["visual_1", "visual_2", "visual_3"]

    def test_a_crop_has_no_stock_and_changes_only_its_version(self) -> None:
        crop = {
            **_order([], ("visual",)),
            "output": {
                "kind": "crop",
                "format": "cog",
                "resolution_factor": 1,
                "extent": "bbox(aoi ∩ footprints)",
                "mask": "file",
            },
        }
        upgraded = upgrade_order(crop)
        assert upgraded["recipe_version"] == 2 and upgraded["inputs"] == crop["inputs"]
        assert upgraded["output"] == crop["output"]

    @pytest.mark.parametrize(
        "broken",
        [
            lambda o: o.update(recipe_version=2),
            lambda o: o.update(recipe_version=True),
            lambda o: o.update(recipe_version=1.0),
            lambda o: o.update(inputs=[]),
            lambda o: o.update(inputs="x"),
            lambda o: o["inputs"][0].update(assets="red"),
            lambda o: o["inputs"][0].update(assets=[1]),
            lambda o: o.update(steps="x"),
            lambda o: o.update(steps=["x"]),
            lambda o: o.update(output=None),
        ],
    )
    def test_a_document_that_is_no_order_of_version_1_is_refused_without_a_value(self, broken) -> None:
        order = _order([])
        broken(order)
        with pytest.raises(RecipeInvalid, match="not a document of recipe version 1"):
            upgrade_order(order)


class TestARecipe:
    def _recipe(self, steps: list[dict[str, Any]], assets: tuple[str, ...] = ("red", "nir")) -> dict[str, Any]:
        data = recipe_data(steps=steps)
        data["recipe_version"] = 1
        data["output"] = {"kind": "raster", "format": "cog", "dtype": "float32"}
        data["inputs"][0]["assets"] = list(assets)
        data["inputs"][0]["resolved"] = [resolved("ITEM_A", asset) for asset in assets]
        return data

    def test_the_assets_and_the_addresses_stay_as_they_are(self) -> None:
        recipe = self._recipe([_step("band_math", 1, expression="nir - red")])
        upgraded = upgrade_recipe(recipe)
        assert upgraded["inputs"] == recipe["inputs"]
        assert _bands(upgraded) == ["band_math"] and upgraded["recipe_version"] == 2

    def test_the_names_come_from_the_resolved_assets(self) -> None:
        recipe = self._recipe([], ("red",))
        recipe["inputs"][0]["resolved"][0]["bands"] = [{"data_type": "uint8", "nodata": 0, "scale": None, "offset": None}] * 3
        recipe["inputs"][0]["resolved"][0]["scaling"] = "none"
        assert _bands(upgrade_recipe(recipe)) == ["red_1", "red_2", "red_3"]

    def test_an_asset_whose_bands_only_the_file_knows_counts_as_one_band_named_like_the_asset(self) -> None:
        recipe = self._recipe([], ("dem",))
        recipe["inputs"][0]["resolved"][0]["bands"] = []
        recipe["inputs"][0]["resolved"][0]["scaling"] = "none"
        assert _bands(upgrade_recipe(recipe)) == ["dem"]

    def test_the_rewritten_recipe_is_one_the_models_read(self) -> None:
        recipe = self._recipe(
            [_step("normalize", 1, **NORMALIZE), _step("band_math", 1, expression="nir - red")]
        )
        parsed = recipe_of_any_version(json.dumps(recipe), REGISTRY)
        assert parsed.output.bands == ["band_math"]
        assert [(step.op, step.op_version) for step in parsed.steps] == [("normalize", 2), ("band_math", 2)]

    def test_a_recipe_of_version_2_is_read_as_it_is(self) -> None:
        recipe = recipe_data(steps=[])
        assert recipe_of_any_version(json.dumps(recipe), REGISTRY).output.bands == ["red", "nir"]

    def test_text_that_is_no_recipe_is_refused(self) -> None:
        with pytest.raises(RecipeInvalid):
            recipe_of_any_version("[1, 2]", REGISTRY)
        with pytest.raises(RecipeInvalid, match="not a JSON document"):
            recipe_of_any_version("{", REGISTRY)


class TestWhichRecipesNeedAWord:
    @pytest.mark.parametrize(("version", "needs"), [(2, True), (3, True), (4, False), (1, False)])
    def test_only_reproject_that_warps_all_bands_at_once_can_give_other_values(self, version: int, needs: bool) -> None:
        steps = [_step("reproject", version, crs="EPSG:3035", resolution=20.0, resampling="nearest", align=False)]
        assert reproject_changes_values({"steps": steps}) is needs

    def test_a_recipe_without_reproject_needs_none(self) -> None:
        assert not reproject_changes_values({"steps": [_step("band_math", 1, expression="a")]})
        assert not reproject_changes_values({"steps": "x"})
        assert not reproject_changes_values({})


class TestVersionOne:
    @pytest.mark.parametrize(("document", "is_one"), [({"recipe_version": 1}, True), ({"recipe_version": 2}, False), ({"recipe_version": True}, False), ({"recipe_version": 1.0}, False), ({}, False), ([], False)])
    def test_only_the_integer_1_is_version_1(self, document: object, is_one: bool) -> None:
        assert is_version_1(document) is is_one

    def test_an_order_for_a_raster_of_version_2_has_no_assets_in_its_test_data(self) -> None:
        assert "assets" not in request_data()["inputs"][0]
