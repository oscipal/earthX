"""The documents of the job API that need no job (M4-08b; adr/0014 §9, §15d).

The API follows the form of OGC API – Processes and claims no conformance (Otto, F4): the
tests keep that claim honest in both directions — nothing declared, and nothing said that
the platform does not do.
"""

from __future__ import annotations

import json
import re
from dataclasses import replace
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from earthx.api.processing_docs import FORM_NOTE, OUTPUTS, order_schema
from earthx.api.processing_route import router
from earthx.catalog.datasets import REGISTRY
from earthx.catalog.registry import DatasetRegistry, LicenseTier
from earthx.processing.errors import RecipeInvalid
from earthx.processing.operators import REGISTRY as REAL_OPERATORS
from earthx.processing.operators import OperatorRegistry, Tier
from earthx.processing.recipe import parse_request
from tests.earthx.api.conftest import build_app
from tests.earthx.api.test_intake import SCALE_STEP, order
from tests.earthx.processing.testops import COARSEN, OPERATORS, SCALE

pytestmark = pytest.mark.anyio

S2 = REGISTRY.get("sentinel-2-c1-l2a")


def problem(response: httpx.Response) -> dict[str, Any]:
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert set(body) == {"type", "title", "status", "detail"}
    assert body["status"] == response.status_code
    return body


class TestLandingPage:
    async def test_it_links_the_api_description_the_conformance_and_the_processes(
        self, docs_client: httpx.AsyncClient
    ) -> None:
        response = await docs_client.get("/processing/")
        assert response.status_code == 200
        links = {link["rel"]: link["href"] for link in response.json()["links"]}
        assert links["self"] == "/processing/"
        assert links["service-desc"] == "/processing/api"
        assert links["http://www.opengis.net/def/rel/ogc/1.0/conformance"] == "/processing/conformance"
        assert links["http://www.opengis.net/def/rel/ogc/1.0/processes"] == "/processing/processes"

    async def test_it_says_in_words_that_no_conformance_is_claimed(self, docs_client: httpx.AsyncClient) -> None:
        text = (await docs_client.get("/processing/")).json()["description"]
        assert "follows the form of OGC API – Processes, no conformance claimed" in text
        assert FORM_NOTE in text

    async def test_the_links_follow_the_root_path_of_a_proxy(self, docs_client: httpx.AsyncClient) -> None:
        app = build_app(None)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, root_path="/earthx"), base_url="http://test"
        ) as client:
            links = (await client.get("/processing/")).json()["links"]
        assert {link["href"] for link in links} == {
            "/earthx/processing/",
            "/earthx/processing/api",
            "/earthx/processing/conformance",
            "/earthx/processing/processes",
        }


class TestConformance:
    """F4: no class is declared, because the platform does not take an input by reference (B8)."""

    async def test_the_list_is_empty(self, docs_client: httpx.AsyncClient) -> None:
        response = await docs_client.get("/processing/conformance")
        assert response.status_code == 200
        assert response.json() == {"conformsTo": []}

    async def test_not_even_json_or_dismiss_is_declared(self, docs_client: httpx.AsyncClient) -> None:
        text = (await docs_client.get("/processing/conformance")).text
        assert "/conf/" not in text and "ogcapi-processes" not in text and "dismiss" not in text


class TestApiDescription:
    async def test_it_describes_the_routes_under_the_prefix_and_no_others(self, docs_client: httpx.AsyncClient) -> None:
        response = await docs_client.get("/processing/api")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/vnd.oai.openapi+json")
        schema = response.json()
        assert schema["openapi"].startswith("3.1")
        assert FORM_NOTE in schema["info"]["description"]
        paths = set(schema["paths"])
        assert {
            "/processing/",
            "/processing/conformance",
            "/processing/processes",
            "/processing/processes/{process_id}",
            "/processing/processes/{process_id}/execution",
            "/processing/processes/{process_id}/estimate",
            "/processing/jobs/{jobID}",
            "/processing/jobs/{jobID}/results",
            "/processing/jobs/{jobID}/results/{name}",
            "/processing/jobs/{jobID}/events",
        } <= paths
        assert "/processing/api" not in paths, "the description does not describe itself"

    async def test_there_is_no_job_list(self, docs_client: httpx.AsyncClient) -> None:
        paths = (await docs_client.get("/processing/api")).json()["paths"]
        assert "/processing/jobs" not in paths
        assert (await docs_client.get("/processing/jobs", follow_redirects=True)).status_code == 404

    async def test_it_does_not_describe_what_outside_the_prefix_does(self) -> None:
        app = build_app(None)

        @app.get("/elsewhere")
        def elsewhere() -> dict:
            return {}

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            assert "/elsewhere" not in (await client.get("/processing/api")).json()["paths"]


