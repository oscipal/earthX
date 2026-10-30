"""A raster order of recipe version 2 names bands, not assets; `api` derives the assets and takes version 1 for a while
(adr/0020 §4–§6, §11, NM4-43c). Synthetic and offline, on the items and the helpers of ``test_intake``."""

from __future__ import annotations

import json
from datetime import date
from typing import Any

import pytest

from earthx.api import intake
from earthx.api.intake import OrderRefused, band_sources, derive_assets, parse_order, version_1_accepted
from earthx.processing.recipe import cache_key
from tests.earthx.api.test_intake import (
    DEM,
    S2,
    SQUARE,
    ZARR,
    ZARR_ID,
    Source,
    accept,
    band_math,
    dem_item,
    estimate_order,
    order,
    refused,
    s2_item,
    zarr_item,
)
from tests.earthx.processing.testops import OPERATORS

pytestmark = pytest.mark.anyio

SCL = "https://{host}/tiles/{item}/SCL.tif"
NDVI = band_math("(nir - red) / (nir + red)", "NDVI")
NDWI = band_math("(green - nir) / (green + nir)", "NDWI")
MASK = {"op": "mask", "op_version": 2, "params": {"source": "scl", "classes": [3, 8, 9, 10]}}


def _item(**more: Any) -> dict[str, Any]:
    """Sentinel-2 as the source serves it, with the bands the chains below name; ``more`` adds assets."""
    item = s2_item()
    for name in ("green", "swir16", "scl"):
        item["assets"][name] = {**item["assets"]["red"], "href": item["assets"]["red"]["href"].replace("red", name)}
    item["assets"]["scl"]["raster:bands"] = [{"nodata": 0, "data_type": "uint8"}]
    item["assets"]["scl"]["gsd"] = 20
    item["assets"]["thumbnail"] = {**item["assets"]["red"], "type": "image/jpeg", "roles": ["thumbnail"]}
    item["assets"].update(more)
    return item


def _order(steps: list[dict[str, Any]], bands: list[str], **override: Any) -> dict[str, Any]:
    return order(steps=steps, bands=bands, **override)


class TestWhichAssetsAreRead:
    async def test_the_bands_an_expression_names_are_the_assets_and_nothing_else_is_read(self) -> None:
        accepted = await accept(_order([NDVI], ["NDVI"]), Source((S2, _item())))
        assert accepted.recipe.inputs[0].assets == ["red", "nir"]
        assert [entry.asset.asset for entry in accepted.recipe.inputs[0].resolved] == ["red", "nir"]

    async def test_the_layer_of_a_mask_is_read_for_the_bands_it_hides_pixels_in(self) -> None:
        accepted = await accept(_order([MASK, NDVI], ["NDVI"]), Source((S2, _item())))
        assert accepted.recipe.inputs[0].assets == ["red", "nir", "scl"]

    async def test_the_assets_come_in_the_order_of_the_item_not_of_the_order(self) -> None:
        accepted = await accept(_order([], ["nir", "red"]), Source((S2, _item())))
        assert accepted.recipe.inputs[0].assets == ["red", "nir"]
        assert accepted.recipe.output.bands == ["nir", "red"]

    async def test_two_results_read_the_union_of_what_they_need(self) -> None:
        accepted = await accept(_order([NDVI, NDWI], ["NDVI", "NDWI"]), Source((S2, _item())))
        assert accepted.recipe.inputs[0].assets == ["red", "nir", "green"]

    async def test_a_result_nobody_asks_for_reads_nothing_for_itself(self) -> None:
        accepted = await accept(_order([NDVI, NDWI], ["NDVI"]), Source((S2, _item())))
        assert accepted.recipe.inputs[0].assets == ["red", "nir"]

    async def test_a_band_of_the_data_in_the_output_is_read_beside_a_result(self) -> None:
        accepted = await accept(_order([NDVI], ["green", "NDVI"]), Source((S2, _item())))
        assert accepted.recipe.inputs[0].assets == ["red", "nir", "green"]

    async def test_a_thumbnail_is_no_band(self) -> None:
        error = await refused(_order([], ["thumbnail"]), Source((S2, _item())))
        assert (error.status_code, error.stage) == (422, "applicable")
        assert "thumbnail" in error.detail

    async def test_the_same_order_is_the_same_recipe_whatever_the_order_of_its_names(self) -> None:
        one = await accept(_order([NDVI, NDWI], ["NDVI", "NDWI"]), Source((S2, _item())))
        two = await accept(_order([NDVI, NDWI], ["NDVI", "NDWI"]), Source((S2, _item())))
        assert cache_key(one.recipe) == cache_key(two.recipe)

    async def test_the_estimate_derives_the_same_assets(self) -> None:
        estimated = await estimate_order(
            json.dumps(_order([MASK, NDVI], ["NDVI"])),
            registry=intake_registry(),
            operators=OPERATORS,
            item_source=Source((S2, _item())),
        )
        assert estimated.recipe.inputs[0].assets == ["red", "nir", "scl"]


