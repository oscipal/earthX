"""T-C: the federated STAC search reads the app's own registry (M4-01b).

Before M4-01b the search looked its entry up in the module-wide ``REGISTRY``,
while routing (M4-01a) already read the registry ``build_app`` was given. Here the
app's entry for Sentinel-2 names a different upstream collection id than
``REGISTRY`` does; the request that reaches the mocked source shows which entry
was used. Real pgstac for the collection document, mocked Earth Search (adr/0002).
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path

import httpx
import psycopg
import pytest

from earthx.api.main import build_app
from earthx.catalog.datasets import SENTINEL_2_L2A
from earthx.catalog.load import main as load_catalog
from earthx.catalog.registry import DatasetRegistry
from earthx.gateway import Gateway, Policy

pytestmark = pytest.mark.anyio

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "earth_search"
POLICY = Policy(allowed_hosts=frozenset({"earth-search.aws.element84.com"}))

APP_ONLY = replace(SENTINEL_2_L2A, source=replace(SENTINEL_2_L2A.source, source_collection_id="earthx-test-app-only"))
app = build_app(DatasetRegistry((APP_ONLY,)))


@pytest.fixture
def require_catalog_loaded(require_postgres_env: None) -> None:
    assert load_catalog() == 0
    # The cache pool commits; a row an earlier run left would answer without
    # reaching the mocked transport (same reasoning as `test_api_federating.py`).
    with psycopg.connect(autocommit=True) as conn:
        conn.execute("DELETE FROM public.earthx_search_cache")


def _public(host: str, port: int) -> tuple[str, ...]:
    return ("93.184.216.34",)


@asynccontextmanager
async def _client() -> AsyncIterator[tuple[httpx.AsyncClient, list[httpx.Request]]]:
    seen: list[httpx.Request] = []
    empty = json.loads((FIXTURES / "search_empty.json").read_text(encoding="utf-8"))

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=empty)

    async def sleep(seconds: float) -> None:
        return None

    async with app.router.lifespan_context(app):
        app.state.earthx_gateway = Gateway(POLICY, transport=httpx.MockTransport(handler), resolve=_public, sleep=sleep)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, seen


def _upstream_collections(seen: list[httpx.Request]) -> list[list[str]]:
    return [json.loads(request.content)["collections"] for request in seen]


async def test_a_search_asks_the_source_with_the_apps_own_entry(require_catalog_loaded: None) -> None:
    async with _client() as (client, seen):
        response = await client.get("/stac/search", params={"collections": SENTINEL_2_L2A.dataset_id})
    assert response.status_code == 200
    assert _upstream_collections(seen) == [["earthx-test-app-only"]]


async def test_the_items_route_does_too(require_catalog_loaded: None) -> None:
    async with _client() as (client, seen):
        response = await client.get(f"/stac/collections/{SENTINEL_2_L2A.dataset_id}/items")
    assert response.status_code == 200
    assert _upstream_collections(seen) == [["earthx-test-app-only"]]