class TestProcesses:
    async def test_the_list_holds_one_process(self, docs_client: httpx.AsyncClient) -> None:
        body = (await docs_client.get("/processing/processes")).json()
        assert [entry["id"] for entry in body["processes"]] == ["recipe"]
        entry = body["processes"][0]
        assert entry["jobControlOptions"] == ["async-execute", "dismiss"]
        assert entry["outputTransmission"] == ["reference"]
        assert FORM_NOTE in entry["description"]

    @pytest.mark.parametrize("limit", ["1", "10", "10000"])
    async def test_a_limit_in_range_is_taken(self, docs_client: httpx.AsyncClient, limit: str) -> None:
        assert (await docs_client.get("/processing/processes", params={"limit": limit})).status_code == 200

    @pytest.mark.parametrize("limit", ["0", "-1", "10001", "x", "", "1.5", "1e3"])
    async def test_a_limit_out_of_range_is_a_400_of_this_apis_own_form(
        self, docs_client: httpx.AsyncClient, limit: str
    ) -> None:
        response = await docs_client.get("/processing/processes", params={"limit": limit})
        assert response.status_code == 400
        assert problem(response)["type"] == "about:blank"

    async def test_the_description_has_the_order_as_its_one_input_and_three_outputs(
        self, docs_client: httpx.AsyncClient
    ) -> None:
        body = (await docs_client.get("/processing/processes/recipe")).json()
        assert list(body["inputs"]) == ["recipe"]
        assert body["inputs"]["recipe"]["minOccurs"] == body["inputs"]["recipe"]["maxOccurs"] == 1
        assert list(body["outputs"]) == list(OUTPUTS)
        assert FORM_NOTE in body["description"]
        assert "refused" in body["inputs"]["recipe"]["description"], "an input by reference is named as refused"

    async def test_another_process_is_a_404_of_the_ogc_kind(self, docs_client: httpx.AsyncClient) -> None:
        response = await docs_client.get("/processing/processes/other")
        assert response.status_code == 404
        assert problem(response)["type"].endswith("/no-such-process")


