"""T-C: the tiler's materialized item path against a real pgstac (M3-11a §3.3).

Proves what the unit tests in ``tests/earthx/api/test_tiler.py`` mock out: the
process ``_lifespan`` really does build ``earthx_item_source`` from the registry
``build_app`` was actually given (M3-11a §2.2 — before this task that only mattered
for the search cache, since nothing else here ever read from pgstac), and a
materialized item is really read through the real database pool this process opens
at startup, not just through a stand-in for it.

Only the database is real. The asset host resolves from memory and the actual pixel
read is faked (the same two seams ``tests/earthx/api/test_tiler.py``'s own ``client``
fixture stands in for) — this file is not about GDAL or a real store, only about the
item really coming from pgstac.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient

from earthx.api.tiler import build_app
from earthx.catalog.datasets import SENTINEL_2_L2A
from earthx.catalog.pgstac import load_collection, upsert_items, use_pgstac_search_path
from earthx.catalog.registry import CoverageProvider, DatasetRegistry, ItemHolding
from earthx.gateway import check_url

MATERIALIZED = replace(
    SENTINEL_2_L2A,
    dataset_id="earthx-test-materialized-tiler",
    source=replace(
        SENTINEL_2_L2A.source,
        item_holding=ItemHolding.MATERIALIZED,
        source_collection_id="earthx-test-materialized-tiler",
        harvest_run=None,
        asset_hosts=("assets.example.invalid",),
    ),
    coverage=replace(SENTINEL_2_L2A.coverage, provider=CoverageProvider.LOCAL_SQL),
)

BASE = f"/collections/{MATERIALIZED.dataset_id}/items"


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
        "assets": {"visual": {"href": "https://assets.example.invalid/a.tif"}},
        "links": [],
    }


@pytest.fixture
def materialized_loaded(require_postgres_env: None) -> None:
    with psycopg.connect(autocommit=True) as conn:
        load_collection(conn, MATERIALIZED)
        upsert_items(conn, MATERIALIZED, [_item("a")])
        # The statistics cache commits (autocommit=True, dependencies.cache_pool),
        # so a row outlives one test run — the same caution
        # `test_api_federating.py::require_catalog_loaded` takes for the search
        # cache, here for the one other cache this process's real pool can fill.
        conn.execute("DELETE FROM public.earthx_stats_cache WHERE dataset_id = %s", (MATERIALIZED.dataset_id,))
    yield
    with psycopg.connect(autocommit=True) as conn:
        use_pgstac_search_path(conn)
        conn.execute("SELECT pgstac.delete_collection(%s)", (MATERIALIZED.dataset_id,))


@pytest.fixture
def app_client(materialized_loaded: None, monkeypatch: pytest.MonkeyPatch) -> Any:
    """The real tiler app, its real lifespan (a real ``cache_pool()``), against a
    registry of one materialized entry. Entering ``TestClient`` as a context manager
    runs that lifespan — unlike ``tests/earthx/api/test_tiler.py``'s own ``client``,
    which deliberately avoids it."""
    monkeypatch.setattr(
        "earthx.readers.cog.check_url",
        lambda url, policy, **_: check_url(url, policy, resolve=lambda host, port: ("93.184.216.34",)),
    )

    opened: list[str] = []

    def fake_read(reader: Any, src_path: Any, **kwargs: Any) -> dict[str, Any]:
        opened.append(str(src_path))
        return {}

    monkeypatch.setattr("earthx.access.tiles._read_statistics", fake_read)

    registry = DatasetRegistry((MATERIALIZED,))
    app = build_app(registry)
    with TestClient(app) as client:
        client.opened = opened  # type: ignore[attr-defined]
        yield client


class TestMaterializedItemThroughTheRealPool:
    def test_a_known_item_is_read_from_pgstac_and_resolved(self, app_client: Any) -> None:
        response = app_client.get(f"{BASE}/a/statistics", params={"asset": "visual"})

        assert response.status_code == 200, response.text
        # The (faked) read happened against the item's own asset href — proof the
        # item came from pgstac, not from a stub the test set up itself.
        assert app_client.opened == ["/vsicurl/https://assets.example.invalid/a.tif"]

    def test_an_unknown_item_is_404(self, app_client: Any) -> None:
        response = app_client.get(f"{BASE}/no-such-item/statistics", params={"asset": "visual"})

        assert response.status_code == 404, response.text
        assert "no item" in response.json()["detail"]
        assert app_client.opened == []
