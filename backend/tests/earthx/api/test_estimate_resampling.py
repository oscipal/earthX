"""The estimate says what the job converts onto a common grid (NM4-65, adr/0014 Nachtrag NM4-65).

``resampling`` of the estimate is read off the items alone (``ResolvedInput.gsd``, the CRS of the asset), by the rule
of the job: the grid of the finest asset (``source.common_grid``), a band counts where it reaches the result
(``core._source_meta``, backlog 51), scenes of another CRS go to the CRS most scenes share (``mosaic_order``). Same
rig as the other estimate tests; everything is synthetic and offline, and no asset is ever asked for.
"""

from __future__ import annotations

import copy
from typing import Any

import pytest

from earthx.api.processing_route import EstimateDocument, Resampling
from tests.catalog.synthetic_zarr import registry_with_zarr
from tests.earthx.api.conftest import Rig
from tests.earthx.api.test_intake import (
    CROP,
    ZARR_HOST,
    ZARR_ID,
    band_math,
    order,
    zarr_item,
)
from tests.earthx.api.test_intake_mosaic import scene
from tests.earthx.api.test_processing_estimate import ESTIMATE, ask
from tests.earthx.api.test_processing_route import client_for, envelope, replace_api

pytestmark = pytest.mark.anyio

MASK = {"op": "mask", "op_version": 2, "params": {"source": "scl", "classes": [3, 8, 9, 10]}}
REPROJECT = {"op": "reproject", "op_version": 4, "params": {"crs": "EPSG:3035", "resolution": 100.0, "resampling": "bilinear"}}
S2 = "sentinel-2-c1-l2a"
RESOLUTIONS = {"red": 10, "nir": 10, "rededge1": 20, "scl": 20, "coastal": 60}


def sentinel(item_id: str = "S2_A", epsg: int | None = 32632, **resolutions: int | None) -> dict[str, Any]:
    """A Sentinel-2 item of an overpass with the assets of its three pixel sizes (10, 20 and 60 m).

    ``resolutions`` overrides the pixel size of an asset by key; ``None`` removes what the item says of it.
    """
    item = scene(item_id, epsg=epsg or 32632)
    if epsg is None:
        del item["properties"]["proj:epsg"]
    template = item["assets"]["red"]
    for key, metres in {**RESOLUTIONS, **resolutions}.items():
        asset = copy.deepcopy(template)
        asset["href"] = template["href"].replace("B04", key)
        asset["file:checksum"] = f"1220{item_id}{key}"
        if metres is None:
            asset["raster:bands"][0].pop("spatial_resolution")
        else:
            asset["raster:bands"][0]["spatial_resolution"] = metres
        item["assets"][key] = asset
    return item


def put(rig: Rig, *items: dict[str, Any]) -> None:
    rig.source.items = {(S2, item["id"]): item for item in items}


def raster(*bands: str, steps: list[dict[str, Any]] | None = None, scenes: tuple[str, ...] = ("S2_A",)) -> dict[str, Any]:
    return order(groups=(scenes,), assets=bands, steps=steps or [])


async def resampling(rig: Rig, document: dict[str, Any]) -> Any:
    response = await ask(rig, document)
    assert response.status_code == 200, response.text
    body = response.json()
    assert "resampling" in body, "the member is always there, null where nothing is converted"
    return body["resampling"]


class TestNothingIsConverted:
    async def test_assets_of_one_pixel_size_give_null(self, rig: Rig) -> None:
        put(rig, sentinel())
        assert await resampling(rig, raster("red", "nir")) is None

    async def test_a_classification_layer_that_only_masks_gives_null(self, rig: Rig) -> None:
        """Backlog 51: `scl` (20 m) is read onto the 10 m grid, but it is not in the result, so nothing is said."""
        put(rig, sentinel())
        assert await resampling(rig, raster("red", "nir", steps=[MASK])) is None

    async def test_an_index_of_bands_on_the_grid_masked_by_the_layer_gives_null(self, rig: Rig) -> None:
        put(rig, sentinel())
        steps = [MASK, band_math("(nir - red) / (nir + red)", "ndvi")]
        assert await resampling(rig, raster("ndvi", steps=steps)) is None

    async def test_a_reproject_step_describes_itself_and_gives_null(self, rig: Rig) -> None:
        """The person chose target and method: that is no silent conversion, whatever the bands and scenes are."""
        put(rig, sentinel("S2_A"), sentinel("S2_B", epsg=32633))
        document = raster("red", "rededge1", steps=[REPROJECT], scenes=("S2_A", "S2_B"))
        assert await resampling(rig, document) is None

    async def test_an_export_reads_the_native_values_and_gives_null(self, rig: Rig) -> None:
        put(rig, sentinel())
        document = order(groups=(("S2_A",),), assets=("red", "rededge1"), steps=[], output=CROP)
        assert await resampling(rig, document) is None


