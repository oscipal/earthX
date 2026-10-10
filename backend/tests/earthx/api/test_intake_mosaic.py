"""Order intake for the mosaic of one overpass (M4-12a): whole scenes, the overpass, the order of the list.

The items are the synthetic ones of ``test_intake``, given the properties of an overpass. Nothing
here is fetched: the item source is a function.
"""

from __future__ import annotations

import json
from dataclasses import replace
from typing import Any

import pytest
from shapely.geometry import box
from shapely.geometry import shape as shapely_shape

from earthx.api.intake import MAX_ORDER_ITEMS, estimate_order
from earthx.catalog.registry import DatasetRegistry
from earthx.processing.plan import estimate
from earthx.processing.recipe import cache_key, recipe_hash
from tests.earthx.api.test_intake import (
    DEM,
    EOPF,
    NEAR,
    OPERATORS,
    S2,
    Source,
    accept,
    dem_item,
    eopf_item,
    order,
    refused,
    s2_item,
)

pytestmark = pytest.mark.anyio

DAY = "2026-06-01T10:00:00Z"
TAKE = "GS2B_20260601T100031_000000_N05.11"


def scene(
    item_id: str,
    bbox: tuple[float, float, float, float] = NEAR,
    *,
    epsg: int = 32632,
    take: str = TAKE,
    day: str = DAY,
) -> dict[str, Any]:
    """A Sentinel-2 item of an overpass: the day and the datatake are its key (``results_group_by``)."""
    item = s2_item(item_id, bbox)
    item["properties"].update({"datetime": day, "s2:datatake_id": take, "proj:epsg": epsg})
    return item


def overpass(*items: dict[str, Any]) -> Source:
    return Source(*((S2, item) for item in items))


def whole(*ids: str, **override: Any) -> dict[str, Any]:
    """An order for the whole scenes: one group, no AOI, no steps."""
    document = order(groups=(tuple(ids),), steps=[], **override)
    del document["aoi"]
    return document


class TestWholeScenes:
    async def test_the_aoi_is_the_union_of_the_footprints(self) -> None:
        source = overpass(scene("S2_A", (8.9, 46.9, 9.1, 47.1)), scene("S2_B", (9.05, 46.95, 9.25, 47.15)))
        accepted = await accept(whole("S2_A", "S2_B"), source)
        aoi = shapely_shape(accepted.recipe.aoi.model_dump(mode="json"))
        expected = box(8.9, 46.9, 9.1, 47.1).union(box(9.05, 46.95, 9.25, 47.15))
        assert aoi.equals(expected)
        assert accepted.recipe.recipe_version == 1  # the recipe has an AOI like any other
        assert accepted.skipped_items == ()

    async def test_one_whole_scene_is_its_footprint(self) -> None:
        accepted = await accept(whole("S2_A"), overpass(scene("S2_A")))
        assert shapely_shape(accepted.recipe.aoi.model_dump(mode="json")).equals(box(*NEAR))

    async def test_an_item_without_a_footprint_counts_with_its_bbox(self) -> None:
        item = scene("S2_A")
        item["geometry"] = None
        accepted = await accept(whole("S2_A"), overpass(item))
        assert shapely_shape(accepted.recipe.aoi.model_dump(mode="json")).equals(box(*NEAR))

    async def test_an_item_with_neither_is_the_sources_mistake(self) -> None:
        item = scene("S2_A")
        item["geometry"] = None
        del item["bbox"]
        error = await refused(whole("S2_A"), overpass(item))
        assert error.status_code == 502 and error.stage == "items"

    async def test_scenes_on_both_sides_of_the_antimeridian_are_refused(self) -> None:
        source = overpass(scene("S2_A", (179.5, 10.0, 179.9, 10.2)), scene("S2_B", (-179.9, 10.0, -179.5, 10.2)))
        error = await refused(whole("S2_A", "S2_B"), source)
        assert error.status_code == 422 and "antimeridian" in error.detail

    async def test_an_export_still_needs_its_area(self) -> None:
        document = whole("S2_A", output={"kind": "crop", "format": "cog", "resolution_factor": 1,
                                         "extent": "bbox(aoi ∩ footprints)", "mask": "file"})  # fmt: skip
        error = await refused(document, overpass(scene("S2_A")))
        assert error.status_code == 422 and "needs an AOI" in error.detail

    async def test_the_estimate_takes_such_an_order_too(self) -> None:
        source = overpass(scene("S2_A"), scene("S2_B", (9.0, 46.9, 9.2, 47.1)))
        estimated = await estimate_order(
            json.dumps(whole("S2_A", "S2_B")), registry=_REGISTRY, operators=OPERATORS, item_source=source
        )
        assert [len(group) for group in estimated.recipe.inputs[0].groups] == [2]
        assert estimated.recipe.recipe_id is None