class TestOrderSchema:
    """K8: the panel reads this; it is built from the models the order is validated with."""

    def test_it_is_json_schema_2020_12(self) -> None:
        assert order_schema(OPERATORS)["$schema"] == "https://json-schema.org/draft/2020-12/schema"

    def test_the_steps_are_a_union_over_the_operators_in_one_version_each(self) -> None:
        schema = order_schema(OPERATORS)
        refs = [entry["$ref"] for entry in schema["properties"]["steps"]["items"]["oneOf"]]
        # The test registry holds the real operators too, and its own two (testops).
        assert refs == [
            "#/$defs/step_band_math_v1",
            "#/$defs/step_coarsen_v1",
            "#/$defs/step_reproject_v2",
            "#/$defs/step_scale_v1",
        ]
        step = schema["$defs"]["step_scale_v1"]
        assert step["properties"]["op"] == {"const": "scale"}
        assert step["properties"]["op_version"] == {"const": 1}
        assert set(step["properties"]["params"]["properties"]) == {"factor", "label"}
        assert step["additionalProperties"] is False
        assert schema["properties"]["steps"]["items"]["discriminator"] == {"propertyName": "op"}

    def test_an_operator_that_does_not_run_as_a_job_is_not_offered(self) -> None:
        pixel_only = replace(SCALE, tiers=frozenset({Tier.T1}))
        names = {
            key for key in order_schema(OperatorRegistry([pixel_only, COARSEN]))["$defs"] if key.startswith("step_")
        }
        assert names == {"step_coarsen_v1"}

    def test_the_real_registry_offers_reproject(self) -> None:
        schema = order_schema(REAL_OPERATORS)
        assert "step_reproject_v2" in schema["$defs"]
        params = schema["$defs"]["step_reproject_v2"]["properties"]["params"]
        assert set(params["required"]) == {"crs", "resolution", "resampling"}

    def test_every_reference_resolves_and_nothing_stays_unused(self) -> None:
        for registry in (OPERATORS, REAL_OPERATORS):
            schema = order_schema(registry)
            text = json.dumps(schema)
            refs = set(re.findall(r'"\$ref": "#/\$defs/([^"]+)"', text))
            assert refs == set(schema["$defs"])

    def test_it_limits_what_the_intake_limits(self) -> None:
        schema = order_schema(OPERATORS)
        assert schema["properties"]["inputs"]["maxItems"] == 1
        assert schema["$defs"]["InputRequest"]["properties"]["assets"]["maxItems"] == 16
        assert schema["properties"]["steps"]["maxItems"] == 16

    def test_a_job_has_a_raster_output_and_no_crop(self) -> None:
        schema = order_schema(OPERATORS)
        assert schema["properties"]["output"] == {"$ref": "#/$defs/RasterOutput"}
        assert "CropOutput" not in schema["$defs"]

    def test_it_asks_for_what_the_order_models_ask_for(self) -> None:
        schema = order_schema(OPERATORS)
        assert set(schema["required"]) == {"recipe_version", "inputs", "aoi", "steps", "output"}
        assert schema["additionalProperties"] is False
        parse_request(json.dumps(order()), OPERATORS)  # the order the schema is for is one the intake reads

    def test_for_a_dataset_it_offers_what_applies_and_fixes_the_dataset(self) -> None:
        schema = order_schema(OPERATORS, S2)
        assert schema["$defs"]["InputRequest"]["properties"]["dataset"] == {"const": S2.dataset_id, "title": "Dataset"}
        assert "step_scale_v1" in schema["$defs"]

    def test_for_a_dataset_that_does_not_reach_processing_no_step_is_offered(self) -> None:
        display = replace(S2, license=replace(S2.license, tier=LicenseTier.DISPLAY))
        schema = order_schema(OPERATORS, display)
        assert schema["properties"]["steps"] == {"type": "array", "title": "Steps", "maxItems": 0}
        assert not [key for key in schema["$defs"] if key.startswith("step_")]

    def test_it_is_built_fresh_so_a_dataset_filter_never_changes_the_other(self) -> None:
        full = order_schema(OPERATORS)
        order_schema(OPERATORS, S2)
        assert order_schema(OPERATORS) == full


class TestWhatThePanelReads:
    """M4-13a: the schema says which steps can be a tile, and how the variables of a Zarr asset are named."""

    def test_every_step_names_its_tiers_and_kind_as_the_operator_has_them(self) -> None:
        schema = order_schema(REAL_OPERATORS)
        for _, operator in sorted(REAL_OPERATORS.items()):
            definition = schema["$defs"][f"step_{operator.op}_v{operator.op_version}"]
            assert definition["x-earthx-tiers"] == sorted(tier.value for tier in operator.tiers)
            assert definition["x-earthx-kind"] == operator.kind

    def test_the_real_operators_are_what_the_planner_expects(self) -> None:
        schema = order_schema(REAL_OPERATORS)
        assert schema["$defs"]["step_band_math_v1"]["x-earthx-tiers"] == ["T1", "T2"]
        assert schema["$defs"]["step_band_math_v1"]["x-earthx-kind"] == "pixel"
        assert schema["$defs"]["step_reproject_v2"]["x-earthx-tiers"] == ["T2"]
        assert schema["$defs"]["step_reproject_v2"]["x-earthx-kind"] == "grid"

    def test_an_order_cannot_use_the_annotations_as_parameters(self) -> None:
        step = {**SCALE_STEP, "x-earthx-tiers": ["T1"]}
        with pytest.raises(RecipeInvalid):
            parse_request(json.dumps(order(steps=[step])), OPERATORS)

    def test_the_separator_of_a_zarr_dataset_is_in_the_schema_of_its_assets(self) -> None:
        eopf = REGISTRY.get("sentinel-2-l2a-zarr3")
        assets = order_schema(OPERATORS, eopf)["$defs"]["InputRequest"]["properties"]["assets"]
        assert assets["x-earthx-variable-separator"] == eopf.zarr.variable_separator != ""

    def test_a_cog_dataset_has_no_separator_and_nothing_is_guessed(self) -> None:
        for dataset in ("sentinel-2-c1-l2a", "cop-dem-glo-30"):
            assets = order_schema(OPERATORS, REGISTRY.get(dataset))["$defs"]["InputRequest"]["properties"]["assets"]
            assert "x-earthx-variable-separator" not in assets

    def test_without_a_dataset_there_is_no_separator(self) -> None:
        assets = order_schema(OPERATORS)["$defs"]["InputRequest"]["properties"]["assets"]
        assert "x-earthx-variable-separator" not in assets

    def test_the_separator_of_a_dataset_never_changes_the_schema_of_another(self) -> None:
        order_schema(OPERATORS, REGISTRY.get("sentinel-2-l2a-zarr3"))
        assets = order_schema(OPERATORS, S2)["$defs"]["InputRequest"]["properties"]["assets"]
        assert "x-earthx-variable-separator" not in assets


