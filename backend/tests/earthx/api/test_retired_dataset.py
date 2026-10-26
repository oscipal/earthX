"""A dataset that left the registry answers ``410`` with its reason, before anything is asked of a source (adr/0017 §8).

Nothing reaches a network: the item source of each test refuses to be called, and the gateway is the synthetic one of
`tests/earthx/api/conftest.py`. The retired id is the one on the real list, `catalog/datasets.py`.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from earthx.access import download as dl
from earthx.adapters import ADAPTER_SPECS
from earthx.api.coverage_route import build_router
from earthx.api.processing_route import GONE, JobApi
from earthx.api.tiler import build_app as build_tiler_app
from earthx.catalog.datasets import REGISTRY, RETIRED
from earthx.catalog.registry import DatasetRegistry
from earthx.objectstore.results import Store
from tests.earthx.api.conftest import Rig
from tests.earthx.api.test_intake import order
from tests.earthx.api.test_permalink_route import PATH as PERMALINKS
from tests.earthx.api.test_permalink_route import body as permalink_body
from tests.earthx.api.test_processing_route import EXECUTION, client_for, finish, place, placed, replace_api
from tests.earthx.api.test_result_zip_route import (
    FOLDER,
    MASK,
    RASTER,
    facts,
    mocked,  # noqa: F401 - fixture
    opened,
    put,
)
from tests.earthx.objectstore.conftest import store  # noqa: F401 - fixture

pytestmark = pytest.mark.anyio

ID = RETIRED[0].dataset_id
REASON = RETIRED[0].message
ESTIMATE = "/processing/processes/recipe/estimate"
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


def retired_order(**override: Any) -> dict[str, Any]:
    return order(ID, assets=("SR_10m:b04", "SR_10m:b08"), **override)


class TestTilesAndCoverage:
    @pytest.fixture
    def client(self) -> TestClient:
        called: list[str] = []

        async def item_source(dataset_id: str, item_id: str) -> dict[str, Any]:
            called.append(item_id)
            raise AssertionError("a retired dataset must not reach the source")

        app = build_tiler_app()
        app.state.earthx_item_source = item_source
        app.state.earthx_cache_pool = None
        app.state.called = called
        return TestClient(app)

    @pytest.mark.parametrize("tail", ["statistics", "info"])
    def test_a_read_of_an_item_is_a_410_with_the_reason_and_asks_nobody(self, client: TestClient, tail: str) -> None:
        response = client.get(f"/collections/{ID}/items/ANY/{tail}", params={"asset": "SR_10m:b04"})
        assert response.status_code == 410
        assert response.json()["detail"] == REASON
        assert client.app.state.called == []

    def test_an_unknown_dataset_stays_a_404_that_says_nothing_of_retirement(self, client: TestClient) -> None:
        response = client.get("/collections/never-existed/items/ANY/statistics", params={"asset": "visual"})
        assert response.status_code == 404 and "retired" not in response.json()["detail"]

    def test_the_coverage_is_a_410_with_the_reason(self) -> None:
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(build_router(REGISTRY, ADAPTER_SPECS))
        response = TestClient(app).get(f"/coverage/{ID}", params={"zoom": 5})
        assert response.status_code == 410 and response.json()["detail"] == REASON


class TestTheProcessing:
    async def test_the_description_of_the_process_for_it_is_a_410(self, rig: Rig) -> None:
        response = await rig.client.get("/processing/processes/recipe", params={"dataset": ID})
        assert response.status_code == 410
        body = response.json()
        assert body["type"] == GONE and body["detail"] == REASON

    async def test_an_estimate_is_a_410_before_any_item_is_asked_for(self, rig: Rig) -> None:
        response = await rig.client.post(ESTIMATE, json={"inputs": {"recipe": retired_order()}})
        assert response.status_code == 410
        assert REASON in response.text

    async def test_placing_an_order_is_a_410_and_creates_no_job(self, rig: Rig) -> None:
        response = await place(rig, retired_order())
        assert response.status_code == 410 and REASON in response.text
        row = rig.db.execute("SELECT count(*) FROM public.earthx_job").fetchone()
        assert row is not None and row[0] == 0

    async def test_the_reason_is_the_same_text_in_every_place(self, rig: Rig) -> None:
        estimate = await rig.client.post(ESTIMATE, json={"inputs": {"recipe": retired_order()}})
        execution = await rig.client.post(EXECUTION, json={"inputs": {"recipe": retired_order()}})
        assert estimate.json()["detail"] == execution.json()["detail"] == REASON


class TestPermalinks:
    async def test_a_new_link_for_it_is_not_made(self, rig: Rig) -> None:
        response = await rig.client.post(PERMALINKS, json=permalink_body(retired_order()))
        assert response.status_code == 410 and response.json()["detail"] == REASON
        row = rig.db.execute("SELECT count(*) FROM public.earthx_permalink").fetchone()
        assert row is not None and row[0] == 0

    async def test_a_stored_link_still_opens_because_the_order_is_the_users(self, rig: Rig) -> None:
        made = (await rig.client.post(PERMALINKS, json=permalink_body())).json()
        rig.db.execute(
            "UPDATE public.earthx_permalink SET body = jsonb_set(body, '{order,inputs,0,dataset}', to_jsonb(%s::text))",
            (ID,),
        )
        response = await rig.client.get(f"{PERMALINKS}/{made['id']}")
        assert response.status_code == 200
        stored = response.json()["order"]
        assert stored["inputs"][0]["dataset"] == ID
        # Starting it is what is refused.
        assert (await rig.client.post(EXECUTION, json={"inputs": {"recipe": stored}})).status_code == 410


class TestAFinishedJob:
    """A job placed before the entry left runs to its end, and its files keep attribution, terms and citation.

    The recipe of a job carries a hash of its dataset id, so the stored job cannot be pointed at the retired id.
    The job is placed on the COG dataset and the registry of the app is the one in which *that* id is retired,
    with the record of the real list (its licence block, its title, its DOI).
    """

    GONE = replace(RETIRED[0], dataset_id="sentinel-2-c1-l2a", successor="cop-dem-glo-30")

    async def finished(self, rig: Rig) -> tuple[str, JobApi]:
        job_id = await placed(rig)
        result = dict(RESULT, files_meta={"result.tif": facts(RASTER), "mask.tif": facts(MASK)})
        result_id = finish(rig.db, job_id, result=result)
        put(rig, result_id, "result.tif", RASTER)
        put(rig, result_id, "mask.tif", MASK)
        registry = DatasetRegistry((REGISTRY.get("cop-dem-glo-30"),), retired=(self.GONE,))
        return job_id, replace_api(rig.api, registry=registry)

    async def test_the_zip_holds_the_notice_and_the_citation(self, mocked: Store, rig: Rig) -> None:  # noqa: F811
        job_id, api = await self.finished(rig)
        async with client_for(api) as client:
            response = await client.get(f"/processing/jobs/{job_id}/results/result.zip")
        assert response.status_code == 200
        archive = opened(response.content)
        names = [name.removeprefix(f"{FOLDER}/") for name in archive.namelist()]
        assert dl.NOTICE_FILENAME in names and dl.CITATION_FILENAME in names
        notice = archive.read(f"{FOLDER}/{dl.NOTICE_FILENAME}").decode("utf-8")
        assert "Contains modified Copernicus Sentinel data 2026" in notice and "Sentinel Data Legal Notice" in notice
        citation = archive.read(f"{FOLDER}/{dl.CITATION_FILENAME}").decode("utf-8")
        assert "10.5270/S2_-znk9xsj" in citation and "Sentinel-2 L2A (Zarr3)" in citation

    async def test_the_recipe_carries_the_attribution_and_the_methods_name_the_dataset(
        self, mocked: Store, rig: Rig  # noqa: F811
    ) -> None:
        job_id, api = await self.finished(rig)
        async with client_for(api) as client:
            recipe = (await client.get(f"/processing/jobs/{job_id}/results/recipe.json")).json()
            methods = (await client.get(f"/processing/jobs/{job_id}/results/methods.txt")).text
        assert recipe["provenance"]["attribution"] == ["Contains modified Copernicus Sentinel data 2026"]
        assert "Sentinel-2 L2A (Zarr3)" in methods and "doi:10.5270/S2_-znk9xsj" in methods
