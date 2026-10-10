"""The job API: place a job, read it, dismiss it, fetch its result (M4-08b; adr/0013 §8 point 9, adr/0015 §6).

A real queue database and a real pool and hub; the order's items come from a function, the
``HEAD`` side from a mock transport behind a real ``Gateway``; the worker is played by
``finish``, which writes the end state a worker would. Everything is synthetic and offline.
"""

from __future__ import annotations

import json
import logging
import re
import secrets
from datetime import UTC, datetime, timedelta, timezone
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
import psycopg
import pytest
from psycopg_pool import ConnectionPool

from earthx.api.job_events import JobEvents
from earthx.api.processing_route import _FAILURES, LINK_NAMES, MAX_BODY_BYTES, JobApi
from earthx.catalog.datasets import REGISTRY
from earthx.catalog.registry import DatasetRegistry, LicenseTier
from earthx.jobs.submit import RecipeIdTaken
from earthx.objectstore.errors import StoreUnavailable
from earthx.processing.operators import REGISTRY as REAL_OPERATORS
from earthx.processing.recipe import job_recipe_document
from tests.conftest import own_log_text
from tests.earthx.api.conftest import Rig, build_app
from tests.earthx.api.test_intake import (
    CROP,
    DEM,
    NEAR,
    PLACE,
    S2_HOST,
    SCALE_STEP,
    dem_item,
    order,
    s2_item,
)

pytestmark = pytest.mark.anyio

EXECUTION = "/processing/processes/recipe/execution"
ID = re.compile(r"^[A-Za-z0-9_-]{22}$")
FINISHED_AT = "2026-03-05 10:00:00+00"
RESULT = {
    "properties": {"proj:code": "EPSG:32632", "processing:lineage": "scale"},
    "scaling": [{"input": "scene", "asset": "red", "source": "item", "scales": [0.0001], "offsets": [-0.1]}],
    "blocks": 4,
    "valid_pixels": 100,
    "engine": {"earthx": "0.0.0", "gdal": "3.12.2", "rasterio": "1.5.0", "numexpr": "2.14.0", "numpy": "2.3.0"},
    "width": 64,
    "height": 48,
    "bands": 2,
    "bytes": 12345,
}


def envelope(document: dict[str, Any] | None = None, **extra: Any) -> dict[str, Any]:
    return {"inputs": {"recipe": order() if document is None else document}, **extra}


async def place(rig: Rig, document: dict[str, Any] | None = None, **extra: Any) -> httpx.Response:
    return await rig.client.post(EXECUTION, json=envelope(document, **extra))


async def placed(rig: Rig, document: dict[str, Any] | None = None) -> str:
    response = await place(rig, document)
    assert response.status_code == 201, response.text
    return response.json()["jobID"]


def finish(
    db: psycopg.Connection,
    job_id: str,
    *,
    status: str = "successful",
    kind: str | None = None,
    expires: str = "7 days",
    result: dict[str, Any] | None = None,
) -> str:
    """Write the end of the run the way the worker does; returns the ``result_id``."""
    result_id = secrets.token_urlsafe(16)
    db.execute(
        """
        UPDATE public.earthx_run SET status = %s, error_kind = %s, progress = 100,
               result_id = %s, result = %s::jsonb,
               started_at = %s::timestamptz - interval '1 minute', finished_at = %s::timestamptz,
               expires_at = clock_timestamp() + %s::interval
        WHERE run_id = (SELECT run_id FROM public.earthx_job WHERE job_id = %s)
        """,
        (
            status,
            kind,
            result_id if status == "successful" else None,
            json.dumps(RESULT if result is None else result) if status == "successful" else None,
            FINISHED_AT,
            FINISHED_AT,
            expires,
            job_id,
        ),
    )
    return result_id


def count(db: psycopg.Connection, table: str) -> int:
    row = db.execute(f"SELECT count(*) FROM public.{table}").fetchone()
    assert row is not None
    return row[0]


def problem(response: httpx.Response, status: int | None = None) -> dict[str, Any]:
    assert response.headers["content-type"] == "application/problem+json", response.text
    body = response.json()
    assert set(body) == {"type", "title", "status", "detail"}
    assert body["status"] == response.status_code
    if status is not None:
        assert response.status_code == status
    return body


def untouched(rig: Rig) -> None:
    """Nothing was fetched, resolved or queued."""
    assert rig.source.calls == [] and rig.heads.requests == []
    assert (count(rig.db, "earthx_recipe"), count(rig.db, "earthx_run"), count(rig.db, "earthx_job")) == (0, 0, 0)


class TestPlacing:
    async def test_a_valid_order_is_a_job_that_waits(self, rig: Rig) -> None:
        response = await place(rig)
        assert response.status_code == 201
        body = response.json()
        assert ID.match(body["jobID"]) and ID.match(body["recipeID"])
        assert (body["processID"], body["type"], body["status"], body["progress"]) == (
            "recipe",
            "process",
            "accepted",
            0,
        )
        assert response.headers["location"] == f"/processing/jobs/{body['jobID']}"
        assert response.headers["cache-control"] == "no-store"
        assert body["skippedItems"] == []
        assert datetime.fromisoformat(body["expires"]) > datetime.now(UTC) + timedelta(days=6)
        rels = {link["rel"]: link["href"] for link in body["links"]}
        assert rels["self"] == rels["monitor"].removesuffix("/events") == f"/processing/jobs/{body['jobID']}"
        assert "http://www.opengis.net/def/rel/ogc/1.0/results" not in rels
        assert (count(rig.db, "earthx_recipe"), count(rig.db, "earthx_run"), count(rig.db, "earthx_job")) == (1, 1, 1)

    async def test_the_answer_is_asynchronous_with_or_without_a_preference(self, rig: Rig) -> None:
        plain = await place(rig)
        assert plain.status_code == 201 and "preference-applied" not in plain.headers
        for prefer in ("respond-async", "respond-async, wait=10", "return=minimal; respond-async"):
            response = await rig.client.post(EXECUTION, json=envelope(), headers={"Prefer": prefer})
            assert response.status_code == 201
            assert response.headers["preference-applied"] == "respond-async"
        sync = await rig.client.post(EXECUTION, json=envelope(), headers={"Prefer": "respond-sync"})
        assert sync.status_code == 201 and sync.json()["status"] == "accepted"

    async def test_equal_orders_share_a_run_but_not_a_job_or_a_recipe(self, rig: Rig) -> None:
        first, second = await place(rig), await place(rig)
        a, b = first.json(), second.json()
        assert a["jobID"] != b["jobID"] and a["recipeID"] != b["recipeID"]
        assert (count(rig.db, "earthx_run"), count(rig.db, "earthx_job")) == (1, 2)

    async def test_the_outputs_of_the_process_may_be_asked_for_by_reference(self, rig: Rig) -> None:
        response = await place(
            rig, outputs={"result": {"transmissionMode": "reference"}, "mask": {}, "recipe": {}}, response="document"
        )
        assert response.status_code == 201

    async def test_items_the_area_does_not_touch_are_named_and_left_out(self, rig: Rig) -> None:
        response = await place(rig, order(groups=(("S2_A", "S2_FAR"),)))
        assert response.status_code == 201
        assert response.json()["skippedItems"] == ["S2_FAR"]

    async def test_a_second_equal_order_after_a_good_run_is_answered_from_the_cache(self, rig: Rig) -> None:
        first = await placed(rig)
        finish(rig.db, first)
        response = await place(rig)
        body = response.json()
        assert response.status_code == 201 and body["status"] == "successful" and body["progress"] == 100
        assert body["jobID"] != first and count(rig.db, "earthx_run") == 1
        assert "http://www.opengis.net/def/rel/ogc/1.0/results" in {link["rel"] for link in body["links"]}

    async def test_a_result_with_less_than_a_day_left_is_not_a_hit(self, rig: Rig) -> None:
        first = await placed(rig)
        finish(rig.db, first, expires="23 hours")
        body = (await place(rig)).json()
        assert body["status"] == "accepted" and count(rig.db, "earthx_run") == 2

    async def test_an_order_without_a_version_is_computed_again(self, rig: Rig) -> None:
        item = s2_item()
        for asset in ("red", "nir"):
            item["assets"][asset].pop("file:checksum")
        item["properties"].pop("updated")
        rig.source.items[("sentinel-2-c1-l2a", "S2_A")] = item
        # A source that gives no ETag either: the version stays empty, and an empty one is never a hit.
        rig.heads._answer = lambda request: httpx.Response(200)
        first = await placed(rig)
        finish(rig.db, first)
        assert (await place(rig)).json()["status"] == "accepted"

    async def test_a_dem_order_asks_the_source_for_its_version_and_places_the_job(self, rig: Rig) -> None:
        rig.source.items[("cop-dem-glo-30", "DEM_N47_E009")] = dem_item()
        document = order("cop-dem-glo-30", (("DEM_N47_E009",),), ("data",))
        assert (await place(rig, document)).status_code == 201
        assert len(rig.heads.requests) == 1 and rig.heads.requests[0].method == "HEAD"