class TestBandsOfAnotherPixelSize:
    async def test_the_bands_of_20_and_60_m_name_themselves_with_their_pixel_size(self, rig: Rig) -> None:
        put(rig, sentinel())
        found = await resampling(rig, raster("red", "rededge1", "coastal"))
        assert found == {
            "grid": {"resolution": 10.0, "crs": "EPSG:32632"},
            "method": "nearest",
            "bands": [
                {"band": "rededge1", "resolution": 20.0, "crs": "EPSG:32632"},
                {"band": "coastal", "resolution": 60.0, "crs": "EPSG:32632"},
            ],
            "scenes": None,
        }

    async def test_the_grid_is_that_of_the_finest_asset_even_if_it_is_not_the_first(self, rig: Rig) -> None:
        put(rig, sentinel())
        found = await resampling(rig, raster("coastal", "rededge1", "red"))
        assert found["grid"]["resolution"] == 10.0
        assert {band["band"] for band in found["bands"]} == {"rededge1", "coastal"}

    async def test_only_coarse_bands_still_lie_on_the_grid_of_the_finest_of_them(self, rig: Rig) -> None:
        put(rig, sentinel())
        found = await resampling(rig, raster("rededge1", "coastal"))
        assert found["grid"]["resolution"] == 20.0
        assert [band["band"] for band in found["bands"]] == ["coastal"]

    async def test_the_layer_that_masks_and_one_band_of_20_m_name_only_the_band(self, rig: Rig) -> None:
        put(rig, sentinel())
        found = await resampling(rig, raster("red", "rededge1", steps=[MASK]))
        assert [band["band"] for band in found["bands"]] == ["rededge1"]

    async def test_a_layer_the_person_asks_for_as_a_band_is_a_band_of_the_result(self, rig: Rig) -> None:
        """The job marks such a result resampled (the layer is in it), so the estimate names the layer."""
        put(rig, sentinel())
        found = await resampling(rig, raster("red", "scl"))
        assert [band["band"] for band in found["bands"]] == ["scl"]

    async def test_a_derived_band_names_the_bands_of_the_data_it_is_made_of(self, rig: Rig) -> None:
        put(rig, sentinel())
        steps = [band_math("(rededge1 - red) / (rededge1 + red)", "index")]
        found = await resampling(rig, raster("index", steps=steps))
        assert [band["band"] for band in found["bands"]] == ["rededge1"]

    async def test_a_band_that_is_computed_and_dropped_is_not_named(self, rig: Rig) -> None:
        put(rig, sentinel())
        steps = [band_math("rededge1 + red", "unused")]
        assert await resampling(rig, raster("red", steps=steps)) is None

    async def test_pixel_sizes_that_differ_in_the_last_digits_are_one_grid(self, rig: Rig) -> None:
        put(rig, sentinel(rededge1=None))
        item = rig.source.items[(S2, "S2_A")]
        item["assets"]["rededge1"]["raster:bands"][0]["spatial_resolution"] = 10.000001
        assert await resampling(rig, raster("red", "rededge1")) is None