_REGISTRY = DatasetRegistry((S2, EOPF, DEM))


class TestTheOrderOfTheList:
    async def test_the_same_overpass_gives_the_same_recipe_however_it_was_asked_for(self) -> None:
        source = overpass(scene("S2_A"), scene("S2_B", (9.0, 46.9, 9.2, 47.1)), scene("S2_C", (9.1, 46.9, 9.3, 47.1)))
        forward = await accept(whole("S2_A", "S2_B", "S2_C"), source)
        backward = await accept(whole("S2_C", "S2_A", "S2_B"), source)
        assert forward.recipe.inputs[0].groups == backward.recipe.inputs[0].groups == [["S2_A", "S2_B", "S2_C"]]
        assert recipe_hash(forward.recipe) == recipe_hash(backward.recipe)
        assert cache_key(forward.recipe) == cache_key(backward.recipe) is not None

    async def test_the_scenes_in_the_target_crs_come_first_each_part_by_id(self) -> None:
        source = overpass(
            scene("S2_3", epsg=32633), scene("S2_9", epsg=32632), scene("S2_1", epsg=32632), scene("S2_2", epsg=32633),
            scene("S2_5", epsg=32632),
        )  # fmt: skip
        accepted = await accept(whole("S2_3", "S2_9", "S2_1", "S2_2", "S2_5"), source)
        # three scenes in zone 32 are the target; the two of zone 33 follow, each part by id
        assert accepted.recipe.inputs[0].groups == [["S2_1", "S2_5", "S2_9", "S2_2", "S2_3"]]
        assert [entry.asset.crs for entry in accepted.recipe.inputs[0].resolved[::2]] == ["EPSG:32632"] * 3 + [
            "EPSG:32633"
        ] * 2

    @pytest.mark.parametrize("named", [("S2_N", "S2_Z"), ("S2_Z", "S2_N")])
    async def test_a_tie_goes_to_the_smaller_epsg_number_whatever_the_order(self, named: tuple[str, ...]) -> None:
        source = overpass(scene("S2_N", epsg=32633), scene("S2_Z", epsg=32632))
        accepted = await accept(whole(*named), source)
        assert accepted.recipe.inputs[0].groups == [["S2_Z", "S2_N"]]

    async def test_one_scene_keeps_its_group_untouched(self) -> None:
        accepted = await accept(whole("S2_A"), overpass(scene("S2_A")))
        assert accepted.recipe.inputs[0].groups == [["S2_A"]]

    async def test_an_order_with_an_aoi_is_sorted_the_same_way(self) -> None:
        source = overpass(scene("S2_B", epsg=32633), scene("S2_A", epsg=32632))
        accepted = await accept(order(groups=(("S2_B", "S2_A"),), steps=[]), source)
        assert accepted.recipe.inputs[0].groups == [["S2_A", "S2_B"]]

    async def test_scenes_the_aoi_does_not_touch_drop_out_before_the_order_is_made(self) -> None:
        source = overpass(scene("S2_FAR", (20.0, 10.0, 20.2, 10.2)), scene("S2_B"), scene("S2_A"))
        accepted = await accept(order(groups=(("S2_FAR", "S2_B", "S2_A"),), steps=[]), source)
        assert accepted.recipe.inputs[0].groups == [["S2_A", "S2_B"]]
        assert accepted.skipped_items == ("S2_FAR",)