class TestProcessPerDataset:
    async def test_the_filter_names_the_dataset(self, docs_client: httpx.AsyncClient) -> None:
        body = (await docs_client.get("/processing/processes/recipe", params={"dataset": S2.dataset_id})).json()
        assert body["inputs"]["recipe"]["schema"]["$defs"]["InputRequest"]["properties"]["dataset"]["const"] == (
            S2.dataset_id
        )

    async def test_an_unknown_dataset_is_a_400_that_names_it(self, docs_client: httpx.AsyncClient) -> None:
        response = await docs_client.get("/processing/processes/recipe", params={"dataset": "no-such-dataset"})
        assert response.status_code == 400
        assert "no-such-dataset" in problem(response)["detail"]

    async def test_a_long_unknown_name_is_cut_in_the_answer(self, docs_client: httpx.AsyncClient) -> None:
        response = await docs_client.get("/processing/processes/recipe", params={"dataset": "x" * 500})
        assert response.status_code == 400
        assert len(problem(response)["detail"]) < 200


class TestWithoutAQueue:
    @pytest.mark.parametrize(
        ("method", "path"),
        [
            ("GET", "/processing/jobs/" + "A" * 22),
            ("DELETE", "/processing/jobs/" + "A" * 22),
            ("GET", "/processing/jobs/" + "A" * 22 + "/results"),
            ("GET", "/processing/jobs/" + "A" * 22 + "/results/result.tif"),
            ("GET", "/processing/jobs/" + "A" * 22 + "/events"),
        ],
    )
    async def test_the_job_routes_say_so_with_a_503(
        self, docs_client: httpx.AsyncClient, method: str, path: str
    ) -> None:
        response = await docs_client.request(method, path)
        assert response.status_code == 503
        assert problem(response)["detail"] == "the job API is not available"

    async def test_placing_a_job_says_so_too(self, docs_client: httpx.AsyncClient) -> None:
        response = await docs_client.post("/processing/processes/recipe/execution", json={"inputs": {}})
        assert response.status_code == 503

    async def test_estimating_an_order_says_so_too(self, docs_client: httpx.AsyncClient) -> None:
        response = await docs_client.post("/processing/processes/recipe/estimate", json={"inputs": {}})
        assert response.status_code == 503


class TestTheRealApp:
    def test_api_main_mounts_the_router_and_hands_it_the_operators(self) -> None:
        from earthx.api.main import build_app as build_api

        app: FastAPI = build_api(DatasetRegistry((S2,)), operators=OPERATORS)
        assert app.state.earthx_operators is OPERATORS
        assert app.state.earthx_job_api is None, "set by the lifespan, once the pools are open"
        # This FastAPI keeps an included router as one route that holds the router itself.
        assert any(getattr(route, "original_router", None) is router for route in app.routes)