def intake_registry():
    from tests.earthx.api.test_intake import INTAKE_REGISTRY

    return INTAKE_REGISTRY


class TestRefusalsByName:
    async def test_a_band_that_nothing_provides_is_named(self) -> None:
        error = await refused(_order([], ["red", "swir99"]), Source((S2, _item())))
        assert (error.status_code, error.stage) == (422, "applicable")
        assert "swir99" in error.detail.split(";")[0] and "red" not in error.detail.split(";")[0]

    async def test_a_band_an_expression_names_and_nothing_provides_is_named(self) -> None:
        error = await refused(_order([band_math("blue - red", "X")], ["X"]), Source((S2, _item())))
        assert (error.status_code, "blue" in error.detail) == (422, True)

    async def test_a_result_used_before_the_step_that_adds_it_is_unknown_there(self) -> None:
        early = band_math("NDVI + red", "Early")
        error = await refused(_order([early, NDVI], ["Early"]), Source((S2, _item())))
        assert "NDVI" in error.detail

    @pytest.mark.parametrize("taken", ["red", "RED", "Green", "swir16", "scl"])
    async def test_a_result_named_like_a_band_of_the_data_is_refused_even_where_nobody_reads_that_band(
        self, taken: str
    ) -> None:
        step = band_math("nir - red", taken)
        error = await refused(_order([step], [taken]), Source((S2, _item())))
        assert (error.status_code, error.stage) == (422, "applicable")
        assert error.detail == f"step 0: {taken} is a band of the data"

    @pytest.mark.parametrize("second", ["NDVI", "ndvi", "Ndvi"])
    async def test_two_results_with_one_name_in_any_case_are_refused(self, second: str) -> None:
        error = await refused(_order([NDVI, band_math("green + red", second)], ["NDVI"]), Source((S2, _item())))
        assert error.detail == f"step 1: {second} is used twice"

    @pytest.mark.parametrize("name", ["in", "where", "1st", "a b", "x" * 33, ""])
    async def test_a_name_an_expression_could_not_use_is_refused_at_the_door(self, name: str) -> None:
        source = Source((S2, _item()))
        error = await refused(_order([band_math("nir - red", name)], [name or "x"]), source)
        assert error.status_code == 422 and source.calls == []

    async def test_an_output_without_bands_is_refused_before_anything_is_fetched(self) -> None:
        source = Source((S2, _item()))
        error = await refused(_order([], []), source)
        assert error.status_code == 422 and source.calls == []

    async def test_assets_in_an_order_for_a_raster_are_refused_before_anything_is_fetched(self) -> None:
        document = _order([], ["red"])
        document["inputs"][0]["assets"] = ["red"]
        source = Source((S2, _item()))
        error = await refused(document, source)
        assert error.status_code == 422 and error.detail.startswith("invalid order") and source.calls == []

    async def test_a_step_that_replaces_the_bands_is_refused_with_its_place(self) -> None:
        old = {"op": "band_math", "op_version": 1, "params": {"expression": "nir - red"}}
        error = await refused(_order([old], ["band_math"]), Source((S2, _item())), operators=intake_operators())
        assert (error.status_code, error.stage) == (422, "applicable")
        assert error.detail.startswith("step 0: 'band_math' version 1 replaces or removes bands")

    async def test_a_crop_names_its_assets_and_has_no_bands(self) -> None:
        crop = order(assets=("red",), steps=[], output={"kind": "crop", "format": "cog", "resolution_factor": 1,
                                                        "extent": "bbox(aoi ∩ footprints)", "mask": "file"})
        accepted = await accept(crop, Source((S2, _item())))
        assert accepted.recipe.inputs[0].assets == ["red"]