class TestOneOverpass:
    async def test_a_scene_of_another_datatake_is_named(self) -> None:
        source = overpass(scene("S2_A"), scene("S2_B"), scene("S2_C", take="GS2A_other"))
        error = await refused(whole("S2_A", "S2_B", "S2_C"), source)
        assert error.status_code == 422 and error.stage == "items"
        assert "S2_C" in error.detail and "S2_B" not in error.detail

    async def test_a_scene_of_another_day_is_named(self) -> None:
        source = overpass(scene("S2_A"), scene("S2_B", day="2026-06-02T10:00:00Z"))
        error = await refused(whole("S2_A", "S2_B"), source)
        assert error.status_code == 422 and "S2_B" in error.detail

    async def test_the_time_of_day_is_no_part_of_the_overpass(self) -> None:
        source = overpass(scene("S2_A"), scene("S2_B", day="2026-06-01T10:00:19Z"))
        assert (await accept(whole("S2_A", "S2_B"), source)).recipe.inputs[0].groups == [["S2_A", "S2_B"]]

    async def test_an_item_without_the_key_is_the_sources_mistake(self) -> None:
        lacking = scene("S2_B")
        del lacking["properties"]["s2:datatake_id"]
        error = await refused(whole("S2_A", "S2_B"), overpass(scene("S2_A"), lacking))
        assert error.status_code == 502 and "s2:datatake_id" in error.detail

    async def test_the_names_are_ids_never_coordinates(self) -> None:
        source = overpass(scene("S2_A"), scene("S2_B", take="GS2A_other"))
        error = await refused(whole("S2_A", "S2_B"), source)
        assert "46." not in error.detail and "9.0" not in error.detail

    async def test_two_groups_are_two_overpasses_and_no_raster_job(self) -> None:
        document = order(groups=(("S2_A",), ("S2_B",)), steps=[])
        error = await refused(document, overpass(scene("S2_A"), scene("S2_B")))
        assert error.status_code == 422 and "one group" in error.detail

    async def test_a_dataset_that_does_not_allow_reprojection_does_not_mosaic(self) -> None:
        no_warp = replace(S2, capabilities=replace(S2.capabilities, reprojection=False))
        error = await refused(
            whole("S2_A", "S2_B"), overpass(scene("S2_A"), scene("S2_B")), registry=DatasetRegistry((no_warp,))
        )
        assert error.status_code == 422 and error.stage == "applicable" and "reprojection" in error.detail

    async def test_one_scene_does_not_need_the_flag(self) -> None:
        no_warp = replace(S2, capabilities=replace(S2.capabilities, reprojection=False))
        accepted = await accept(whole("S2_A"), overpass(scene("S2_A")), registry=DatasetRegistry((no_warp,)))
        assert accepted.recipe.inputs[0].groups == [["S2_A"]]

    async def test_the_cap_of_items_stays(self) -> None:
        ids = [f"S2_{i:02d}" for i in range(MAX_ORDER_ITEMS + 1)]
        error = await refused(whole(*ids), overpass(*(scene(i) for i in ids)))
        assert error.status_code == 413

    async def test_exactly_at_the_cap_of_items_is_fine(self) -> None:
        ids = [f"S2_{i:02d}" for i in range(MAX_ORDER_ITEMS)]
        accepted = await accept(whole(*ids), overpass(*(scene(i) for i in ids)))
        assert len(accepted.recipe.inputs[0].groups[0]) == MAX_ORDER_ITEMS


