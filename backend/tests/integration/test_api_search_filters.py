"""T-C, DS-02: search filters on ``POST /stac/search``, against real pgstac with the sources mocked.

Three collections: Sentinel-2 with all of its filters, a second federated one (the synthetic Zarr entry) that
offers only cloud cover, and a materialized one that offers none. Each source is told only the conditions on
its own filters; what a shared ``query`` cannot give a collection is named, never silently dropped.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path
from typing import Any

import httpx
import psycopg
import pytest

from earthx.api.main import build_app
from earthx.catalog.datasets import REGISTRY, SENTINEL_2_L2A
from earthx.catalog.load import main as load_catalog
from earthx.catalog.pgstac import load_collection, use_pgstac_search_path
from earthx.catalog.registry import CoverageProvider, DatasetRegistry, ItemHolding
from earthx.gateway import Gateway, Policy
from tests.catalog.synthetic_zarr import SYNTHETIC_ZARR
from tests.conftest import format_without_timestamp

pytestmark = pytest.mark.anyio

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "earth_search"
HOST = "earth-search.aws.element84.com"
ZARR_HOST = "stac.example.invalid"
POLICY = Policy(allowed_hosts=frozenset({HOST, ZARR_HOST}))
S2 = SENTINEL_2_L2A.dataset_id

CLOUD_ONLY = replace(
    SYNTHETIC_ZARR, search_filters=(replace(SENTINEL_2_L2A.search_filter("eo:cloud_cover"), within_aoi=False),)
)
NATIVE = replace(
    SENTINEL_2_L2A,
    dataset_id="earthx-test-filters-native",
    source=replace(
        SENTINEL_2_L2A.source, item_holding=ItemHolding.MATERIALIZED, source_collection_id="earthx-test-filters-native"
    ),
    coverage=replace(SENTINEL_2_L2A.coverage, provider=CoverageProvider.LOCAL_SQL),
    search_filters=(),
)

app = build_app(DatasetRegistry((*REGISTRY, CLOUD_ONLY, NATIVE)))


def load_fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def _public(host: str, port: int) -> tuple[str, ...]:
    return ("93.184.216.34",)


@pytest.fixture
def collections_loaded(require_postgres_env: None) -> Iterator[None]:
    assert load_catalog() == 0
    with psycopg.connect(autocommit=True) as conn:
        load_collection(conn, CLOUD_ONLY)
        load_collection(conn, NATIVE)
        # Rows outlive one test (the cache pool commits); an earlier run's page must not answer this one.
        conn.execute("DELETE FROM public.earthx_search_cache")
    yield
    with psycopg.connect(autocommit=True) as conn:
        use_pgstac_search_path(conn)
        for config in (CLOUD_ONLY, NATIVE):
            conn.execute("SELECT pgstac.delete_collection(%s)", (config.dataset_id,))


@asynccontextmanager
async def _client(handler: Callable[[httpx.Request], httpx.Response]) -> AsyncIterator[httpx.AsyncClient]:
    async def sleep(seconds: float) -> None:
        return None

    async with app.router.lifespan_context(app):
        app.state.earthx_gateway = Gateway(POLICY, transport=httpx.MockTransport(handler), resolve=_public, sleep=sleep)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            yield client


def _by_host(
    responses: dict[str, httpx.Response] | None = None,
) -> tuple[Callable[[httpx.Request], httpx.Response], dict[str, list[dict[str, Any]]]]:
    """Answers each source, and keeps the bodies each one was sent."""
    bodies: dict[str, list[dict[str, Any]]] = {HOST: [], ZARR_HOST: []}
    answers = responses or {}

    def handler(request: httpx.Request) -> httpx.Response:
        host = request.headers["host"]
        bodies[host].append(json.loads(request.content))
        return answers.get(host) or httpx.Response(200, json=load_fixture("search_empty"))

    return handler, bodies


async def _search(body: dict[str, Any], responses: dict[str, httpx.Response] | None = None):
    handler, bodies = _by_host(responses)
    async with _client(handler) as client:
        response = await client.post("/stac/search", json=body)
    return response, bodies


class TestOneCollection:
    async def test_the_conditions_reach_the_source_as_its_query(self, collections_loaded: None) -> None:
        response, bodies = await _search(
            {
                "collections": [S2],
                "query": {"eo:cloud_cover": {"lte": 20}, "platform": {"in": ["sentinel-2c", "sentinel-2a"]}},
            }
        )
        assert response.status_code == 200
        assert bodies[HOST][0]["query"] == {
            "eo:cloud_cover": {"lte": 20.0},
            "platform": {"in": ["sentinel-2a", "sentinel-2c"]},
        }
        assert "ignored_filters" not in response.json()

    async def test_a_search_without_filters_sends_none(self, collections_loaded: None) -> None:
        response, bodies = await _search({"collections": [S2]})
        assert response.status_code == 200
        assert "query" not in bodies[HOST][0]

    @pytest.mark.parametrize(
        "body",
        [
            {"query": {"eo:cloud_cover": {"lte": 120.75}}},
            {"query": {"eo:cloud_cover": {"lt": 20}}},
            {"query": {"platform": {"in": ["sentinel-9z"]}}},
            {"query": {"sat:orbit_state": {"in": ["descending"]}}},
            {"query": {"earthx:aoi_cloud_cover": {"lte": 5}}},
            {"query": {"eo:cloud_cover": {"lte": 20}}, "query_by_collection": {}},
            {"query_by_collection": {SYNTHETIC_ZARR.dataset_id: {"eo:cloud_cover": {"lte": 20}}}},
        ],
    )
    async def test_a_request_the_registry_does_not_allow_is_400_before_any_source(
        self, collections_loaded: None, body: dict[str, Any]
    ) -> None:
        response, bodies = await _search({"collections": [S2], **body})
        assert response.status_code == 400
        assert bodies == {HOST: [], ZARR_HOST: []}
        assert "120.75" not in response.text and "sentinel-9z" not in response.text

    @pytest.mark.parametrize("key", ["query", "query_by_collection"])
    async def test_a_get_search_refuses_filters(self, collections_loaded: None, key: str) -> None:
        handler, bodies = _by_host()
        async with _client(handler) as client:
            response = await client.get("/stac/search", params={"collections": S2, key: "{}"})
        assert response.status_code == 400
        assert "POST" in response.json()["detail"]
        assert bodies == {HOST: [], ZARR_HOST: []}

    async def test_the_next_page_keeps_its_filters(self, collections_loaded: None) -> None:
        query = {"eo:cloud_cover": {"lte": 20}}
        first, _ = await _search(
            {"collections": [S2], "query": query, "limit": 2}, {HOST: httpx.Response(200, json=load_fixture("search_page_1"))}
        )
        token = next(link for link in first.json()["links"] if link["rel"] == "next")["body"]["token"]
        same, bodies = await _search({"collections": [S2], "query": query, "limit": 2, "token": token})
        assert same.status_code == 200
        assert bodies[HOST][0]["query"] == {"eo:cloud_cover": {"lte": 20.0}}
        assert "next" in bodies[HOST][0]
        other, bodies = await _search(
            {"collections": [S2], "query": {"eo:cloud_cover": {"lte": 30}}, "limit": 2, "token": token}
        )
        assert other.status_code == 400
        assert bodies == {HOST: [], ZARR_HOST: []}


class TestSeveralCollections:
    async def test_a_shared_query_goes_where_it_is_offered_and_names_the_rest(self, collections_loaded: None) -> None:
        response, bodies = await _search(
            {
                "collections": [S2, CLOUD_ONLY.dataset_id, NATIVE.dataset_id],
                "query": {"eo:cloud_cover": {"lte": 20}, "platform": {"in": ["sentinel-2a"]}},
            }
        )
        assert response.status_code == 200
        assert bodies[HOST][0]["query"] == {"eo:cloud_cover": {"lte": 20.0}, "platform": {"in": ["sentinel-2a"]}}
        assert bodies[ZARR_HOST][0]["query"] == {"eo:cloud_cover": {"lte": 20.0}}
        answer = response.json()
        assert answer["ignored_filters_by_collection"] == {
            CLOUD_ONLY.dataset_id: ["platform"],
            NATIVE.dataset_id: ["eo:cloud_cover", "platform"],
        }
        assert answer["ignored_filters"] == ["eo:cloud_cover", "platform"]

    async def test_values_per_collection_reach_only_their_own_source(self, collections_loaded: None) -> None:
        response, bodies = await _search(
            {
                "collections": [S2, CLOUD_ONLY.dataset_id, NATIVE.dataset_id],
                "query_by_collection": {
                    S2: {"platform": {"in": ["sentinel-2b"]}},
                    CLOUD_ONLY.dataset_id: {"eo:cloud_cover": {"gte": 50}},
                },
            }
        )
        assert response.status_code == 200
        assert bodies[HOST][0]["query"] == {"platform": {"in": ["sentinel-2b"]}}
        assert bodies[ZARR_HOST][0]["query"] == {"eo:cloud_cover": {"gte": 50.0}}
        assert "ignored_filters_by_collection" not in response.json()

    async def test_a_collection_without_values_is_searched_unfiltered(self, collections_loaded: None) -> None:
        _, bodies = await _search(
            {
                "collections": [S2, CLOUD_ONLY.dataset_id],
                "query_by_collection": {S2: {"eo:cloud_cover": {"lte": 10}}},
            }
        )
        assert bodies[HOST][0]["query"] == {"eo:cloud_cover": {"lte": 10.0}}
        assert "query" not in bodies[ZARR_HOST][0]


class TestTheSourcesOwnWords:
    """Otto's C (28.10.2026): a source's error text reaches neither the answer nor a log line."""

    INTERNALS = "query_shard_exception: failed to create query: For input string"

    async def test_stay_out_of_the_answer_and_the_log(
        self, collections_loaded: None, caplog: pytest.LogCaptureFixture
    ) -> None:
        rejection = httpx.Response(400, json={"code": "BadRequest", "description": self.INTERNALS})
        with caplog.at_level(logging.DEBUG):
            response, _ = await _search(
                {"collections": [S2], "query": {"eo:cloud_cover": {"lte": 17.25}}}, {HOST: rejection}
            )
        assert response.status_code == 400
        assert response.json()["detail"] == "the source answered with an error"
        assert self.INTERNALS not in response.text
        assert caplog.records, "the test would prove nothing if nothing was logged"
        for record in caplog.records:
            rendered = format_without_timestamp(record)
            assert "query_shard_exception" not in rendered
            assert "17.25" not in rendered