def intake_operators():
    from earthx.processing.operators import REGISTRY

    return REGISTRY


class TestAssetsTheItemDoesNotCount:
    async def test_a_band_of_an_asset_the_item_does_not_count_is_matched_to_that_asset(self) -> None:
        item = dem_item("DEM_N47_E009")
        source = Source((DEM, item))
        accepted = await accept(order("cop-dem-glo-30", (("DEM_N47_E009",),), steps=[], bands=["data_2"]), source)
        assert accepted.recipe.inputs[0].assets == ["data"]

    async def test_a_band_that_only_looks_like_one_of_an_asset_the_item_counts_is_not(self) -> None:
        error = await refused(_order([], ["red_2"]), Source((S2, _item())))
        assert "red_2" in error.detail


class TestZarr:
    def _item(self) -> dict[str, Any]:
        item = zarr_item()
        item["assets"]["SR_20m"] = {**item["assets"]["SR_10m"], "eo:bands": [{"name": "b05"}, {"name": "b04"}]}
        return item

    async def test_each_variable_is_an_asset_of_its_own_named_by_the_variable(self) -> None:
        accepted = await accept(order(ZARR_ID, (("ZARR_A",),), bands=["b05"], steps=[]), Source((ZARR, self._item())))
        assert accepted.recipe.inputs[0].assets == ["SR_20m:b05"]

    async def test_a_name_that_two_groups_carry_is_not_chosen_for_the_person(self) -> None:
        error = await refused(order(ZARR_ID, (("ZARR_A",),), bands=["b04"], steps=[]), Source((ZARR, self._item())))
        assert (error.status_code, error.stage) == (422, "applicable")
        assert "b04" in error.detail and "more than one asset" in error.detail

    def test_the_bands_of_a_group_are_listed_by_variable(self) -> None:
        assert band_sources(self._item(), ZARR) == [
            ("SR_10m:b04", ["b04"]),
            ("SR_10m:b08", ["b08"]),
            ("SR_20m:b05", ["b05"]),
            ("SR_20m:b04", ["b04"]),
        ]