class TestWhatIsNotAnInlineOrder:
    """F4: an input by reference is the part of OGC the platform does not do (B8). Nothing is fetched for it."""

    @pytest.mark.parametrize(
        "reference",
        [
            {"href": "https://example.invalid/order.json"},
            {"href": "https://example.invalid/order.json", "type": "application/json"},
            {"href": "http://169.254.169.254/latest/meta-data/"},
            {"href": "file:///etc/passwd"},
            {"href": ""},
            "https://example.invalid/order.json",
            "",
        ],
    )
    async def test_an_input_given_as_a_link_is_a_400_that_says_inline_only(self, rig: Rig, reference: Any) -> None:
        response = await rig.client.post(EXECUTION, json={"inputs": {"recipe": reference}})
        body = problem(response, 400)
        assert "inline only" in body["detail"] and "not fetched" in body["detail"]
        assert "inputs.recipe" in body["detail"], "it says where the order goes"
        untouched(rig)

    async def test_the_address_of_a_link_is_never_asked_for_nor_repeated(self, rig: Rig) -> None:
        response = await rig.client.post(EXECUTION, json={"inputs": {"recipe": {"href": "https://secret.invalid/x"}}})
        assert "secret.invalid" not in response.text
        untouched(rig)

    async def test_a_qualified_value_is_not_taken_either(self, rig: Rig) -> None:
        response = await rig.client.post(EXECUTION, json={"inputs": {"recipe": {"value": order()}}})
        assert "inline only" in problem(response, 400)["detail"]
        untouched(rig)

    @pytest.mark.parametrize(
        ("document", "fragment"),
        [
            ({}, "holds the input"),
            ({"inputs": {}}, "holds the input"),
            ({"inputs": []}, "holds the input"),
            ({"inputs": {"other": {}}}, "holds the input"),
            ({"inputs": {"recipe": {}, "other": {}}}, "holds the input"),
            ({"inputs": {"aoiProvenance": {"source": "x"}}}, "holds the input"),
            ({"inputs": {"recipe": []}}, "a JSON object"),
            ({"inputs": {"recipe": 7}}, "a JSON object"),
            ({"inputs": {"recipe": None}}, "a JSON object"),
            ({"inputs": {"recipe": {}}, "subscriber": {"successUri": "https://example.invalid/hook"}}, "does not take"),
            ({"inputs": {"recipe": {}}, "callback": "x"}, "does not take"),
            ({"inputs": {"recipe": {}}, "response": "raw"}, "response is document"),
            ({"inputs": {"recipe": {}}, "response": None}, "response is document"),
            ({"inputs": {"recipe": {}}, "outputs": []}, "outputs names"),
            ({"inputs": {"recipe": {}}, "outputs": {"other": {}}}, "outputs names"),
            ({"inputs": {"recipe": {}}, "outputs": {"result": {"transmissionMode": "value"}}}, "by reference"),
            ({"inputs": {"recipe": {}}, "outputs": {"result": {"format": {"mediaType": "image/png"}}}}, "only transmissionMode"),
            ({"inputs": {"recipe": {}}, "outputs": {"result": "x"}}, "only transmissionMode"),
        ],
    )  # fmt: skip
    async def test_the_envelope_holds_what_the_platform_can_honour_and_nothing_else(
        self, rig: Rig, document: Any, fragment: str
    ) -> None:
        response = await rig.client.post(EXECUTION, json=document)
        assert fragment in problem(response, 400)["detail"]
        untouched(rig)

    @pytest.mark.parametrize(
        "raw",
        [
            b"",
            b"not json",
            b"[]",
            b'"text"',
            b"7",
            b"null",
            b'{"inputs": {"recipe": {}}, "inputs": {"recipe": {}}}',
            b'{"inputs": {"recipe": {"recipe_version": NaN}}}',
            b'{"inputs": {"recipe": {"recipe_version": 1e999}}}',
            b'{"inputs": {"recipe": {"recipe_version": 9007199254740993}}}',
            b"\xff\xfe",
            b'{"inputs": {"recipe": {"recipe_version": 1, "x": "\\ud800"}}}',
        ],
    )
    async def test_a_body_that_is_not_a_json_object_is_a_400(self, rig: Rig, raw: bytes) -> None:
        response = await rig.client.post(EXECUTION, content=raw, headers={"Content-Type": "application/json"})
        problem(response, 400)
        untouched(rig)

    async def test_a_refusal_of_the_json_does_not_repeat_what_was_sent(self, rig: Rig) -> None:
        raw = b'{"inputs": {"recipe": {"coordinates-47.123456": 1, "coordinates-47.123456": 2}}}'
        response = await rig.client.post(EXECUTION, content=raw, headers={"Content-Type": "application/json"})
        assert "duplicate key" in problem(response, 400)["detail"]

    async def test_a_recipe_that_already_has_addresses_is_not_an_order(self, rig: Rig) -> None:
        document = order()
        document["inputs"][0]["resolved"] = []
        document["recipe_id"] = "A" * 22
        response = await place(rig, document)
        problem(response, 400)
        untouched(rig)

    @pytest.mark.parametrize("content_type", ["text/plain", "application/x-www-form-urlencoded", "", "image/png"])
    async def test_a_body_that_is_not_json_by_its_type_is_a_415(self, rig: Rig, content_type: str) -> None:
        response = await rig.client.post(
            EXECUTION, content=json.dumps(envelope()), headers={"Content-Type": content_type}
        )
        problem(response, 415)
        untouched(rig)

    async def test_a_json_type_with_a_charset_is_fine(self, rig: Rig) -> None:
        response = await rig.client.post(
            EXECUTION, content=json.dumps(envelope()), headers={"Content-Type": "application/json; charset=utf-8"}
        )
        assert response.status_code == 201

    async def test_a_body_over_the_cap_is_a_413_whether_or_not_it_says_how_long_it_is(self, rig: Rig) -> None:
        big = b'{"inputs": {"recipe": {"x": "' + b"a" * MAX_BODY_BYTES + b'"}}}'
        sized = await rig.client.post(EXECUTION, content=big, headers={"Content-Type": "application/json"})
        problem(sized, 413)

        async def chunks():  # no Content-Length: the cap counts what arrives
            for start in range(0, len(big), 65536):
                yield big[start : start + 65536]

        streamed = await rig.client.post(EXECUTION, content=chunks(), headers={"Content-Type": "application/json"})
        problem(streamed, 413)
        untouched(rig)

    async def test_the_cap_is_the_size_of_an_aoi_file(self) -> None:
        from earthx.access.aoi_upload import MAX_UPLOAD_BYTES

        assert MAX_BODY_BYTES == MAX_UPLOAD_BYTES

    async def test_another_process_is_not_executed(self, rig: Rig) -> None:
        response = await rig.client.post("/processing/processes/other/execution", json=envelope())
        assert problem(response, 404)["type"].endswith("/no-such-process")
        untouched(rig)

    @pytest.mark.parametrize("method", ["PUT", "PATCH", "DELETE"])
    async def test_the_execution_takes_post_only(self, rig: Rig, method: str) -> None:
        assert (await rig.client.request(method, EXECUTION)).status_code == 405

    async def test_there_is_no_synchronous_execution_and_no_job_list(self, rig: Rig) -> None:
        assert (await rig.client.get("/processing/jobs", follow_redirects=True)).status_code == 404
        assert (await rig.client.get(EXECUTION)).status_code == 405