class TestScenesInAnotherZone:
    async def test_scenes_in_the_other_zone_are_counted_of_all_scenes(self, rig: Rig) -> None:
        put(rig, sentinel("S2_A"), sentinel("S2_B"), sentinel("S2_C", epsg=32633))
        found = await resampling(rig, raster("red", "nir", scenes=("S2_A", "S2_B", "S2_C")))
        assert found == {
            "grid": {"resolution": 10.0, "crs": "EPSG:32632"},
            "method": "nearest",
            "bands": [],
            "scenes": {"count": 1, "of": 3, "crs": "EPSG:32632"},
        }

    async def test_the_zone_most_scenes_lie_in_is_the_grid_whatever_the_order_of_the_names(self, rig: Rig) -> None:
        put(rig, sentinel("S2_A", epsg=32633), sentinel("S2_B"), sentinel("S2_C"), sentinel("S2_D", epsg=32633), sentinel("S2_E"))
        found = await resampling(rig, raster("red", scenes=("S2_A", "S2_B", "S2_C", "S2_D", "S2_E")))
        assert found["scenes"] == {"count": 2, "of": 5, "crs": "EPSG:32632"}
        assert found["grid"]["crs"] == "EPSG:32632"

    async def test_a_tie_goes_to_the_smaller_epsg_number_as_the_mosaic_does(self, rig: Rig) -> None:
        put(rig, sentinel("S2_A", epsg=32633), sentinel("S2_B", epsg=32632))
        found = await resampling(rig, raster("red", scenes=("S2_A", "S2_B")))
        assert found["scenes"] == {"count": 1, "of": 2, "crs": "EPSG:32632"}

    async def test_scenes_in_one_zone_say_nothing(self, rig: Rig) -> None:
        put(rig, sentinel("S2_A"), sentinel("S2_B"))
        assert await resampling(rig, raster("red", "nir", scenes=("S2_A", "S2_B"))) is None

    async def test_zones_and_pixel_sizes_together_name_both(self, rig: Rig) -> None:
        put(rig, sentinel("S2_A"), sentinel("S2_B", epsg=32633))
        found = await resampling(rig, raster("red", "rededge1", steps=[MASK], scenes=("S2_A", "S2_B")))
        assert found["scenes"] == {"count": 1, "of": 2, "crs": "EPSG:32632"}
        assert found["bands"] == [{"band": "rededge1", "resolution": 20.0, "crs": "EPSG:32632"}]

    async def test_the_scenes_of_a_zone_are_judged_by_the_asset_of_the_finest_grid(self, rig: Rig) -> None:
        """Both scenes are 10 m for `red`; the count is of the scenes the grid's asset has, not of all assets."""
        put(rig, sentinel("S2_A"), sentinel("S2_B", epsg=32633))
        found = await resampling(rig, raster("rededge1", "red", scenes=("S2_A", "S2_B")))
        assert found["scenes"]["of"] == 2


async def zarr_resampling(rig: Rig, document: dict[str, Any]) -> Any:
    """As :func:`resampling`, on an API whose registry holds the synthetic Zarr dataset."""
    api = replace_api(rig.api, registry=registry_with_zarr())
    async with client_for(api) as client:
        response = await client.post(ESTIMATE, json=envelope(document))
    assert response.status_code == 200, response.text
    return response.json()["resampling"]


class TestAZarrStore:
    @staticmethod
    def store(rig: Rig, epsg: str | None = "EPSG:32632") -> None:
        item = zarr_item()
        item["assets"]["SR_20m"] = {
            "href": f"https://{ZARR_HOST}/zarr/ZARR_A/measurements/r20m",
            "gsd": 20,
            "raster:bands": [{"nodata": 0, "data_type": "uint16", "spatial_resolution": 20}],
            "eo:bands": [{"name": "b05"}, {"name": "b06"}],
        }
        if epsg is None:
            del item["properties"]["proj:code"]
        rig.source.items = {(ZARR_ID, "ZARR_A"): item}

    async def test_a_variable_of_a_coarser_group_is_named_by_its_variable(self, rig: Rig) -> None:
        self.store(rig)
        document = order(ZARR_ID, (("ZARR_A",),), bands=["b04", "b08", "b05"], steps=[])
        found = await zarr_resampling(rig, document)
        assert found == {
            "grid": {"resolution": 10.0, "crs": "EPSG:32632"},
            "method": "nearest",
            "bands": [{"band": "b05", "resolution": 20.0, "crs": "EPSG:32632"}],
            "scenes": None,
        }

    async def test_the_variables_of_one_group_give_null(self, rig: Rig) -> None:
        self.store(rig)
        assert await zarr_resampling(rig, order(ZARR_ID, (("ZARR_A",),), bands=["b04", "b08"], steps=[])) is None

    async def test_a_store_without_a_crs_names_the_band_and_no_crs(self, rig: Rig) -> None:
        self.store(rig, None)
        found = await zarr_resampling(rig, order(ZARR_ID, (("ZARR_A",),), bands=["b04", "b05"], steps=[]))
        assert found["grid"] == {"resolution": 10.0, "crs": None}
        assert found["bands"] == [{"band": "b05", "resolution": 20.0, "crs": None}]


class TestAnItemWithoutACrs:
    async def test_the_bands_are_named_the_crs_is_null_and_nothing_fails(self, rig: Rig) -> None:
        put(rig, sentinel(epsg=None))
        found = await resampling(rig, raster("red", "rededge1"))
        assert found == {
            "grid": {"resolution": 10.0, "crs": None},
            "method": "nearest",
            "bands": [{"band": "rededge1", "resolution": 20.0, "crs": None}],
            "scenes": None,
        }

    async def test_scenes_without_a_crs_are_not_counted_as_another_zone(self, rig: Rig) -> None:
        put(rig, sentinel("S2_A", epsg=None), sentinel("S2_B", epsg=None))
        assert await resampling(rig, raster("red", "nir", scenes=("S2_A", "S2_B"))) is None

    async def test_one_scene_without_a_crs_among_scenes_in_a_zone_is_not_counted(self, rig: Rig) -> None:
        put(rig, sentinel("S2_A"), sentinel("S2_B", epsg=None), sentinel("S2_C"))
        assert await resampling(rig, raster("red", "nir", scenes=("S2_A", "S2_B", "S2_C"))) is None


