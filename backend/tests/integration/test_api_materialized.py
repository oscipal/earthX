"""T-C: a materialized collection through the real STAC API (M3-11a §3.2).

No mocked transport and no gateway usage at all: a materialized collection answers
straight from pgstac (``super()``), so ``FederatingCoreCrudClient`` never reaches
``earthx.adapters`` for it. This proves the dispatch itself — search,
``item_collection`` and ``get_item`` all reach pgstac rather than a source that does
not exist for this kind of collection — and that the parameter checks moved to run
before the dispatch (M3-11a §3.2) still hold on this branch, which before this task
no real collection ever reached.

Written and cleaned up on its own commit, not through the rolled-back ``conn``
fixture: the api process reads through its own connection pool, which would never
see an uncommitted transaction on a different connection (the same reasoning
``test_pgstac_load.py``'s own entry-point tests already follow).
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from typing import Any

import httpx
import psycopg
import pytest

from earthx.api.main import app
from earthx.catalog.collection import to_stac_collection
from earthx.catalog.datasets import SENTINEL_2_L2A
from earthx.catalog.pgstac import load_collection, upsert_items, use_pgstac_search_path
from earthx.catalog.registry import CoverageProvider, ItemHolding

pytestmark = pytest.mark.anyio

MATERIALIZED = replace(
    SENTINEL_2_L2A,
    dataset_id="earthx-test-materialized-api",
    source=replace(
        SENTINEL_2_L2A.source,
        item_holding=ItemHolding.MATERIALIZED,
        source_collection_id="earthx-test-materialized-api",
        harvest_run=None,
    ),
    coverage=replace(SENTINEL_2_L2A.coverage, provider=CoverageProvider.LOCAL_SQL),
)


def _item(item_id: str) -> dict[str, Any]:
    return {
        "id": item_id,
        "type": "Feature",
        "stac_version": "1.0.0",
        "collection": MATERIALIZED.dataset_id,
        "bbox": [-1.0, -1.0, 1.0, 1.0],
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[-1.0, -1.0], [1.0, -1.0], [1.0, 1.0], [-1.0, 1.0], [-1.0, -1.0]]],
        },
        "properties": {"datetime": "2026-01-01T00:00:00Z"},
        "assets": {},
        "links": [],
    }


@pytest.fixture
def materialized_loaded(require_postgres_env: None) -> None:
    with psycopg.connect(autocommit=True) as conn:
        load_collection(conn, MATERIALIZED)
        upsert_items(conn, MATERIALIZED, [_item("a"), _item("b")])
    yield
    with psycopg.connect(autocommit=True) as conn:
        use_pgstac_search_path(conn)
        conn.execute("SELECT pgstac.delete_collection(%s)", (MATERIALIZED.dataset_id,))


@asynccontextmanager
async def _client() -> AsyncIterator[httpx.AsyncClient]:
    """No mocked transport: a materialized collection never reaches ``gateway``."""
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


class TestMaterializedSearch:
    async def test_get_search_finds_the_items(self, materialized_loaded: None) -> None:
        async with _client() as client:
            response = await client.get("/stac/search", params={"collections": MATERIALIZED.dataset_id})
        assert response.status_code == 200
        assert {item["id"] for item in response.json()["features"]} == {"a", "b"}

    async def test_post_search_finds_the_items(self, materialized_loaded: None) -> None:
        async with _client() as client:
            response = await client.post("/stac/search", json={"collections": [MATERIALIZED.dataset_id]})
        assert response.status_code == 200
        assert {item["id"] for item in response.json()["features"]} == {"a", "b"}

    async def test_ids_filters_within_the_collection(self, materialized_loaded: None) -> None:
        async with _client() as client:
            response = await client.get(
                "/stac/search", params={"collections": MATERIALIZED.dataset_id, "ids": "a"}
            )
        assert response.status_code == 200
        assert [item["id"] for item in response.json()["features"]] == ["a"]

    async def test_a_filter_parameter_is_rejected_here_too(self, materialized_loaded: None) -> None:
        """Before M3-11a nothing this route ever handled materialized had a native
        pgstac path with a caller — the check for a disabled extension only ever
        ran on the federated branch. It has to hold here too (adr/0005 rule VI)."""
        async with _client() as client:
            response = await client.get(
                "/stac/search", params={"collections": MATERIALIZED.dataset_id, "filter": "true"}
            )
        assert response.status_code == 400


class TestMaterializedItemCollection:
    async def test_it_lists_the_items(self, materialized_loaded: None) -> None:
        async with _client() as client:
            response = await client.get(f"/stac/collections/{MATERIALIZED.dataset_id}/items")
        assert response.status_code == 200
        assert {item["id"] for item in response.json()["features"]} == {"a", "b"}

    async def test_a_filter_parameter_is_rejected(self, materialized_loaded: None) -> None:
        """M3-11a §3.2: moved to run before the holding dispatch, so it now also
        covers the pgstac-native branch a materialized collection takes."""
        async with _client() as client:
            response = await client.get(
                f"/stac/collections/{MATERIALIZED.dataset_id}/items", params={"filter": "true"}
            )
        assert response.status_code == 400

    async def test_ids_is_not_a_parameter_of_this_endpoint(self, materialized_loaded: None) -> None:
        """M3-08: `ids`/`intersects` belong to `item-search`, not OGC's items
        endpoint — true for a materialized collection exactly as for a federated
        one."""
        async with _client() as client:
            response = await client.get(
                f"/stac/collections/{MATERIALIZED.dataset_id}/items", params={"ids": "a"}
            )
        assert response.status_code == 400


class TestMaterializedGetItem:
    async def test_a_known_item_is_returned(self, materialized_loaded: None) -> None:
        async with _client() as client:
            response = await client.get(f"/stac/collections/{MATERIALIZED.dataset_id}/items/a")
        assert response.status_code == 200
        assert response.json()["id"] == "a"

    async def test_an_unknown_item_is_pgstacs_own_404(self, materialized_loaded: None) -> None:
        async with _client() as client:
            response = await client.get(f"/stac/collections/{MATERIALIZED.dataset_id}/items/no-such-item")
        assert response.status_code == 404


BROKEN_ID = "earthx-test-broken-holding"


@pytest.fixture
def broken_collection_loaded(require_postgres_env: None) -> None:
    """A collection in pgstac with no ``earthx:source.item_holding`` at all — the
    shape a collection loaded before this field existed would still have, or one
    written outside ``catalog.load`` by mistake (M3-11a §6, F5)."""
    broken = to_stac_collection(replace(MATERIALIZED, dataset_id=BROKEN_ID))
    del broken["earthx:source"]["item_holding"]
    with psycopg.connect(autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT pgstac.upsert_collection(%s::jsonb)", (json.dumps(broken),))
    yield
    with psycopg.connect(autocommit=True) as conn:
        use_pgstac_search_path(conn)
        conn.execute("SELECT pgstac.delete_collection(%s)", (BROKEN_ID,))


class TestUnrecognisedItemHolding:
    """M3-11a §6/F5: a collection whose ``item_holding`` is missing or unknown is a
    data problem, not a signal to guess — refused loudly rather than answered as
    pgstac's own near-empty result for a collection nobody put items in."""

    async def test_item_collection_is_a_500_not_an_empty_page(self, broken_collection_loaded: None) -> None:
        async with _client() as client:
            response = await client.get(f"/stac/collections/{BROKEN_ID}/items")
        assert response.status_code == 500
        assert "item_holding" in response.json()["detail"]

    async def test_get_item_is_a_500(self, broken_collection_loaded: None) -> None:
        async with _client() as client:
            response = await client.get(f"/stac/collections/{BROKEN_ID}/items/whatever")
        assert response.status_code == 500

    async def test_search_naming_it_is_a_500_not_an_empty_result(self, broken_collection_loaded: None) -> None:
        async with _client() as client:
            response = await client.get("/stac/search", params={"collections": BROKEN_ID})
        assert response.status_code == 500