class TestWhatTheOrderMayNotBe:
    """What `accept_order` turns away, as the API says it (M4-07b stages, one status each)."""

    async def refused(self, rig: Rig, document: dict[str, Any], status: int, stage: str) -> dict[str, Any]:
        response = await place(rig, document)
        body = problem(response, status)
        assert body["type"] == f"urn:earthx:order-refused:{stage}"
        assert (count(rig.db, "earthx_run"), count(rig.db, "earthx_job")) == (0, 0)
        return body

    async def test_an_unknown_dataset_is_a_422(self, rig: Rig) -> None:
        await self.refused(rig, order("no-such-dataset"), 422, "dataset")

    async def test_an_unknown_operator_is_a_422(self, rig: Rig) -> None:
        step = {"op": "no_such_operator", "op_version": 1, "params": {}}
        await self.refused(rig, order(steps=[step]), 422, "order")

    async def test_an_operator_in_a_version_the_platform_does_not_run_is_a_422(self, rig: Rig) -> None:
        step = {**SCALE_STEP, "op_version": 99}
        await self.refused(rig, order(steps=[step]), 422, "order")

    async def test_parameters_the_operator_does_not_take_are_a_422(self, rig: Rig) -> None:
        step = {"op": "scale", "op_version": 1, "params": {"factor": "2", "extra": 1}}
        body = await self.refused(rig, order(steps=[step]), 422, "order")
        assert "parameters of step 0 (scale)" in body["detail"], "it says which step, and not what was sent"
        assert '"2"' not in body["detail"], "what was sent is not repeated"

    async def test_an_export_with_steps_is_refused(self, rig: Rig) -> None:
        await self.refused(rig, order(output=CROP), 422, "order")

    async def test_an_unknown_item_is_a_422_that_names_it(self, rig: Rig) -> None:
        body = await self.refused(rig, order(groups=(("NO_SUCH_ITEM",),)), 422, "items")
        assert "NO_SUCH_ITEM" in body["detail"]

    async def test_an_area_that_touches_no_item_is_a_422_and_does_not_repeat_it(self, rig: Rig) -> None:
        far = {
            "type": "Polygon",
            "coordinates": [[[100.123456, 10.0], [100.223456, 10.0], [100.223456, 10.1], [100.123456, 10.0]]],
        }
        body = await self.refused(rig, order(aoi=far), 422, "aoi")
        assert "100.123456" not in json.dumps(body)

    async def test_more_items_than_an_order_may_name_are_a_413(self, rig: Rig) -> None:
        ids = tuple(f"S2_{n}" for n in range(26))
        await self.refused(rig, order(groups=((*ids,),)), 413, "size")
        assert rig.source.calls == [], "no item was fetched for an order that is too big"

    async def test_an_unknown_asset_is_a_422(self, rig: Rig) -> None:
        await self.refused(rig, order(assets=("no_such_asset",)), 422, "resolve")

    async def test_a_dataset_whose_licence_does_not_reach_processing_is_a_403(self, rig: Rig) -> None:
        S2 = REGISTRY.get("sentinel-2-c1-l2a")
        from dataclasses import replace

        display = replace(S2, license=replace(S2.license, tier=LicenseTier.DISPLAY))
        registry = DatasetRegistry((display,))
        api = replace_api(rig.api, registry=registry)
        async with client_for(api) as client:
            response = await client.post(EXECUTION, json=envelope())
        assert problem(response, 403)["type"] == "urn:earthx:order-refused:license"

    async def test_several_items_are_not_run_yet_and_do_not_wait_in_the_queue(self, rig: Rig) -> None:
        rig.source.items[("sentinel-2-c1-l2a", "S2_B")] = s2_item("S2_B", NEAR)
        response = await place(rig, order(groups=(("S2_A",), ("S2_B",))))
        body = problem(response, 422)
        assert body["type"] == "urn:earthx:order-refused:scope" and "one item" in body["detail"]
        assert (count(rig.db, "earthx_run"), count(rig.db, "earthx_job")) == (0, 0)

    async def test_an_item_of_the_source_that_points_elsewhere_is_a_502_without_the_address(self, rig: Rig) -> None:
        item = s2_item()
        item["assets"]["red"]["href"] = "https://evil.example.invalid/steal.tif"
        rig.source.items[("sentinel-2-c1-l2a", "S2_A")] = item
        response = await place(rig)
        problem(response, 502)
        assert "evil.example" not in response.text
        assert count(rig.db, "earthx_job") == 0

    async def test_a_refusal_never_repeats_the_area(self, rig: Rig) -> None:
        response = await place(rig, order(assets=("no_such_asset",)))
        assert "47.01" not in response.text and "9.01" not in response.text

    async def test_a_band_the_item_does_not_describe_is_a_422_and_not_in_the_queue(self, rig: Rig) -> None:
        # The check at acceptance cannot tell where an asset has no band description; the time limit of
        # the run is the first place that can, and it used to end as a 500.
        item = s2_item()
        item["assets"]["red"].pop("raster:bands")
        rig.source.items[("sentinel-2-c1-l2a", "S2_A")] = item
        step = {"op": "band_math", "op_version": 1, "params": {"expression": "red_2 + 1"}}
        async with client_for(replace_api(rig.api, operators=REAL_OPERATORS)) as client:
            response = await client.post(EXECUTION, json=envelope(order(assets=("red",), steps=[step])))
        body = problem(response, 422)
        assert body["type"] == "urn:earthx:order-refused:applicable" and "red_2" in body["detail"]
        assert (count(rig.db, "earthx_recipe"), count(rig.db, "earthx_run"), count(rig.db, "earthx_job")) == (0, 0, 0)


def replace_api(api: JobApi, **changes: Any) -> JobApi:
    from dataclasses import replace

    return replace(api, **changes)


def client_for(api: JobApi) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=build_app(api)), base_url="http://test")


class TestTheQueueIsNotThere:
    async def test_an_unreachable_database_is_a_503_that_names_nothing(self, rig: Rig) -> None:
        dead = ConnectionPool(
            conninfo="host=127.0.0.1 port=1 dbname=x user=x password=secret-password",
            min_size=0,
            max_size=1,
            timeout=1,
            open=False,
        )
        dead.open(wait=False)
        try:
            api = replace_api(rig.api, pool=dead, events=JobEvents(dead))
            async with client_for(api) as client:
                for method, path in (
                    ("GET", "/processing/jobs/" + "A" * 22),
                    ("DELETE", "/processing/jobs/" + "A" * 22),
                    ("POST", EXECUTION),
                ):
                    kwargs = {"json": envelope()} if method == "POST" else {}
                    response = await client.request(method, path, **kwargs)
                    assert response.status_code == 503, path
                    assert response.headers["retry-after"] == "5"
                    assert "secret-password" not in response.text and "127.0.0.1" not in response.text
        finally:
            dead.close()


