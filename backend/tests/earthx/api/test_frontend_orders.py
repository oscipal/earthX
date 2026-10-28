"""The orders the panel sends, held against the backend's own schema (M4-13b; plans/m4/m4-13-processing-panel.md §12).

``frontend/src/processingContract.test.ts`` builds orders the way the panel does, sends them through the
real client with ``fetch`` recorded, and writes what it would have sent to ``frontend/src/fixtures/orders/``.
This is the other half: every one of those files goes through the same validation and the same routes a
browser reaches. A panel that sends a member the schema forbids (the first version sent the ``properties`` of
a place-search outline in the AOI: ``aoi.Polygon.properties: extra_forbidden``) fails here, not at Otto's.

The routes run on the real operators with synthetic items that cover each file's area.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from shapely.geometry import shape

from earthx.processing.operators import REGISTRY as REAL_OPERATORS
from earthx.processing.recipe import parse_request
from tests.catalog.synthetic_zarr import SYNTHETIC_ZARR, registry_with_zarr
from tests.earthx.api.conftest import Rig
from tests.earthx.api.test_intake import dem_item, s2_item, zarr_item
from tests.earthx.api.test_processing_route import EXECUTION, client_for, replace_api

pytestmark = pytest.mark.anyio

ESTIMATE = "/processing/processes/recipe/estimate"
ORDERS = Path(__file__).resolve().parents[4] / "frontend" / "src" / "fixtures" / "orders"
FILES = sorted(ORDERS.glob("*.json"))


def test_there_are_orders_to_check() -> None:
    """A glob that finds nothing would pass for the wrong reason."""
    assert len(FILES) >= 6
    assert {json.loads(f.read_text("utf-8"))["inputs"]["recipe"]["inputs"][0]["dataset"] for f in FILES} == {
        "sentinel-2-c1-l2a",
        "cop-dem-glo-30",
        SYNTHETIC_ZARR.dataset_id,
    }


def api_of(rig: Rig):
    """The job API on the real operators and the registry with the synthetic Zarr entry the orders name."""
    return replace_api(rig.api, operators=REAL_OPERATORS, registry=registry_with_zarr())


def recipe_of(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text("utf-8"))["inputs"]["recipe"]


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.stem)
def test_the_schema_takes_the_order(path: Path) -> None:
    parse_request(json.dumps(recipe_of(path)), REAL_OPERATORS)


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.stem)
def test_the_order_has_exactly_the_members_of_the_schema(path: Path) -> None:
    recipe = recipe_of(path)
    # The AOI may be left out for the whole scenes of a pass (M4-12); where it is there, it is bare.
    assert set(recipe) - {"aoi"} == {"recipe_version", "inputs", "steps", "output"}
    assert set(recipe.get("aoi", {"type": 0, "coordinates": 0})) == {"type", "coordinates"}
    assert set(recipe["inputs"][0]) == {"name", "dataset", "groups", "assets"}
    assert all(set(step) == {"op", "op_version", "params"} for step in recipe["steps"])


def items_of(recipe: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    """The items the order names, covering the area of the order (or a shared one without an AOI).

    The scenes of a group are one overpass: they carry the same day and datatake, the key of ``results_group_by``.
    """
    entry = recipe["inputs"][0]
    area = recipe["aoi"] if "aoi" in recipe else None
    west, south, east, north = shape(area).bounds if area else (8.9, 46.9, 9.1, 47.1)
    box = (west - 0.1, south - 0.1, east + 0.1, north + 0.1)
    make = {"sentinel-2-c1-l2a": s2_item, "cop-dem-glo-30": dem_item, SYNTHETIC_ZARR.dataset_id: zarr_item}
    items = {}
    for item_id in entry["groups"][0]:
        item = make[entry["dataset"]](item_id, box)
        if entry["dataset"] == "sentinel-2-c1-l2a":
            item["properties"]["s2:datatake_id"] = "GS2B_20260601T100031_000000_N05.11"
            item["assets"]["visual"] = {
                **item["assets"]["red"],
                "gsd": 10,  # the pixel size was in the band description, which this asset replaces
                "raster:bands": [{"nodata": 0, "data_type": "uint8"}] * 3,
            }
            # The layer a mask reads (`earthx:mask`): classes, no scaling, a pixel of 20 m.
            item["assets"]["scl"] = {
                "href": item["assets"]["red"]["href"].replace("B04", "SCL"),
                "gsd": 20,
                "raster:bands": [{"nodata": 0, "data_type": "uint8", "spatial_resolution": 20}],
            }
        items[(entry["dataset"], item_id)] = item
    return items


def with_item(rig: Rig, recipe: dict[str, Any]) -> None:
    rig.source.items.update(items_of(recipe))


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.stem)
async def test_the_estimate_route_takes_the_body(rig: Rig, path: Path) -> None:
    body = json.loads(path.read_text("utf-8"))
    with_item(rig, body["inputs"]["recipe"])
    async with client_for(api_of(rig)) as client:
        response = await client.post(ESTIMATE, json=body)
    assert response.status_code == 200, response.text
    # What `processing.ts::parseEstimate` reads of the answer.
    body = response.json()
    assert set(body["estimate"]) == {"size", "duration", "outputPixels", "inputPixels", "inputBytes", "assets", "units"}
    assert body["estimate"]["size"] > 0 and isinstance(body["skippedItems"], list)


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.stem)
async def test_the_execution_route_takes_the_body(rig: Rig, path: Path) -> None:
    body = json.loads(path.read_text("utf-8"))
    with_item(rig, body["inputs"]["recipe"])
    async with client_for(api_of(rig)) as client:
        response = await client.post(EXECUTION, json=body, headers={"Prefer": "respond-async"})
    assert response.status_code == 201, response.text
    # What `processing.ts::parseStatusInfo` reads of the answer.
    status = response.json()
    assert re.fullmatch(r"[A-Za-z0-9_-]{22}", status["jobID"])
    assert status["status"] in {"accepted", "running", "successful", "failed", "dismissed"}
    assert isinstance(status["progress"], int) and isinstance(status["message"], str)
    assert datetime.fromisoformat(status["expires"]).tzinfo is not None


class TestTheCheckWouldHaveFoundTheFirstBug:
    """The same files with the member the first panel sent: the routes and the schema turn them away."""

    @pytest.fixture
    def body(self) -> dict[str, Any]:
        return json.loads((ORDERS / "ndvi-with-place-search-aoi.json").read_text("utf-8"))

    def test_the_schema_refuses_properties_in_the_aoi(self, body: dict[str, Any]) -> None:
        body["inputs"]["recipe"]["aoi"]["properties"] = {"source": "OpenStreetMap / Nominatim"}
        with pytest.raises(Exception, match="extra_forbidden"):
            parse_request(json.dumps(body["inputs"]["recipe"]), REAL_OPERATORS)

    async def test_the_estimate_route_refuses_them_with_a_400(self, rig: Rig, body: dict[str, Any]) -> None:
        with_item(rig, body["inputs"]["recipe"])
        body["inputs"]["recipe"]["aoi"]["properties"] = {"source": "x"}
        async with client_for(api_of(rig)) as client:
            response = await client.post(ESTIMATE, json=body)
        assert response.status_code in (400, 422)
        assert "extra_forbidden" in response.json()["detail"]


class TestTheOrdersOfAMosaic:
    """The orders of M4-12b: the scenes of a pass in one group, and the dialog's order with no AOI at all."""

    DIALOG = ORDERS / "whole-scenes-of-a-pass-without-aoi.json"
    PANEL = ORDERS / "ndvi-on-a-mosaic-of-three-scenes.json"

    def test_the_files_are_there_and_name_several_scenes(self) -> None:
        assert [len(recipe_of(f)["inputs"][0]["groups"][0]) for f in (self.DIALOG, self.PANEL)] == [2, 3]
        assert "aoi" not in recipe_of(self.DIALOG) and recipe_of(self.DIALOG)["steps"] == []

    @pytest.mark.parametrize("file", [DIALOG, PANEL], ids=lambda p: p.stem)
    async def test_a_scene_of_another_pass_is_refused_with_its_id(self, rig: Rig, file: Path) -> None:
        body = json.loads(file.read_text("utf-8"))
        with_item(rig, body["inputs"]["recipe"])
        odd = body["inputs"]["recipe"]["inputs"][0]["groups"][0][-1]
        rig.source.items[("sentinel-2-c1-l2a", odd)]["properties"]["s2:datatake_id"] = (
            "GS2B_20260602T100031_000000_N05.11"
        )
        async with client_for(api_of(rig)) as client:
            response = await client.post(EXECUTION, json=body, headers={"Prefer": "respond-async"})
        assert response.status_code == 422 and odd in response.json()["detail"], response.text

    async def test_the_estimate_of_the_dialog_order_is_taken(self, rig: Rig) -> None:
        body = json.loads(self.DIALOG.read_text("utf-8"))
        with_item(rig, body["inputs"]["recipe"])
        async with client_for(api_of(rig)) as client:
            response = await client.post(ESTIMATE, json=body)
        assert response.status_code == 200, response.text
        assert response.json()["skippedItems"] == []