class TestVersion1WhileItIsTaken:
    def _v1(self, steps: list[dict[str, Any]], assets: tuple[str, ...]) -> dict[str, Any]:
        document = order(steps=steps, assets=assets)
        document["recipe_version"] = 1
        document["inputs"][0]["assets"] = list(assets)
        del document["output"]["bands"]
        return document

    async def test_an_order_of_version_1_becomes_a_recipe_of_version_2(self) -> None:
        old = [
            {"op": "mask", "op_version": 1, "params": {"source": "scl", "classes": [3, 8]}},
            {"op": "band_math", "op_version": 1, "params": {"expression": "(nir - red) / (nir + red)"}},
        ]
        accepted = await accept(self._v1(old, ("red", "nir", "scl")), Source((S2, _item())), operators=intake_operators())
        recipe = accepted.recipe
        assert recipe.recipe_version == 2 and recipe.output.bands == ["band_math"]
        assert [(step.op, step.op_version) for step in recipe.steps] == [("mask", 2), ("band_math", 2)]
        assert recipe.steps[1].params["name"] == "band_math"
        assert recipe.inputs[0].assets == ["red", "nir", "scl"]

    async def test_without_steps_the_output_is_every_asset_of_the_order(self) -> None:
        accepted = await accept(self._v1([], ("red", "nir")), Source((S2, _item())), operators=intake_operators())
        assert accepted.recipe.output.bands == ["red", "nir"]

    async def test_a_multi_band_asset_of_an_order_of_version_1_is_the_numbered_bands_of_the_item(self) -> None:
        item = _item()
        item["assets"]["visual"] = {**item["assets"]["red"], "raster:bands": [{"data_type": "uint8"}] * 3, "gsd": 10}
        accepted = await accept(self._v1([], ("visual",)), Source((S2, item)), operators=intake_operators())
        assert accepted.recipe.output.bands == ["visual_1", "visual_2", "visual_3"]
        assert accepted.recipe.inputs[0].assets == ["visual"]

    async def test_a_zarr_key_with_variables_is_the_bands_of_those_variables(self) -> None:
        accepted = await accept(self._v1([], ("SR_10m:b04,b08",)) | {"inputs": [{"name": "scene", "dataset": ZARR_ID, "groups": [["ZARR_A"]], "assets": ["SR_10m:b04,b08"]}]}, Source((ZARR, zarr_item())))
        assert accepted.recipe.output.bands == ["b04", "b08"]

    async def test_a_document_that_is_no_order_of_version_1_says_so_without_a_value(self) -> None:
        document = self._v1([], ("red",))
        document["inputs"][0]["assets"] = "red"
        error = await refused(document, Source((S2, _item())))
        assert error.status_code == 422 and "not a document of recipe version 1" in error.detail

    def test_the_last_day_is_up_to_and_including_the_day_named(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(intake, "VERSION_1_ACCEPTED_UNTIL", date(2026, 12, 1))
        assert version_1_accepted(date(2026, 11, 30)) and version_1_accepted(date(2026, 12, 1))
        assert not version_1_accepted(date(2026, 12, 2))

    def test_without_a_day_version_1_is_taken(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(intake, "VERSION_1_ACCEPTED_UNTIL", None)
        assert version_1_accepted(date(2999, 1, 1))

    async def test_after_the_day_an_order_of_version_1_is_refused_with_the_way_out(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(intake, "VERSION_1_ACCEPTED_UNTIL", date(2000, 1, 1))
        source = Source((S2, _item()))
        error = await refused(self._v1([], ("red", "nir")), source)
        assert (error.status_code, error.stage) == (422, "order")
        assert error.detail == "recipe_version 1 is no longer accepted; send version 2"
        assert source.calls == []

    async def test_after_the_day_version_2_is_taken_as_before(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(intake, "VERSION_1_ACCEPTED_UNTIL", date(2000, 1, 1))
        accepted = await accept(_order([], ["red"]), Source((S2, _item())))
        assert accepted.recipe.output.bands == ["red"]

    def test_a_permalink_order_of_version_1_is_checked_as_it_will_be_read(self) -> None:
        parsed = parse_order(json.dumps(self._v1([], ("red", "nir"))), OPERATORS)
        assert parsed.recipe_version == 2 and parsed.output.bands == ["red", "nir"]
        with pytest.raises(OrderRefused, match="invalid order"):
            parse_order(json.dumps({**self._v1([], ("red",)), "extra": 1}), OPERATORS)


class TestTheBandsOfAnItem:
    def test_a_cog_asset_is_a_band_named_like_it_or_one_per_band(self) -> None:
        item = _item()
        item["assets"]["visual"] = {**item["assets"]["red"], "raster:bands": [{"data_type": "uint8"}] * 3}
        listed = dict(band_sources(item, S2))
        assert listed["red"] == ["red"] and listed["visual"] == ["visual_1", "visual_2", "visual_3"]
        assert "thumbnail" not in listed

    def test_an_asset_without_a_media_type_may_carry_bands_and_a_typed_one_must_be_a_geotiff(self) -> None:
        item = _item()
        item["assets"]["metadata"] = {"href": "https://x.invalid/m.xml", "type": "application/xml"}
        listed = dict(band_sources(item, S2))
        assert "red" in listed and "metadata" not in listed

    def test_derive_assets_reads_nothing_but_the_item(self) -> None:
        from earthx.processing.recipe import RecipeRequest

        request = RecipeRequest.model_validate_json(json.dumps(_order([NDVI], ["NDVI"])), strict=True)
        assert derive_assets(request, _item(), S2, OPERATORS) == ["red", "nir"]
        assert SQUARE