class TestTheProgressHubIsNotThere:
    async def test_a_hub_that_cannot_reach_the_database_is_a_503_before_the_stream_starts(self, rig: Rig) -> None:
        dead = ConnectionPool(
            conninfo="host=127.0.0.1 port=1 dbname=x user=x password=secret-password",
            min_size=0,
            max_size=1,
            timeout=1,
            open=False,
        )
        dead.open(wait=False)
        job_id = await placed(rig)
        try:
            api = replace_api(rig.api, events=JobEvents(dead))
            async with client_for(api) as client:
                response = await client.get(f"/processing/jobs/{job_id}/events")
            assert response.status_code == 503 and response.headers["retry-after"] == "5"
            assert "secret-password" not in response.text
        finally:
            dead.close()


class TestStatus:
    async def test_the_states_of_a_job(self, rig: Rig) -> None:
        job_id = await placed(rig)
        url = f"/processing/jobs/{job_id}"
        waiting = (await rig.client.get(url)).json()
        assert (waiting["status"], waiting["progress"], waiting["message"]) == (
            "accepted",
            0,
            "The job is waiting for a worker.",
        )
        rig.db.execute("UPDATE public.earthx_run SET status = 'running', progress = 42, started_at = clock_timestamp()")
        running = (await rig.client.get(url)).json()
        assert (running["status"], running["progress"], running["message"]) == ("running", 42, "The job is running.")
        assert "started" in running and "finished" not in running
        finish(rig.db, job_id)
        done = (await rig.client.get(url)).json()
        assert (done["status"], done["progress"]) == ("successful", 100)
        assert done["finished"].startswith("2026-03-05T10:00:00")
        rels = {link["rel"] for link in done["links"]}
        assert "http://www.opengis.net/def/rel/ogc/1.0/results" in rels and "monitor" not in rels

    async def test_a_failed_job_names_the_kind_and_no_text_of_the_failure(self, rig: Rig) -> None:
        job_id = await placed(rig)
        finish(rig.db, job_id, status="failed", kind="source_timeout")
        body = (await rig.client.get(f"/processing/jobs/{job_id}")).json()
        assert (body["status"], body["message"]) == ("failed", "The source did not answer in time")
        assert "result" not in json.dumps(body["links"])

    async def test_it_has_no_hash_no_run_no_area_no_address_and_no_result_id(self, rig: Rig) -> None:
        job_id = await placed(rig)
        result_id = finish(rig.db, job_id)
        text = (await rig.client.get(f"/processing/jobs/{job_id}")).text
        for forbidden in ("c1:", S2_HOST, "9.01", "47.01", result_id, "run_id", "cache_key", "hosts"):
            assert forbidden not in text

    async def test_looking_at_a_job_changes_no_row(self, rig: Rig) -> None:
        job_id = await placed(rig)
        finish(rig.db, job_id)
        snapshot = """
            SELECT 'recipe', xmin::text, recipe_id FROM public.earthx_recipe
            UNION ALL SELECT 'run', xmin::text, run_id::text FROM public.earthx_run
            UNION ALL SELECT 'job', xmin::text, job_id FROM public.earthx_job
            ORDER BY 1, 3
        """
        before = rig.db.execute(snapshot).fetchall()
        for path in ("", "/results", "/results/result.tif", "/results/recipe.json"):
            await rig.client.get(f"/processing/jobs/{job_id}{path}")
        assert rig.db.execute(snapshot).fetchall() == before


NO_JOB_ROUTES = [
    ("GET", ""),
    ("DELETE", ""),
    ("GET", "/results"),
    ("GET", "/results/result.tif"),
    ("GET", "/results/mask.tif"),
    ("GET", "/results/recipe.json"),
    ("GET", "/events"),
]
MALFORMED = [
    "short",
    "A" * 21,
    "A" * 23,
    "A" * 21 + "=",
    "A" * 21 + ".",
    "%2e%2e",
    "a b",
    "A" * 22 + "%00",
    "A" * 22 + "%0A",
    "é" * 22,
]


class TestAJobThatIsNotThere:
    """§8 point 9: a foreign, malformed, dismissed or expired identifier is a 404, whatever the route."""

    def check(self, response: httpx.Response) -> None:
        body = problem(response, 404)
        assert body["type"].endswith("/no-such-job")
        assert body["detail"] == "there is no such job"

    @pytest.mark.parametrize(("method", "tail"), NO_JOB_ROUTES)
    async def test_an_unknown_identifier(self, rig: Rig, method: str, tail: str) -> None:
        self.check(await rig.client.request(method, f"/processing/jobs/{'A' * 22}{tail}"))

    @pytest.mark.parametrize("bad", MALFORMED)
    @pytest.mark.parametrize(("method", "tail"), NO_JOB_ROUTES)
    async def test_a_malformed_identifier(self, rig: Rig, bad: str, method: str, tail: str) -> None:
        self.check(await rig.client.request(method, f"/processing/jobs/{bad}{tail}"))

    @pytest.mark.parametrize(("method", "tail"), NO_JOB_ROUTES)
    async def test_a_dismissed_job(self, rig: Rig, method: str, tail: str) -> None:
        job_id = await placed(rig)
        assert (await rig.client.delete(f"/processing/jobs/{job_id}")).status_code == 200
        self.check(await rig.client.request(method, f"/processing/jobs/{job_id}{tail}"))

    @pytest.mark.parametrize(("method", "tail"), [route for route in NO_JOB_ROUTES if "results/" not in route[1]])
    async def test_an_expired_job(self, rig: Rig, method: str, tail: str) -> None:
        job_id = await placed(rig)
        finish(rig.db, job_id, expires="-1 hour")
        self.check(await rig.client.request(method, f"/processing/jobs/{job_id}{tail}"))

    async def test_nobody_can_tell_never_from_dismissed_from_expired(self, rig: Rig) -> None:
        dismissed, expired = await placed(rig, order(assets=("red",))), await placed(rig)
        await rig.client.delete(f"/processing/jobs/{dismissed}")
        finish(rig.db, expired, expires="-1 hour")
        bodies = {
            (await rig.client.get(f"/processing/jobs/{job_id}")).text for job_id in ("A" * 22, dismissed, expired)
        }
        assert len(bodies) == 1

    async def test_a_name_the_job_does_not_have_is_a_404_for_a_job_that_exists(self, rig: Rig) -> None:
        job_id = await placed(rig)
        finish(rig.db, job_id)
        for name in (
            "other.tif",
            "RESULT.TIF",
            "..%2Fresult.tif",
            "result.tif%00",
            "recipe.json.bak",
            "citation.bib",
        ):
            response = await rig.client.get(f"/processing/jobs/{job_id}/results/{name}")
            assert response.status_code == 404, name


