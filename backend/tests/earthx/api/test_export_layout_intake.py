"""NM4-75: an order for an export with a layout, taken in by `api`.

The three forms, the whole scenes (no area named: the union of the footprints), the bands the job needs to name its
files, and what the estimate says is converted. Offline; the items are synthetic.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from shapely.geometry import box
from shapely.geometry import shape as shapely_shape

from earthx.api.intake import OrderRefused
from tests.earthx.api.test_estimate_resampling import ask, put, resampling, sentinel
from tests.earthx.api.test_intake import accept, export_order, refused
from tests.earthx.api.test_intake_mosaic import overpass, scene

pytestmark = pytest.mark.anyio

ASSETS = ("red", "rededge1", "scl", "coastal")


def layout_order(layout: dict[str, Any] | None, *, groups: tuple[tuple[str, ...], ...] = (("S2_A",),), whole: bool = False, assets: tuple[str, ...] = ASSETS) -> dict[str, Any]:
    document = export_order(groups=groups, assets=assets)
    if layout is not None:
        document["output"] = {**document["output"], "layout": layout}
    if whole:
        del document["aoi"]
    return document


def scenes(*ids: str, epsg: dict[str, int] | None = None) -> Any:
    return overpass(*(sentinel(item_id, (epsg or {}).get(item_id, 32632)) for item_id in ids))


class TestTheOrderTheJobIsGiven:
    async def test_whole_scenes_take_the_union_of_their_footprints_as_the_area(self) -> None:
        source = overpass(scene("S2_A", (8.9, 46.9, 9.1, 47.1)), scene("S2_B", (9.05, 46.95, 9.25, 47.15)))
        for item in source.items.values():
            item["assets"].update(sentinel(item["id"])["assets"])
        accepted = await accept(
            layout_order({"form": "per_resolution"}, groups=(("S2_A", "S2_B"),), whole=True), source
        )
        area = shapely_shape(accepted.recipe.aoi.model_dump(mode="json"))
        assert area.equals_exact(box(8.9, 46.9, 9.1, 47.1).union(box(9.05, 46.95, 9.25, 47.15)), 1e-9)
        assert accepted.recipe.output.layout.form == "per_resolution"
        assert accepted.attachments is not None
        properties = json.loads(accepted.attachments.files["aoi.geojson"])["properties"]
        assert "union of the footprints" in properties["earthx:aoi"]

    async def test_its_bands_come_with_it_so_that_the_job_can_name_its_files(self) -> None:
        accepted = await accept(layout_order({"form": "multi_band", "resolution_m": 20.0}), scenes("S2_A"))
        assert accepted.attachments is not None
        by_asset = {band.asset: band for band in accepted.attachments.bands}
        assert list(by_asset) == list(ASSETS)
        assert by_asset["coastal"].resolution_m == 60.0 and by_asset["red"].resolution_m == 10.0
        assert by_asset["scl"].categorical is True and by_asset["red"].categorical is False
        notice = accepted.attachments.files["ATTRIBUTION.txt"]
        assert "bands_20m.tif" in notice and "Resolution: 20 m for all bands" in notice

    async def test_scenes_in_two_coordinate_systems_leave_a_note_for_bands_txt(self) -> None:
        source = scenes("S2_A", "S2_B", epsg={"S2_B": 32633})
        accepted = await accept(layout_order({"form": "per_band"}, groups=(("S2_A", "S2_B"),)), source)
        assert accepted.attachments is not None and len(accepted.attachments.notes) == 1
        assert "EPSG:32632, EPSG:32633" in accepted.attachments.notes[0]
        same = await accept(layout_order({"form": "per_band"}, groups=(("S2_A", "S2_B"),)), scenes("S2_A", "S2_B"))
        assert same.attachments is not None and same.attachments.notes == ()  # Gegenprobe

    async def test_without_a_layout_the_crop_is_the_one_of_before(self) -> None:
        accepted = await accept(layout_order(None), scenes("S2_A"))
        assert accepted.recipe.output.layout is None
        assert accepted.attachments is not None and accepted.attachments.bands == ()
        assert "layout" not in accepted.recipe.output.model_dump(mode="json")


class TestWhatIsRefused:
    async def test_a_crop_without_area_needs_a_layout_to_mean_whole_scenes(self) -> None:
        error = await refused(layout_order(None, whole=True), scenes("S2_A"))
        assert error.status_code == 422 and "needs an AOI" in str(error)

    @pytest.mark.parametrize(
        "layout",
        [
            {"form": "multi_band"},
            {"form": "per_band", "resolution_m": 20.0},
            {"form": "multi_band", "resolution_m": 0},
            {"form": "multi_band", "resolution_m": 5000.0},
            {"form": "everything"},
        ],
    )
    async def test_a_layout_that_is_not_one_is_refused_before_anything_is_fetched(self, layout: dict[str, Any]) -> None:
        with pytest.raises(OrderRefused) as error:
            await accept(layout_order(layout), scenes("S2_A"))
        assert error.value.status_code in (400, 422)

    async def test_an_asset_without_a_pixel_size_cannot_be_brought_to_a_common_resolution(self) -> None:
        source = overpass(sentinel("S2_A", rededge1=None))
        error = await refused(layout_order({"form": "multi_band", "resolution_m": 20.0}), source)
        assert error.status_code == 422


class TestAssetsOfSeveralBands:
    async def test_they_cannot_be_stacked_and_the_order_is_refused_before_a_job_is_placed(self) -> None:
        source = overpass(scene("S2_A"))
        source.items[next(iter(source.items))]["assets"]["visual"] = {
            "href": "https://e84-earth-search-sentinel-data.s3.us-west-2.amazonaws.com/x/TCI.tif",
            "type": "image/tiff; application=geotiff; profile=cloud-optimized",
            "gsd": 10,
            "raster:bands": [{"data_type": "uint8", "nodata": 0}] * 3,
        }
        for form in ("per_resolution", "multi_band"):
            layout = {"form": form, **({"resolution_m": 10.0} if form == "multi_band" else {})}
            error = await refused(layout_order(layout, assets=("visual",)), source)
            assert error.status_code == 422 and "several bands" in str(error), form
        accepted = await accept(layout_order({"form": "per_band"}, assets=("visual",)), source)  # Gegenprobe
        assert accepted.recipe.output.layout.form == "per_band"


class TestWhatTheEstimateSays:
    async def test_the_bands_of_another_pixel_size_than_the_common_one_are_named(self, rig: Any) -> None:
        put(rig, sentinel())
        found = await resampling(rig, layout_order({"form": "multi_band", "resolution_m": 20.0}))
        assert found["grid"] == {"resolution": 20.0, "crs": "EPSG:4326"}
        assert [(b["band"], b["resolution"]) for b in found["bands"]] == [("red", 10.0), ("coastal", 60.0)]
        assert found["method"] == "mixed"  # red becomes coarser (averaged), coastal finer (repeated)

    async def test_the_method_follows_the_direction_of_the_conversion(self, rig: Any) -> None:
        put(rig, sentinel())
        coarse = await resampling(rig, layout_order({"form": "multi_band", "resolution_m": 60.0}))
        fine = await resampling(rig, layout_order({"form": "multi_band", "resolution_m": 10.0}))
        assert (coarse["method"], fine["method"]) == ("average", "nearest")

    async def test_one_file_per_band_and_per_resolution_convert_no_band(self, rig: Any) -> None:
        put(rig, sentinel())
        for form in ("per_band", "per_resolution"):
            assert await resampling(rig, layout_order({"form": form})) is None

    async def test_scenes_in_another_zone_are_named_in_every_form(self, rig: Any) -> None:
        put(rig, sentinel("S2_A"), sentinel("S2_B"), sentinel("S2_C", epsg=32633))
        for layout in ({"form": "per_band"}, {"form": "per_resolution"}, {"form": "multi_band", "resolution_m": 10.0}):
            found = await resampling(rig, layout_order(layout, groups=(("S2_A", "S2_B", "S2_C"),)))
            assert found["scenes"] == {"count": 1, "of": 3, "crs": "EPSG:32632"}, layout

    async def test_the_size_of_a_multi_band_file_is_that_of_one_grid(self, rig: Any) -> None:
        put(rig, sentinel())
        sizes = {}
        for name, layout in {
            "per_band": {"form": "per_band"},
            "coarse": {"form": "multi_band", "resolution_m": 60.0},
            "fine": {"form": "multi_band", "resolution_m": 10.0},
        }.items():
            response = await ask(rig, layout_order(layout))
            assert response.status_code == 200, response.text
            sizes[name] = response.json()["estimate"]["size"]
        assert sizes["coarse"] < sizes["per_band"] < sizes["fine"]