class TestOtherDatasets:
    async def test_dem_tiles_are_one_overpass_and_a_mosaic(self) -> None:
        source = Source((DEM, dem_item("DEM_N47_E010", (10.0, 47.0, 11.0, 48.0))), (DEM, dem_item("DEM_N47_E009")))
        document = order("cop-dem-glo-30", (("DEM_N47_E010", "DEM_N47_E009"),), ("data",), steps=[])
        del document["aoi"]
        accepted = await accept(document, source)
        assert accepted.recipe.inputs[0].groups == [["DEM_N47_E009", "DEM_N47_E010"]]
        assert shapely_shape(accepted.recipe.aoi.model_dump(mode="json")).area > 0

    async def test_a_zarr_mosaic_in_one_crs_is_accepted(self) -> None:
        def zarr_scene(item_id: str, **crs: str) -> dict[str, Any]:
            item = eopf_item(item_id)
            item["properties"]["eopf:datatake_id"] = TAKE
            item["properties"]["proj:code"] = crs.get("code", "EPSG:32632")
            return item

        source = Source((EOPF, zarr_scene("EOPF_A")), (EOPF, zarr_scene("EOPF_B")))
        document = order("sentinel-2-l2a-zarr3", (("EOPF_B", "EOPF_A"),), ("SR_10m:b04",), steps=[])
        del document["aoi"]
        accepted = await accept(document, source)
        assert accepted.recipe.inputs[0].groups == [["EOPF_A", "EOPF_B"]]

    async def test_a_zarr_mosaic_over_two_crs_is_refused_before_any_work(self) -> None:
        def zarr_scene(item_id: str, code: str) -> dict[str, Any]:
            item = eopf_item(item_id)
            item["properties"]["eopf:datatake_id"] = TAKE
            item["properties"]["proj:code"] = code
            return item

        source = Source((EOPF, zarr_scene("EOPF_A", "EPSG:32632")), (EOPF, zarr_scene("EOPF_B", "EPSG:32633")))
        document = order("sentinel-2-l2a-zarr3", (("EOPF_A", "EOPF_B"),), ("SR_10m:b04",), steps=[])
        error = await refused(document, source)
        assert error.status_code == 422 and "one CRS" in error.detail


class TestTheCapOfAJob:
    async def test_a_mosaic_over_the_cap_is_a_413_before_the_queue(self) -> None:
        source = overpass(scene("S2_A", (0.0, 40.0, 10.0, 50.0)), scene("S2_B", (10.0, 40.0, 20.0, 50.0)))
        error = await refused(whole("S2_A", "S2_B"), source)
        assert error.status_code == 413 and error.stage == "size"
        assert "more than the 5000 MB" in error.detail

    async def test_the_cap_holds_to_the_byte(self, monkeypatch: pytest.MonkeyPatch) -> None:
        source = overpass(scene("S2_A"), scene("S2_B", (9.0, 46.9, 9.2, 47.1)))
        first = await accept(whole("S2_A", "S2_B"), source)
        cost = estimate(first.recipe, OPERATORS)
        total = cost.output_bytes + cost.output_pixels  # the raster and its mask
        monkeypatch.setattr("earthx.processing.plan.MAX_JOB_BYTES", total)
        await accept(whole("S2_A", "S2_B"), source)
        monkeypatch.setattr("earthx.processing.plan.MAX_JOB_BYTES", total - 1)
        assert (await refused(whole("S2_A", "S2_B"), source)).status_code == 413

    async def test_one_scene_is_judged_by_the_same_cap(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("earthx.processing.plan.MAX_JOB_BYTES", 1_000)
        error = await refused(order(), overpass(scene("S2_A")))
        assert error.status_code == 413

    async def test_the_estimate_counts_the_assets_of_a_mosaic_once(self) -> None:
        source = overpass(scene("S2_A"), scene("S2_B"))
        one = await accept(whole("S2_A"), overpass(scene("S2_A")))
        two = await accept(whole("S2_A", "S2_B"), source)
        assert estimate(two.recipe, OPERATORS).input_bytes == estimate(one.recipe, OPERATORS).input_bytes
        assert estimate(two.recipe, OPERATORS).assets == 2 * estimate(one.recipe, OPERATORS).assets