class TestResults:
    async def test_a_job_that_waits_or_runs_has_no_result_yet(self, rig: Rig) -> None:
        job_id = await placed(rig)
        for state in ("accepted", "running"):
            rig.db.execute("UPDATE public.earthx_run SET status = %s", (state,))
            response = await rig.client.get(f"/processing/jobs/{job_id}/results")
            assert problem(response, 404)["type"].endswith("/result-not-ready")
            link = await rig.client.get(f"/processing/jobs/{job_id}/results/result.tif")
            assert problem(link, 404)["type"].endswith("/result-not-ready")

    @pytest.mark.parametrize("kind", sorted(_FAILURES))
    async def test_a_failed_job_answers_with_the_status_of_its_kind(self, rig: Rig, kind: str) -> None:
        job_id = await placed(rig)
        finish(rig.db, job_id, status="failed", kind=kind)
        for tail in ("/results", "/results/result.tif", "/results/recipe.json"):
            response = await rig.client.get(f"/processing/jobs/{job_id}{tail}")
            body = problem(response, _FAILURES[kind][0])
            assert body["type"] == f"urn:earthx:job-failed:{kind}" and body["title"] == _FAILURES[kind][1]
            assert body["detail"] == "the job failed; no result exists"

    def test_the_statuses_are_the_ones_the_plan_chose(self) -> None:
        expected = {
            422: {"recipe_invalid", "unsupported_recipe", "scaling_mismatch", "grid_mismatch", "aoi_outside_inputs"},
            502: {"source_4xx", "source_429", "source_5xx", "source_unreachable", "rejected"},
            504: {"source_timeout"},
            500: {"out_of_memory", "child_crashed", "runtime_exceeded", "upload_failed", "lease_lost", "cancelled", "unknown",
                  "disk_space"},
        }  # fmt: skip
        assert {code: {k for k, (c, _) in _FAILURES.items() if c == code} for code in expected} == expected

    @pytest.mark.parametrize("kind", ["weird", "", "source_timeout; drop table", None])
    async def test_a_kind_nobody_knows_is_a_500_named_unknown_and_not_repeated(
        self, rig: Rig, kind: str | None
    ) -> None:
        job_id = await placed(rig)
        finish(rig.db, job_id, status="failed", kind=kind)
        response = await rig.client.get(f"/processing/jobs/{job_id}/results")
        body = problem(response, 500)
        assert body["type"] == "urn:earthx:job-failed:unknown"
        if kind:
            assert kind not in response.text

    async def test_a_finished_job_has_links_to_api_and_never_to_the_store(self, rig: Rig) -> None:
        job_id = await placed(rig)
        result_id = finish(rig.db, job_id)
        response = await rig.client.get(f"/processing/jobs/{job_id}/results")
        assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
        body = response.json()
        assert list(body) == ["result", "mask", "recipe"]
        base = f"/processing/jobs/{job_id}/results/"
        assert [body[key]["href"] for key in body] == [base + "result.tif", base + "mask.tif", base + "recipe.json"]
        assert body["result"]["type"] == "image/tiff; application=geotiff; profile=cloud-optimized"
        assert (body["result"]["length"], body["result"]["width"], body["result"]["height"]) == (12345, 64, 48)
        assert body["result"]["properties"]["proj:code"] == "EPSG:32632"
        for forbidden in (result_id, "localhost:3900", "objectstore", "X-Amz", "earthx/results", "c1:", "9.01"):
            assert forbidden not in response.text

    async def test_the_links_name_what_the_store_holds_and_what_api_builds(self) -> None:
        assert LINK_NAMES == ("result.tif", "mask.tif", "export.zip", "recipe.json")


def signed(response: httpx.Response) -> tuple[str, dict[str, list[str]]]:
    assert response.status_code == 303, response.text
    parts = urlsplit(response.headers["location"])
    return parts.path, parse_qs(parts.query)


class TestResultLinks:
    async def test_a_link_is_a_303_to_a_url_signed_just_now(self, rig: Rig) -> None:
        job_id = await placed(rig)
        result_id = finish(rig.db, job_id)
        response = await rig.client.get(f"/processing/jobs/{job_id}/results/result.tif")
        path, query = signed(response)
        assert response.headers["cache-control"] == "no-store" and response.content == b""
        assert response.headers["location"].startswith("http://localhost:3900/earthx/results/")
        assert path == f"/earthx/results/{result_id}/result.tif"
        assert int(query["X-Amz-Expires"][0]) == 900
        assert "sentinel-2-c1-l2a_scale_20260305.tif" in query["response-content-disposition"][0]
        again = await rig.client.get(f"/processing/jobs/{job_id}/results/result.tif")
        assert again.status_code == 303, "the link stays good, and each call signs afresh"

    async def test_the_mask_is_the_other_file_under_the_same_prefix(self, rig: Rig) -> None:
        job_id = await placed(rig)
        result_id = finish(rig.db, job_id)
        path, query = signed(await rig.client.get(f"/processing/jobs/{job_id}/results/mask.tif"))
        assert path == f"/earthx/results/{result_id}/mask.tif"
        assert "sentinel-2-c1-l2a_scale_20260305_mask.tif" in query["response-content-disposition"][0]

    async def test_the_url_never_lives_past_the_end_of_the_result(self, rig: Rig) -> None:
        job_id = await placed(rig)
        finish(rig.db, job_id, expires="5 minutes")
        _, query = signed(await rig.client.get(f"/processing/jobs/{job_id}/results/result.tif"))
        assert 290 <= int(query["X-Amz-Expires"][0]) <= 300

    @pytest.mark.parametrize("expires", ["59 seconds", "10 seconds", "0 seconds", "-1 second", "-6 days"])
    async def test_a_result_with_less_than_a_minute_left_or_none_is_a_410(self, rig: Rig, expires: str) -> None:
        job_id = await placed(rig)
        finish(rig.db, job_id, expires=expires)
        for tail in ("result.tif", "mask.tif", "recipe.json"):
            response = await rig.client.get(f"/processing/jobs/{job_id}/results/{tail}")
            body = problem(response, 410)
            assert body["type"] == "urn:earthx:gone" and response.headers["cache-control"] == "no-store"
            assert "location" not in response.headers

    @pytest.mark.parametrize("state", ["failed", "accepted", "running"])
    async def test_a_job_that_did_not_succeed_is_gone_at_the_end_of_its_life_not_failed_again(
        self, rig: Rig, state: str
    ) -> None:
        job_id = await placed(rig)
        if state == "failed":
            finish(rig.db, job_id, status="failed", kind="source_5xx", expires="-1 hour")
        else:
            rig.db.execute(
                "UPDATE public.earthx_run SET status = %s, expires_at = clock_timestamp() - interval '1 hour'", (state,)
            )
        for tail in ("result.tif", "mask.tif", "recipe.json"):
            response = await rig.client.get(f"/processing/jobs/{job_id}/results/{tail}")
            assert problem(response, 410)["type"] == "urn:earthx:gone"
        assert (await rig.client.get(f"/processing/jobs/{job_id}")).status_code == 404

    async def test_a_result_with_more_than_a_minute_left_is_still_linked(self, rig: Rig) -> None:
        job_id = await placed(rig)
        finish(rig.db, job_id, expires="90 seconds")
        _, query = signed(await rig.client.get(f"/processing/jobs/{job_id}/results/result.tif"))
        assert int(query["X-Amz-Expires"][0]) <= 90

    async def test_the_name_comes_from_dataset_operators_and_date_and_nothing_else(self, rig: Rig) -> None:
        plain = await placed(rig, order(steps=[]))
        scaled = await placed(rig)
        finish(rig.db, plain)
        finish(rig.db, scaled)
        for job_id, expected in (
            (plain, "sentinel-2-c1-l2a_export_20260305.tif"),
            (scaled, "sentinel-2-c1-l2a_scale_20260305.tif"),
        ):
            _, query = signed(await rig.client.get(f"/processing/jobs/{job_id}/results/result.tif"))
            assert query["response-content-disposition"] == [f'attachment; filename="{expected}"']

    async def test_the_name_has_no_area_hash_job_or_result_identifier(self, rig: Rig) -> None:
        job_id = await placed(rig)
        result_id = finish(rig.db, job_id)
        response = await rig.client.get(f"/processing/jobs/{job_id}/results/result.tif")
        disposition = signed(response)[1]["response-content-disposition"][0]
        for forbidden in (job_id, result_id, "c1:", "9.0", "47.0"):
            assert forbidden not in disposition

    async def test_a_link_is_a_hit_for_the_job_that_placed_it_only_by_its_own_identifier(self, rig: Rig) -> None:
        first = await placed(rig)
        finish(rig.db, first)
        second = (await place(rig)).json()["jobID"]
        a = signed(await rig.client.get(f"/processing/jobs/{first}/results/result.tif"))[0]
        b = signed(await rig.client.get(f"/processing/jobs/{second}/results/result.tif"))[0]
        assert a == b, "a cache hit serves the run's result"
        assert first not in a and second not in a, "and the prefix names neither job"