class TestWhatItAsksFor:
    async def test_an_asset_without_a_pixel_size_is_refused_as_before(self, rig: Rig) -> None:
        put(rig, sentinel(rededge1=None))
        item = rig.source.items[(S2, "S2_A")]
        item["properties"].pop("gsd", None)
        response = await ask(rig, raster("red", "rededge1"))
        assert response.status_code == 422
        assert response.json()["type"].endswith(":scope")

    async def test_no_asset_is_asked_for_and_no_file_is_opened(self, rig: Rig, monkeypatch: pytest.MonkeyPatch) -> None:
        def forbidden(*args: object, **kwargs: object) -> None:
            raise AssertionError("the estimate opened an asset")

        monkeypatch.setattr("rasterio.open", forbidden)
        monkeypatch.setattr("earthx.access.resolve.open_asset_ref", forbidden)
        put(rig, sentinel("S2_A"), sentinel("S2_B", epsg=32633))
        found = await resampling(rig, raster("red", "rededge1", scenes=("S2_A", "S2_B")))
        assert found is not None and found["scenes"] is not None and found["bands"]
        assert rig.heads.requests == []
        assert {dataset for dataset, _ in rig.source.calls} == {S2}

    async def test_the_answer_names_no_address_no_item_and_no_checksum(self, rig: Rig) -> None:
        put(rig, sentinel("S2_A"), sentinel("S2_B", epsg=32633))
        response = await ask(rig, raster("red", "rededge1", scenes=("S2_A", "S2_B")))
        text = response.text
        assert "S2_A" not in text and "S2_B" not in text and "https://" not in text and "1220" not in text

    async def test_the_rest_of_the_answer_is_as_it_was(self, rig: Rig) -> None:
        put(rig, sentinel())
        body = (await ask(rig, raster("red", "rededge1"))).json()
        assert set(body) == {"estimate", "skippedItems", "resampling"}
        assert set(body["estimate"]) == {"size", "duration", "outputPixels", "inputPixels", "inputBytes", "assets", "units"}

    async def test_asking_twice_gives_the_same_answer(self, rig: Rig) -> None:
        put(rig, sentinel("S2_A"), sentinel("S2_B", epsg=32633))
        document = raster("red", "rededge1", "coastal", scenes=("S2_B", "S2_A"))
        first = await ask(rig, document)
        assert (await ask(rig, document)).json() == first.json()

    async def test_the_whole_answer_for_a_mosaic_over_two_zones_with_a_20_m_band(self, rig: Rig) -> None:
        put(rig, sentinel("S2_A"), sentinel("S2_B"), sentinel("S2_C", epsg=32633))
        document = raster("red", "rededge1", steps=[MASK], scenes=("S2_A", "S2_B", "S2_C"))
        body = (await ask(rig, document)).json()
        assert body["resampling"] == {
            "grid": {"resolution": 10.0, "crs": "EPSG:32632"},
            "method": "nearest",
            "bands": [{"band": "rededge1", "resolution": 20.0, "crs": "EPSG:32632"}],
            "scenes": {"count": 1, "of": 3, "crs": "EPSG:32632"},
        }


class TestTheSchema:
    def test_the_document_says_the_member_is_always_there(self) -> None:
        schema = EstimateDocument.model_json_schema(by_alias=True)
        assert "resampling" in schema["required"]

    def test_a_resampling_that_names_neither_bands_nor_scenes_is_not_a_document(self) -> None:
        with pytest.raises(ValueError, match="bands, scenes or both"):
            Resampling.model_validate(
                {"grid": {"resolution": 10.0, "crs": None}, "method": "nearest", "bands": [], "scenes": None}
            )

    def test_the_method_is_the_one_the_core_uses(self) -> None:
        with pytest.raises(ValueError):
            Resampling.model_validate(
                {
                    "grid": {"resolution": 10.0, "crs": None},
                    "method": "bilinear",
                    "bands": [{"band": "b", "resolution": 20.0, "crs": None}],
                    "scenes": None,
                }
            )

    def test_a_scene_count_needs_more_than_one_scene(self) -> None:
        with pytest.raises(ValueError):
            Resampling.model_validate(
                {
                    "grid": {"resolution": 10.0, "crs": None},
                    "method": "nearest",
                    "bands": [],
                    "scenes": {"count": 1, "of": 1, "crs": "EPSG:32632"},
                }
            )

