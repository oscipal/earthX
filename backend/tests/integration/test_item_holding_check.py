"""T-C: a process does not start while pgstac and the registry hold a dataset's
items differently (adr/0011 §7 D2, Otto's answer M4-01a F2).

The collection is loaded as *materialized*; the registry the app is built with
says *federated* for the same id. Every request would then be routed past the
items pgstac really holds.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import httpx
import psycopg
import pytest

from earthx.api import main, tiler
from earthx.api.item_source import ItemHoldingMismatch
from earthx.catalog.datasets import SENTINEL_2_L2A
from earthx.catalog.pgstac import load_collection, use_pgstac_search_path
from earthx.catalog.registry import CoverageProvider, DatasetRegistry, ItemHolding
from earthx.gateway import Gateway, Policy

pytestmark = pytest.mark.anyio

DATASET = "earthx-test-holding-check"
ITEM = json.loads(
    (Path(__file__).resolve().parents[1] / "fixtures" / "earth_search" / "item.json").read_text(encoding="utf-8")
)
SOURCE_HOST = "earth-search.aws.element84.com"

# The source collection stays the real one's, so the recorded item fits it.
FEDERATED = replace(SENTINEL_2_L2A, dataset_id=DATASET)
MATERIALIZED = replace(
    FEDERATED,
    source=replace(FEDERATED.source, item_holding=ItemHolding.MATERIALIZED),
    coverage=replace(FEDERATED.coverage, provider=CoverageProvider.LOCAL_SQL),
)


def _load(config) -> None:
    with psycopg.connect(autocommit=True) as conn:
        load_collection(conn, config)


@pytest.fixture
def cleaned_up(require_postgres_env: None) -> Iterator[None]:
    with psycopg.connect(autocommit=True) as conn:
        conn.execute("DELETE FROM public.earthx_search_cache")
    yield
    with psycopg.connect(autocommit=True) as conn:
        use_pgstac_search_path(conn)
        conn.execute("SELECT pgstac.delete_collection(%s)", (DATASET,))


@pytest.fixture
def loaded_as_materialized(cleaned_up: None) -> None:
    _load(MATERIALIZED)


@pytest.fixture
def loaded_as_federated(cleaned_up: None) -> None:
    _load(FEDERATED)


class TestTiler:
    async def test_a_different_holding_stops_the_start(self, loaded_as_materialized: None) -> None:
        app = tiler.build_app(DatasetRegistry((FEDERATED,)))
        with pytest.raises(ItemHoldingMismatch, match=DATASET):
            async with app.router.lifespan_context(app):
                pass

    async def test_the_same_holding_starts(self, loaded_as_materialized: None) -> None:
        app = tiler.build_app(DatasetRegistry((MATERIALIZED,)))
        async with app.router.lifespan_context(app):
            assert app.state.earthx_item_source is not None


class TestApi:
    async def test_a_different_holding_stops_the_start(self, loaded_as_materialized: None) -> None:
        app = main.build_app(DatasetRegistry((FEDERATED,)))
        with pytest.raises(ItemHoldingMismatch, match=DATASET):
            async with app.router.lifespan_context(app):
                pass

    async def test_a_collection_only_pgstac_knows_is_a_warning_and_a_500_per_request(
        self, loaded_as_federated: None, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # `configure_logging` replaces the root handlers, `caplog`'s among them.
        monkeypatch.setattr(main, "configure_logging", lambda: None)
        app = main.build_app(DatasetRegistry((MATERIALIZED_ELSEWHERE,)))
        with caplog.at_level("WARNING", logger="earthx.api.item_source"):
            async with app.router.lifespan_context(app):
                async with _client(app) as client:
                    items = await client.get(f"/stac/collections/{DATASET}/items")
                    item = await client.get(f"/stac/collections/{DATASET}/items/{ITEM['id']}")
                    search = await client.get("/stac/search", params={"collections": DATASET})
        assert [r.status_code for r in (items, item, search)] == [500, 500, 500]
        assert "not in the registry" in items.json()["detail"]
        warnings = [record for record in caplog.records if record.name == "earthx.api.item_source"]
        assert any(DATASET in record.collections for record in warnings)

    async def test_get_item_routes_by_the_registry_not_by_the_document(self, loaded_as_federated: None) -> None:
        """Otto, M4-01a F3: the document in pgstac is changed to *materialized* after
        the start; the registry still says *federated*, and that is where the item
        comes from. Read off the document, it would be pgstac's own 404."""
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200, json=ITEM)

        app = main.build_app(DatasetRegistry((FEDERATED,)))
        async with app.router.lifespan_context(app):
            app.state.earthx_gateway = Gateway(
                Policy(allowed_hosts=frozenset({SOURCE_HOST})),
                transport=httpx.MockTransport(handler),
                resolve=lambda host, port: ("93.184.216.34",),
            )
            _load(MATERIALIZED)
            async with _client(app) as client:
                response = await client.get(f"/stac/collections/{DATASET}/items/{ITEM['id']}")
        assert response.status_code == 200, response.text
        assert response.json()["id"] == ITEM["id"]
        assert [request.headers["host"] for request in seen] == [SOURCE_HOST]


# A registry that knows some other dataset, but not DATASET.
MATERIALIZED_ELSEWHERE = replace(MATERIALIZED, dataset_id="earthx-test-holding-check-other")


def _client(app) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