class TestRecipeJson:
    async def fetched(self, rig: Rig, job_id: str) -> tuple[httpx.Response, dict[str, Any]]:
        response = await rig.client.get(f"/processing/jobs/{job_id}/results/recipe.json")
        assert response.status_code == 200, response.text
        return response, json.loads(response.content)

    async def test_it_is_the_jobs_own_recipe_with_the_provenance_of_the_run(self, rig: Rig) -> None:
        job_id = await placed(rig)
        finish(rig.db, job_id)
        response, document = await self.fetched(rig, job_id)
        recipe_id = (await rig.client.get(f"/processing/jobs/{job_id}")).json()["recipeID"]
        assert response.headers["content-type"] == "application/json"
        assert response.headers["cache-control"] == "no-store"
        assert (
            response.headers["content-disposition"]
            == 'attachment; filename="sentinel-2-c1-l2a_scale_20260305_recipe.json"'
        )
        assert document["recipe_id"] == recipe_id
        assert document["steps"] == [SCALE_STEP | {"params": {"factor": 2.0, "label": None}}]
        assert document["inputs"][0]["groups"] == [["S2_A"]]
        provenance = document["provenance"]
        assert (provenance["execution"], provenance["kind"], provenance["self_attested"]) == ("cloud", "job", False)
        assert provenance["engine"] == RESULT["engine"] and provenance["scaling"] == RESULT["scaling"]
        assert provenance["finished"].startswith("2026-03-05T10:00:00")
        assert provenance["started"].startswith("2026-03-05T09:59:00")
        assert provenance["attribution"] and "2026" in provenance["attribution"][0]
        assert provenance["runner_version"] is None

    async def test_it_has_no_hash(self, rig: Rig) -> None:
        job_id = await placed(rig)
        finish(rig.db, job_id)
        text = (await self.fetched(rig, job_id))[0].text
        assert "c1:" not in text and not re.search(r"[0-9a-f]{64}", text)
        assert "hash" not in text.lower() and "cache_key" not in text

    async def test_it_is_written_the_way_the_crops_file_is(self, rig: Rig) -> None:
        job_id = await placed(rig)
        finish(rig.db, job_id)
        text = (await self.fetched(rig, job_id))[0].text
        assert text.endswith("\n") and text.startswith('{\n  "aoi"'), "two spaces, keys sorted"

    async def test_two_equal_orders_share_a_run_and_each_file_holds_its_own_recipe_id(self, rig: Rig) -> None:
        first = (await place(rig)).json()
        second = (await place(rig)).json()
        finish(rig.db, first["jobID"])
        one = (await self.fetched(rig, first["jobID"]))[1]
        two = (await self.fetched(rig, second["jobID"]))[1]
        assert one["recipe_id"] == first["recipeID"] and two["recipe_id"] == second["recipeID"]
        assert first["recipeID"] not in json.dumps(two) and second["recipeID"] not in json.dumps(one)

    async def test_a_cache_hit_shows_the_run_that_computed_it_and_still_its_own_recipe_id(self, rig: Rig) -> None:
        first = await placed(rig)
        finish(rig.db, first)
        second = (await place(rig)).json()
        document = (await self.fetched(rig, second["jobID"]))[1]
        assert document["recipe_id"] == second["recipeID"]
        assert document["provenance"]["finished"].startswith("2026-03-05T10:00:00")

    async def test_a_dataset_the_registry_no_longer_knows_still_gives_the_file_without_an_attribution(
        self, rig: Rig
    ) -> None:
        job_id = await placed(rig)
        finish(rig.db, job_id)
        api = replace_api(rig.api, registry=DatasetRegistry((DEM,)))
        async with client_for(api) as client:
            response = await client.get(f"/processing/jobs/{job_id}/results/recipe.json")
        assert response.status_code == 200 and response.json()["provenance"]["attribution"] == []


class TestDismissing:
    async def test_a_waiting_job_is_dismissed_at_once_and_is_gone_afterwards(self, rig: Rig) -> None:
        job_id = await placed(rig)
        response = await rig.client.delete(f"/processing/jobs/{job_id}")
        assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
        assert (response.json()["status"], response.json()["jobID"]) == ("dismissed", job_id)
        assert rig.db.execute("SELECT status FROM public.earthx_run").fetchone() == ("dismissed",)
        assert (await rig.client.get(f"/processing/jobs/{job_id}")).status_code == 404
        assert (await rig.client.delete(f"/processing/jobs/{job_id}")).status_code == 404

    async def test_a_running_job_is_asked_to_stop(self, rig: Rig) -> None:
        job_id = await placed(rig)
        rig.db.execute("UPDATE public.earthx_run SET status = 'running'")
        assert (await rig.client.delete(f"/processing/jobs/{job_id}")).json()["status"] == "dismissed"
        assert rig.db.execute("SELECT status, cancel_requested FROM public.earthx_run").fetchone() == ("running", True)

    async def test_dismissing_one_of_two_equal_orders_lets_the_other_run(self, rig: Rig) -> None:
        first, second = await placed(rig), await placed(rig)
        rig.db.execute("UPDATE public.earthx_run SET status = 'running'")
        assert (await rig.client.delete(f"/processing/jobs/{first}")).status_code == 200
        assert rig.db.execute("SELECT cancel_requested FROM public.earthx_run").fetchone() == (False,)
        assert (await rig.client.get(f"/processing/jobs/{second}")).json()["status"] == "running"
        assert (await rig.client.delete(f"/processing/jobs/{second}")).status_code == 200
        assert rig.db.execute("SELECT cancel_requested FROM public.earthx_run").fetchone() == (True,)

    async def test_dismissing_a_finished_job_keeps_the_result_another_job_may_be_served_from(self, rig: Rig) -> None:
        """adr/0015 §13, decided with M4-08a F5: the result stays until it expires."""
        first = await placed(rig)
        result_id = finish(rig.db, first)
        second = (await place(rig)).json()["jobID"]
        assert (await rig.client.delete(f"/processing/jobs/{first}")).json()["status"] == "dismissed"
        assert rig.db.execute("SELECT status, result_id FROM public.earthx_run").fetchone() == ("successful", result_id)
        path, _ = signed(await rig.client.get(f"/processing/jobs/{second}/results/result.tif"))
        assert path == f"/earthx/results/{result_id}/result.tif"
        assert (await rig.client.get(f"/processing/jobs/{first}/results/result.tif")).status_code == 404

    async def test_nobody_dismisses_a_job_by_knowing_the_same_order(self, rig: Rig) -> None:
        mine, other = await placed(rig), await placed(rig)
        await rig.client.delete(f"/processing/jobs/{other}")
        assert (await rig.client.get(f"/processing/jobs/{mine}")).json()["status"] == "accepted"


