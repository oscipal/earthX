"""The estimate route: the cost of an order before it is placed (M4-13a; plans/m4-13-processing-panel.md §3.1, F2).

Same rig as the job API tests: a real queue database (to show that nothing is written to it), the
items from a function, the ``HEAD`` side from a mock transport (to show that nothing is asked).
Everything is synthetic and offline.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx
import pytest

from earthx.api.intake import accept_order
from earthx.catalog.datasets import REGISTRY
from earthx.catalog.registry import DatasetRegistry, LicenseTier
from earthx.gateway import UpstreamError
from earthx.processing.operators import REGISTRY as REAL_OPERATORS
from earthx.processing.plan import estimate
from tests.conftest import own_log_text
from tests.earthx.api.conftest import Rig
from tests.earthx.api.test_intake import NEAR, S2_HOST, dem_item, order, s2_item
from tests.earthx.api.test_processing_route import (
    EXECUTION,
    client_for,
    count,
    envelope,
    place,
    problem,
    replace_api,
)

pytestmark = pytest.mark.anyio

ESTIMATE = "/processing/processes/recipe/estimate"
DURATION = re.compile(r"^PT[0-9]+\.[0-9]S$")


async def ask(rig: Rig, document: dict[str, Any] | None = None, **extra: Any) -> httpx.Response:
    return await rig.client.post(ESTIMATE, json=envelope(document, **extra))


class TestTheAnswer:
    async def test_a_valid_order_gets_its_cost(self, rig: Rig) -> None:
        response = await ask(rig)
        assert response.status_code == 200
        body = response.json()
        assert set(body) == {"estimate", "skippedItems"}
        assert set(body["estimate"]) == {
            "size",
            "duration",
            "outputPixels",
            "inputPixels",
            "inputBytes",
            "assets",
            "units",
        }
        cost = body["estimate"]
        assert cost["assets"] == 2
        assert cost["outputPixels"] > 0 and cost["inputPixels"] >= cost["outputPixels"] > 0
        assert cost["size"] > 0 and cost["units"] > 0 and DURATION.match(cost["duration"])
        assert body["skippedItems"] == []

    async def test_the_answer_is_the_estimate_of_the_plan_for_the_recipe_an_order_would_become(self, rig: Rig) -> None:
        body = (await ask(rig)).json()["estimate"]
        accepted = await accept_order(
            json.dumps(order()),
            registry=rig.api.registry,
            operators=rig.api.operators,
            item_source=rig.source,
            gateway=rig.api.gateway,
        )
        cost = estimate(accepted.recipe, rig.api.operators)
        assert body["size"] == cost.output_bytes
        assert body["outputPixels"] == cost.output_pixels
        assert (body["inputPixels"], body["inputBytes"], body["assets"]) == (
            cost.input_pixels,
            cost.input_bytes,
            cost.assets,
        )
        assert body["units"] == pytest.approx(cost.units)
        assert body["duration"] == f"PT{cost.seconds:.1f}S"

    async def test_more_steps_cost_more_units(self, rig: Rig) -> None:
        one = (await ask(rig, order(steps=[]))).json()["estimate"]["units"]
        two = (await ask(rig)).json()["estimate"]["units"]
        assert two > one > 0

    async def test_items_the_area_does_not_touch_are_named_and_left_out(self, rig: Rig) -> None:
        response = await ask(rig, order(groups=(("S2_A", "S2_FAR"),)))
        assert response.status_code == 200
        assert response.json()["skippedItems"] == ["S2_FAR"]

    async def test_every_answer_is_no_store_even_a_refusal(self, rig: Rig) -> None:
        assert (await ask(rig)).headers["cache-control"] == "no-store"
        assert (await ask(rig, order("no-such-dataset"))).headers["cache-control"] == "no-store"
        assert (await rig.client.post(ESTIMATE, content=b"{")).headers["cache-control"] == "no-store"

    async def test_it_works_for_another_dataset(self, rig: Rig) -> None:
        rig.source.items[("cop-dem-glo-30", "DEM_N47_E009")] = dem_item()
        response = await ask(rig, order("cop-dem-glo-30", groups=(("DEM_N47_E009",),), assets=("data",), steps=[]))
        assert response.status_code == 200, response.text
        assert response.json()["estimate"]["assets"] == 1


class TestNothingIsStartedAndNothingIsStored:
    async def test_no_asset_is_asked_and_no_row_is_written(self, rig: Rig) -> None:
        response = await ask(rig)
        assert response.status_code == 200
        assert rig.heads.requests == [], "an estimate makes no HEAD"
        assert (count(rig.db, "earthx_recipe"), count(rig.db, "earthx_run"), count(rig.db, "earthx_job")) == (0, 0, 0)

    async def test_the_answer_holds_no_identifier_and_no_address(self, rig: Rig) -> None:
        text = (await ask(rig)).text
        assert "recipe" not in text.lower() and "jobID" not in text
        assert S2_HOST not in text and "1220S2_A" not in text and "etag" not in text.lower()

    async def test_asking_twice_places_nothing_and_places_a_job_later_as_before(self, rig: Rig) -> None:
        await ask(rig)
        await ask(rig)
        assert (await place(rig)).status_code == 201
        assert count(rig.db, "earthx_job") == 1

    async def test_it_does_not_need_the_queue(self, rig: Rig) -> None:
        async with client_for(replace_api(rig.api, pool=None, events=None)) as client:
            response = await client.post(ESTIMATE, json=envelope())
        assert response.status_code == 200


class TestWhatItTurnsAway:
    """The stages `execution` turns an order away at before the versions, with the same status and type."""

    async def refused(self, rig: Rig, document: dict[str, Any], status: int, stage: str) -> dict[str, Any]:
        response = await ask(rig, document)
        body = problem(response, status)
        assert body["type"] == f"urn:earthx:order-refused:{stage}"
        assert rig.heads.requests == []
        assert (count(rig.db, "earthx_run"), count(rig.db, "earthx_job")) == (0, 0)
        return body

    async def test_the_same_refusal_as_placing(self, rig: Rig) -> None:
        cases = [
            (order("no-such-dataset"), 422, "dataset"),
            (order(steps=[{"op": "no_such_operator", "op_version": 1, "params": {}}]), 422, "order"),
            (order(groups=(("NO_SUCH_ITEM",),)), 422, "items"),
            (order(assets=("no_such_asset",)), 422, "resolve"),
        ]
        for document, status, stage in cases:
            placed = problem(await place(rig, document), status)
            asked = await self.refused(rig, document, status, stage)
            assert asked["type"] == placed["type"] and asked["detail"] == placed["detail"]

    async def test_a_crop_is_not_a_job(self, rig: Rig) -> None:
        crop = {
            "kind": "crop",
            "format": "cog",
            "resolution_factor": 1,
            "extent": "bbox(aoi ∩ footprints)",
            "mask": "file",
        }
        await self.refused(rig, order(steps=[], output=crop), 422, "order")

    async def test_an_order_that_carries_addresses_or_an_identifier_is_a_400(self, rig: Rig) -> None:
        recipe_id = "A" * 22
        await self.refused(rig, order(recipe_id=recipe_id), 400, "order")
        document = order()
        document["inputs"][0]["resolved"] = [{"asset": {"href": "https://secret.invalid/x.tif"}}]
        body = await self.refused(rig, document, 400, "order")
        assert "secret.invalid" not in json.dumps(body)

    async def test_more_items_than_an_order_may_name_are_a_413_and_none_is_fetched(self, rig: Rig) -> None:
        ids = tuple(f"S2_{n}" for n in range(26))
        await self.refused(rig, order(groups=((*ids,),)), 413, "size")
        assert rig.source.calls == []

    async def test_an_area_that_touches_no_item_is_a_422_and_does_not_repeat_it(self, rig: Rig) -> None:
        far = {
            "type": "Polygon",
            "coordinates": [[[100.123456, 10.0], [100.223456, 10.0], [100.223456, 10.1], [100.123456, 10.0]]],
        }
        body = await self.refused(rig, order(aoi=far), 422, "aoi")
        assert "100.123456" not in json.dumps(body)

    async def test_a_dataset_whose_licence_does_not_reach_processing_is_a_403(self, rig: Rig) -> None:
        from dataclasses import replace

        s2 = REGISTRY.get("sentinel-2-c1-l2a")
        display = replace(s2, license=replace(s2.license, tier=LicenseTier.DISPLAY))
        api = replace_api(rig.api, registry=DatasetRegistry((display,)))
        async with client_for(api) as client:
            response = await client.post(ESTIMATE, json=envelope())
        assert problem(response, 403)["type"] == "urn:earthx:order-refused:license"

    async def test_an_item_of_the_source_that_points_elsewhere_is_a_502_without_the_address(self, rig: Rig) -> None:
        item = s2_item()
        item["assets"]["red"]["href"] = "https://evil.example.invalid/steal.tif"
        rig.source.items[("sentinel-2-c1-l2a", "S2_A")] = item
        response = await ask(rig)
        problem(response, 502)
        assert "evil.example" not in response.text

    async def test_a_source_that_fails_is_a_502_and_does_not_name_it(self, rig: Rig) -> None:
        async def failing(dataset: str, item_id: str) -> dict[str, Any]:
            raise UpstreamError(500, "boom at https://secret.invalid/")

        async with client_for(replace_api(rig.api, item_source=failing)) as client:
            response = await client.post(ESTIMATE, json=envelope())
        problem(response, 502)
        assert "secret.invalid" not in response.text

    async def test_several_items_are_not_run_yet_so_not_estimated(self, rig: Rig) -> None:
        rig.source.items[("sentinel-2-c1-l2a", "S2_B")] = s2_item("S2_B", NEAR)
        response = await ask(rig, order(groups=(("S2_A",), ("S2_B",))))
        body = problem(response, 422)
        assert body["type"] == "urn:earthx:order-refused:scope" and "one item" in body["detail"]
        untouched_queue = (count(rig.db, "earthx_run"), count(rig.db, "earthx_job"))
        assert untouched_queue == (0, 0)

    async def test_a_band_the_item_does_not_describe_is_found_where_the_check_before_could_not_tell(
        self, rig: Rig
    ) -> None:
        item = s2_item()
        item["assets"]["red"].pop("raster:bands")
        rig.source.items[("sentinel-2-c1-l2a", "S2_A")] = item
        step = {"op": "band_math", "op_version": 1, "params": {"expression": "red_2 + 1"}}
        async with client_for(replace_api(rig.api, operators=REAL_OPERATORS)) as client:
            response = await client.post(ESTIMATE, json=envelope(order(assets=("red",), steps=[step])))
        body = problem(response, 422)
        assert body["type"] == "urn:earthx:order-refused:applicable" and "red_2" in body["detail"]

    async def test_a_wrong_process_is_a_404(self, rig: Rig) -> None:
        response = await rig.client.post("/processing/processes/other/estimate", json=envelope())
        problem(response, 404)

    @pytest.mark.parametrize(
        ("kwargs", "status"),
        [
            ({"content": b""}, 400),
            ({"content": b"{"}, 400),
            ({"content": b"[]"}, 400),
            ({"json": {"inputs": {"recipe": {"href": "https://example.invalid/o.json"}}}}, 400),
        ],
    )
    async def test_what_is_not_an_inline_order_is_a_400(self, rig: Rig, kwargs: dict[str, Any], status: int) -> None:
        response = await rig.client.post(ESTIMATE, headers={"Content-Type": "application/json"}, **kwargs)
        problem(response, status)
        assert rig.source.calls == [] and rig.heads.requests == []

    async def test_a_body_that_is_not_json_is_a_415(self, rig: Rig) -> None:
        response = await rig.client.post(ESTIMATE, content=b"{}", headers={"Content-Type": "text/plain"})
        problem(response, 415)

    async def test_a_body_over_the_cap_is_a_413(self, rig: Rig) -> None:
        response = await rig.client.post(
            ESTIMATE, content=b" " * (1_048_576 + 1), headers={"Content-Type": "application/json"}
        )
        problem(response, 413)
        assert rig.source.calls == []

    async def test_a_refusal_never_repeats_the_area(self, rig: Rig) -> None:
        response = await ask(rig, order(assets=("no_such_asset",)))
        assert "47.01" not in response.text and "9.01" not in response.text


class TestWhatItCannotSee:
    """Stage 7 is the version of each input; an estimate stops before it (module docstring of `api.intake`)."""

    async def test_an_asset_the_source_no_longer_has_passes_the_estimate_and_fails_the_placing(self, rig: Rig) -> None:
        item = s2_item()
        for asset in ("red", "nir"):
            item["assets"][asset].pop("file:checksum")
        item["properties"].pop("updated")
        rig.source.items[("sentinel-2-c1-l2a", "S2_A")] = item
        rig.heads._answer = lambda request: httpx.Response(404)
        assert (await ask(rig)).status_code == 200
        assert rig.heads.requests == []
        placed = await place(rig)
        assert problem(placed, 502)["type"] == "urn:earthx:order-refused:version"
        assert rig.heads.requests, "placing asked"


class TestLogs:
    async def test_the_log_names_the_dataset_and_the_size_of_the_order_never_the_area_or_an_address(
        self, rig: Rig, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.DEBUG, logger="earthx"):
            await ask(rig)
            await ask(rig, order(assets=("no_such_asset",)))
        records = [r for r in caplog.records if r.getMessage() == "order estimated"]
        assert len(records) == 1 and records[0].order_dataset == "sentinel-2-c1-l2a"
        assert records[0].order_items == 1 and records[0].order_assets == 2
        text = "\n".join(own_log_text(record) for record in caplog.records)
        assert caplog.records
        for forbidden in ("9.01", "47.01", S2_HOST, "1220S2_A", "recipe_id", "etag"):
            assert forbidden not in text, forbidden

    async def test_a_refusal_is_logged_with_its_stage_like_a_refusal_of_placing(
        self, rig: Rig, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.INFO, logger="earthx.api.intake"):
            await ask(rig, order("no-such-dataset"))
        record = next(r for r in caplog.records if r.getMessage() == "order refused")
        assert (record.order_stage, record.order_status) == ("dataset", 422)


class TestPlacingStillWorks:
    """`accept_order` was cut in two; its behaviour and the order of its refusals are the same."""

    async def test_a_placed_job_still_has_a_version_a_recipe_id_and_a_head(self, rig: Rig) -> None:
        item = s2_item()
        for asset in ("red", "nir"):
            item["assets"][asset].pop("file:checksum")
        item["properties"].pop("updated")
        rig.source.items[("sentinel-2-c1-l2a", "S2_A")] = item
        response = await rig.client.post(EXECUTION, json=envelope())
        assert response.status_code == 201
        assert len(rig.heads.requests) == 2, "one HEAD per asset"
        assert re.match(r"^[A-Za-z0-9_-]{22}$", response.json()["recipeID"])