class TestWhatLogsAndHeadersCarry:
    async def lifecycle(self, rig: Rig) -> tuple[str, str]:
        job_id = (await place(rig, order(steps=[]))).json()["jobID"]
        result_id = finish(rig.db, job_id)
        for tail in ("", "/results", "/results/result.tif", "/results/mask.tif", "/results/recipe.json"):
            await rig.client.get(f"/processing/jobs/{job_id}{tail}")
        await rig.client.delete(f"/processing/jobs/{job_id}")
        await rig.client.get(f"/processing/jobs/{job_id}")
        return job_id, result_id

    async def test_the_access_log_names_the_route_and_never_the_job(
        self, rig: Rig, access_log_lines: list[str]
    ) -> None:
        job_id, result_id = await self.lifecycle(rig)
        assert not [line for line in access_log_lines if job_id in line or result_id in line]
        paths = {json.loads(line)["path"] for line in access_log_lines}
        assert "/processing/jobs/{jobID}" in paths and "/processing/jobs/{jobID}/results/result.tif" in paths
        assert "/processing/jobs/{jobID}/results/recipe.json" in paths

    async def test_the_access_log_hides_whatever_stands_where_an_identifier_would(
        self, rig: Rig, access_log_lines: list[str]
    ) -> None:
        await rig.client.get("/processing/jobs/not-an-identifier-but-secret")
        assert not [line for line in access_log_lines if "secret" in line]

    async def test_no_log_line_names_the_job_the_area_the_source_or_a_hash(
        self, rig: Rig, caplog: pytest.LogCaptureFixture
    ) -> None:
        # The platform's own loggers: production sets `botocore` and `httpx`, which write signatures
        # and full URLs at lower levels, to WARNING (earthx.logging, adr/0015 §9.2).
        with caplog.at_level(logging.DEBUG, logger="earthx"):
            job_id, result_id = await self.lifecycle(rig)
        text = "\n".join(own_log_text(record) for record in caplog.records)
        assert caplog.records
        for forbidden in (job_id, result_id, "9.01", "47.01", S2_HOST, "c1:", "1220S2_A", "secret"):
            assert forbidden not in text, forbidden

    async def test_a_placed_job_is_logged_by_its_recipe_not_its_job(
        self, rig: Rig, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.INFO, logger="earthx.api.processing"):
            body = (await place(rig)).json()
        record = next(r for r in caplog.records if r.getMessage() == "job placed")
        assert record.order_recipe_id == body["recipeID"] and body["jobID"] not in own_log_text(record)

    @pytest.mark.parametrize(
        "path",
        [
            f"/processing/jobs/{'A' * 22}",
            f"/processing/jobs/{'A' * 22}/results",
            f"/processing/jobs/{'A' * 22}/results/result.tif",
        ],
    )
    async def test_every_answer_under_jobs_is_no_store_even_a_404(self, rig: Rig, path: str) -> None:
        assert (await rig.client.get(path)).headers["cache-control"] == "no-store"

    async def test_the_documents_that_need_no_job_may_be_cached(self, rig: Rig) -> None:
        assert "cache-control" not in (await rig.client.get("/processing/conformance")).headers


class TestOtherDatasets:
    async def test_the_dem_job_carries_the_dem_in_its_file_name(self, rig: Rig) -> None:
        rig.source.items[("cop-dem-glo-30", "DEM_N47_E009")] = dem_item()
        job_id = await placed(rig, order("cop-dem-glo-30", (("DEM_N47_E009",),), ("data",)))
        finish(rig.db, job_id)
        _, query = signed(await rig.client.get(f"/processing/jobs/{job_id}/results/result.tif"))
        assert "cop-dem-glo-30_scale_20260305.tif" in query["response-content-disposition"][0]


class TestWhatGoesWrongInside:
    """Failures that are the platform's, answered in the form of the API and without a text of the driver or the store."""

    async def test_a_store_that_cannot_sign_is_a_503_that_names_nothing(
        self, rig: Rig, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def broken(*args: Any, **kwargs: Any) -> str:
            raise StoreUnavailable("http://objectstore:3900 GKtestaccesskey0001 refused")

        monkeypatch.setattr("earthx.api.processing_route.signed_download", broken)
        job_id = await placed(rig)
        finish(rig.db, job_id)
        response = await rig.client.get(f"/processing/jobs/{job_id}/results/result.tif")
        problem(response, 503)
        assert response.headers["retry-after"] == "5"
        assert "objectstore" not in response.text and "GKtest" not in response.text

    async def test_a_queue_that_cannot_place_the_job_is_a_503(self, rig: Rig, monkeypatch: pytest.MonkeyPatch) -> None:
        def busy(*args: Any, **kwargs: Any) -> str:
            raise RuntimeError("the queue could not place the order; try again")

        monkeypatch.setattr("earthx.api.processing_route.submit", busy)
        response = await place(rig)
        problem(response, 503)
        assert response.headers["retry-after"] == "5"

    async def test_a_recipe_id_that_is_taken_is_a_500_in_the_form_of_the_api_without_the_value(
        self, rig: Rig, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def taken(*args: Any, **kwargs: Any) -> str:
            raise RecipeIdTaken("a recipe with this recipe_id exists")

        monkeypatch.setattr("earthx.api.processing_route.submit", taken)
        response = await place(rig)
        assert problem(response, 500)["detail"] == "the job could not be placed"
        assert response.headers["cache-control"] == "no-store"

    @pytest.mark.parametrize(
        "path",
        [
            "/processing/jobs/{id}/results/a/b",
            "/processing/jobs/{id}/results/result.tif/more",
            "/processing/jobs/{id}/x",
            "/processing/jobs//{id}",
            "/processing/jobs/a/b/c/d",
        ],
    )
    @pytest.mark.parametrize("method", ["GET", "DELETE"])
    async def test_a_path_under_jobs_that_is_no_route_is_the_same_404_as_a_job_that_is_not_there(
        self, rig: Rig, path: str, method: str
    ) -> None:
        job_id = await placed(rig)
        response = await rig.client.request(method, path.replace("{id}", job_id))
        assert problem(response, 404)["type"].endswith("/no-such-job")
        assert response.headers["cache-control"] == "no-store"
        assert job_id not in response.text

    async def test_the_wrong_method_on_a_route_is_still_a_405(self, rig: Rig) -> None:
        job_id = await placed(rig)
        assert (await rig.client.post(f"/processing/jobs/{job_id}")).status_code in (404, 405)
        assert (await rig.client.put(f"/processing/jobs/{job_id}")).status_code in (404, 405)


class TestTheNameOfADownload:
    """The name is built from the job's own recipe; a recipe of another shape must not break the link."""

    def status(self) -> Any:
        from earthx.jobs.submit import JobStatus

        created = datetime(2026, 1, 2, 3, 4, tzinfo=UTC)
        return JobStatus(
            job_id="A" * 22, recipe_id="B" * 22, status="successful", progress=100, created_at=created,
            started_at=None, finished_at=None, expires_at=created, error_kind=None, result_id="C" * 22, result={},
        )  # fmt: skip

    @pytest.mark.parametrize(
        "body", [None, {}, {"inputs": []}, {"inputs": [{}], "steps": []}, {"inputs": "x", "steps": 3}]
    )
    def test_a_recipe_of_another_shape_gives_the_plain_name_of_the_day(self, body: Any) -> None:
        from earthx.api.processing_route import _download_name

        assert _download_name(body, self.status(), ".tif") == "result_export_20260102.tif"

    def test_the_day_is_the_runs_end_in_utc_else_the_jobs_creation(self) -> None:
        from dataclasses import replace

        from earthx.api.processing_route import _download_name

        body = {"inputs": [{"dataset": "d"}], "steps": []}
        late = replace(self.status(), finished_at=datetime(2026, 3, 5, 23, 30, tzinfo=timezone(timedelta(hours=-5))))
        assert _download_name(body, late, ".tif") == "d_export_20260306.tif"

    def test_a_dataset_name_that_the_store_would_refuse_is_cleaned_and_many_steps_are_counted(self) -> None:
        from earthx.api.processing_route import _download_name
        from earthx.objectstore.results import _check_filename

        body = {"inputs": [{"dataset": "we ird/na\u00efme" + "x" * 200}], "steps": [{"op": "a" * 30}, {"op": "b" * 30}]}
        name = _download_name(body, self.status(), "_recipe.json")
        _check_filename(name)  # the store's own rule
        assert "2-steps" in name and name.endswith("_20260102_recipe.json")


# --- an export (M4-11a) ------------------------------------------------------------

EXPORT_RESULT = {
    "files": ["export.zip"],
    "members": ["red.tif", "red_mask.tif", "aoi.geojson", "recipe.json", "citation.bib", "ATTRIBUTION.txt"],
    "groups": 1,
    "assets": 1,
    "blocks": 3,
    "engine": RESULT["engine"],
    "scaling": [],
    "attribution": ["Contains modified Copernicus Sentinel data 2025"],
    "started": "2026-03-05T09:58:30+00:00",
    "finished": "2026-03-05T09:59:45+00:00",
    "bytes": 54321,
}


def export_order() -> dict[str, Any]:
    return order(assets=("red",), steps=[], output=CROP)


class TestAnExport:
    async def test_two_equal_exports_get_runs_of_their_own_with_their_side_files(self, rig: Rig) -> None:
        await placed(rig, export_order())
        await placed(rig, export_order())
        rows = rig.db.execute("SELECT cacheable, attachments FROM public.earthx_run ORDER BY run_id").fetchall()
        assert [cacheable for cacheable, _ in rows] == [False, False]
        for _, attachments in rows:
            assert set(attachments["files"]) == {"ATTRIBUTION.txt", "citation.bib", "aoi.geojson"}

    async def test_the_origin_of_a_place_aoi_goes_into_the_side_files(self, rig: Rig) -> None:
        response = await rig.client.post(
            EXECUTION, json={"inputs": {"recipe": export_order(), "aoiProvenance": PLACE}}
        )
        assert response.status_code == 201, response.text
        (attachments,) = rig.db.execute("SELECT attachments FROM public.earthx_run").fetchone()  # type: ignore[misc]
        assert "AOI geometry: © OpenStreetMap contributors" in attachments["files"]["ATTRIBUTION.txt"]
        assert json.loads(attachments["files"]["aoi.geojson"])["properties"] == PLACE
        (body,) = rig.db.execute("SELECT body FROM public.earthx_recipe").fetchone()  # type: ignore[misc]
        assert "properties" not in body["aoi"] and "OpenStreetMap" not in json.dumps(body)

    @pytest.mark.parametrize(
        "provenance",
        [
            {},
            {"other": "x"},
            {"source": ""},
            {"source": "x" * 201},
            {"source": "two\nlines"},
            {"source": " padded"},
            {"source": "right\u202eto left"},
            {"source": "zero\u200bwidth"},
            {"source": 7},
            "© OpenStreetMap",
            {"href": "https://example.invalid/provenance.json"},
            {"value": {"source": "x"}},
        ],
    )
    async def test_a_malformed_origin_is_a_400_and_nothing_is_fetched(self, rig: Rig, provenance: Any) -> None:
        response = await rig.client.post(
            EXECUTION, json={"inputs": {"recipe": export_order(), "aoiProvenance": provenance}}
        )
        problem(response, 400)
        untouched(rig)

    @pytest.mark.parametrize(("document", "name"), [("export", "result"), ("export", "mask"), ("raster", "export")])
    async def test_outputs_name_only_what_a_job_of_this_kind_has(self, rig: Rig, document: str, name: str) -> None:
        recipe = export_order() if document == "export" else order()
        response = await rig.client.post(EXECUTION, json={"inputs": {"recipe": recipe}, "outputs": {name: {}}})
        assert "outputs names" in problem(response, 400)["detail"]
        untouched(rig)

    async def test_an_export_may_ask_for_its_own_outputs(self, rig: Rig) -> None:
        outputs = {"export": {"transmissionMode": "reference"}, "recipe": {}}
        response = await rig.client.post(EXECUTION, json={"inputs": {"recipe": export_order()}, "outputs": outputs})
        assert response.status_code == 201, response.text

    async def test_a_lone_surrogate_in_the_origin_is_a_400(self, rig: Rig) -> None:
        """Valid JSON text, no UTF-8 form: it may not reach ATTRIBUTION.txt (review of M4-11a)."""
        body = json.dumps({"inputs": {"recipe": export_order(), "aoiProvenance": {"attribution": "SURROGATE"}}})
        raw = body.replace("SURROGATE", "a\\ud800b").encode("ascii")
        response = await rig.client.post(EXECUTION, content=raw, headers={"content-type": "application/json"})
        problem(response, 400)
        untouched(rig)

    async def test_an_origin_with_a_raster_order_is_a_400(self, rig: Rig) -> None:
        response = await rig.client.post(EXECUTION, json={"inputs": {"recipe": order(), "aoiProvenance": PLACE}})
        assert problem(response, 400)["type"].endswith(":order")

    async def test_the_results_are_the_zip_and_the_recipe(self, rig: Rig) -> None:
        job_id = await placed(rig, export_order())
        finish(rig.db, job_id, result=EXPORT_RESULT)
        document = (await rig.client.get(f"/processing/jobs/{job_id}/results")).json()
        assert list(document) == ["export", "recipe"]
        assert document["export"]["type"] == "application/zip" and document["export"]["length"] == 54321

    async def test_the_zip_link_is_a_303_named_by_dataset_export_and_date(self, rig: Rig) -> None:
        job_id = await placed(rig, export_order())
        result_id = finish(rig.db, job_id, result=EXPORT_RESULT)
        path, query = signed(await rig.client.get(f"/processing/jobs/{job_id}/results/export.zip"))
        assert path == f"/earthx/results/{result_id}/export.zip"
        assert "sentinel-2-c1-l2a_export_20260305.zip" in query["response-content-disposition"][0]

    async def test_a_name_of_the_other_output_is_a_404_either_way(self, rig: Rig) -> None:
        export_job = await placed(rig, export_order())
        finish(rig.db, export_job, result=EXPORT_RESULT)
        raster_job = await placed(rig)
        finish(rig.db, raster_job)
        for job_id, name in ((export_job, "result.tif"), (export_job, "mask.tif"), (raster_job, "export.zip")):
            response = await rig.client.get(f"/processing/jobs/{job_id}/results/{name}")
            assert problem(response, 404)["type"] == "urn:earthx:no-such-result"

    async def test_the_recipe_link_carries_the_times_the_export_wrote_into_its_zip(self, rig: Rig) -> None:
        job_id = await placed(rig, export_order())
        finish(rig.db, job_id, result=EXPORT_RESULT)
        document = (await rig.client.get(f"/processing/jobs/{job_id}/results/recipe.json")).json()
        assert document["provenance"]["started"].startswith("2026-03-05T09:58:30")
        assert document["provenance"]["finished"].startswith("2026-03-05T09:59:45")
        assert document["output"]["kind"] == "crop" and set(document["inputs"][0]["footprints"]) == {"S2_A"}

    async def test_the_recipe_link_is_the_file_in_the_zip_whatever_the_registry_says_now(self, rig: Rig) -> None:
        """Accepted in one year, finished in the next: the link repeats the export's attribution (review, M4-11a)."""
        job_id = await placed(rig, export_order())
        finish(rig.db, job_id, result=EXPORT_RESULT)
        served = (await rig.client.get(f"/processing/jobs/{job_id}/results/recipe.json")).content
        (body,) = rig.db.execute(  # type: ignore[misc]
            "SELECT r.body FROM public.earthx_recipe r JOIN public.earthx_job j USING (recipe_id) WHERE j.job_id = %s",
            (job_id,),
        ).fetchone()
        written = job_recipe_document(
            body,
            attribution=EXPORT_RESULT["attribution"],
            result=EXPORT_RESULT,
            started=datetime.fromisoformat(EXPORT_RESULT["started"]),
            finished=datetime.fromisoformat(EXPORT_RESULT["finished"]),
        )
        assert served == written
        assert json.loads(served)["provenance"]["attribution"] == ["Contains modified Copernicus Sentinel data 2025"]
