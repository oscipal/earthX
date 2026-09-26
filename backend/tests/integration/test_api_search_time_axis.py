"""M3-12: a dataset without a time axis is never filtered by `datetime`.

`capabilities.time_range=False` (the DEM, once it is real, M3-11b) means a search
with a chosen time window answers the same as one without — not even the frontend's
±90-day fallback matters, because the backend never drops a matching item to begin
with. The route says so in the answer's `ignored_filters`, the same field the
coverage route already uses for the identical rule (`api/coverage_route.py`,
M3-11c).

No mocked transport: every dataset here is materialized (`ItemHolding.MATERIALIZED`),
so `FederatingCoreCrudClient` answers straight from pgstac, the same as
`test_api_materialized.py`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from typing import Any

import httpx
import psycopg
import pytest

from earthx.api.main import app
from earthx.catalog.datasets import SENTINEL_2_L2A
from earthx.catalog.pgstac import load_collection, upsert_items, use_pgstac_search_path
from earthx.catalog.registry import CoverageProvider, ItemHolding

pytestmark = pytest.mark.anyio

# A one-off product acquired well before any window a test would ever search —
# the same shape the real DEM entry has (M3-11b: `datetime=None`, a fixed period),
# without needing that entry to exist yet.
_ACQUIRED = "2012-06-15T00:00:00Z"

NO_TIME_AXIS = replace(
    SENTINEL_2_L2A,
    dataset_id="earthx-test-no-time-axis",
    capabilities=replace(SENTINEL_2_L2A.capabilities, time_range=False, single_coverage_product=True),
    source=replace(
        SENTINEL_2_L2A.source,
        item_holding=ItemHolding.MATERIALIZED,
        source_collection_id="earthx-test-no-time-axis",
        harvest_run=None,
    ),
    coverage=replace(SENTINEL_2_L2A.coverage, provider=CoverageProvider.LOCAL_SQL),
)

# A control with a time axis, otherwise identical — proves the drop is specific to
# `time_range=False` and does not leak into an ordinary materialized dataset.
WITH_TIME_AXIS = replace(
    NO_TIME_AXIS,
    dataset_id="earthx-test-with-time-axis",
    capabilities=replace(NO_TIME_AXIS.capabilities, time_range=True),
    source=replace(NO_TIME_AXIS.source, source_collection_id="earthx-test-with-time-axis"),
)


def _item(collection_id: str, item_id: str, datetime_value: str) -> dict[str, Any]:
    return {
        "id": item_id,
        "type": "Feature",
        "stac_version": "1.0.0",
        "collection": collection_id,
        "bbox": [-1.0, -1.0, 1.0, 1.0],
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[-1.0, -1.0], [1.0, -1.0], [1.0, 1.0], [-1.0, 1.0], [-1.0, -1.0]]],
        },
        "properties": {"datetime": datetime_value},
        "assets": {},
        "links": [],
    }


@pytest.fixture
def datasets_loaded(require_postgres_env: None):
    with psycopg.connect(autocommit=True) as conn:
        load_collection(conn, NO_TIME_AXIS)
        load_collection(conn, WITH_TIME_AXIS)
        upsert_items(conn, NO_TIME_AXIS, [_item(NO_TIME_AXIS.dataset_id, "a", _ACQUIRED)])
        upsert_items(conn, WITH_TIME_AXIS, [_item(WITH_TIME_AXIS.dataset_id, "b", _ACQUIRED)])
    yield
    with psycopg.connect(autocommit=True) as conn:
        use_pgstac_search_path(conn)
        for dataset_id in (NO_TIME_AXIS.dataset_id, WITH_TIME_AXIS.dataset_id):
            conn.execute("SELECT pgstac.delete_collection(%s)", (dataset_id,))


@asynccontextmanager
async def _client() -> AsyncIterator[httpx.AsyncClient]:
    """No mocked transport: a materialized collection never reaches `gateway`."""
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


# A window nowhere near `_ACQUIRED` — the same situation that, before this task,
# answered "No results in the chosen time range, nor within ±90 days" for the DEM.
_UNRELATED_WINDOW = "2026-01-01T00:00:00Z/2026-12-31T23:59:59Z"


class TestGetSearch:
    async def test_a_dataset_without_a_time_axis_ignores_an_unrelated_window(
        self, datasets_loaded: None
    ) -> None:
        async with _client() as client:
            response = await client.get(
                "/stac/search",
                params={"collections": NO_TIME_AXIS.dataset_id, "datetime": _UNRELATED_WINDOW},
            )
        assert response.status_code == 200
        body = response.json()
        assert [item["id"] for item in body["features"]] == ["a"]
        assert body["ignored_filters"] == ["datetime"]

    async def test_without_a_datetime_at_all_nothing_is_ignored(self, datasets_loaded: None) -> None:
        async with _client() as client:
            response = await client.get("/stac/search", params={"collections": NO_TIME_AXIS.dataset_id})
        assert response.status_code == 200
        assert "ignored_filters" not in response.json()

    async def test_a_dataset_with_a_time_axis_is_filtered_as_usual(self, datasets_loaded: None) -> None:
        """The control: the same unrelated window, but `time_range=True` — the item
        is filtered out exactly as pgstac would for any collection, and the answer
        names no ignored filter."""
        async with _client() as client:
            response = await client.get(
                "/stac/search",
                params={"collections": WITH_TIME_AXIS.dataset_id, "datetime": _UNRELATED_WINDOW},
            )
        assert response.status_code == 200
        body = response.json()
        assert body["features"] == []
        assert "ignored_filters" not in body

    async def test_a_malformed_datetime_is_still_a_400(self, datasets_loaded: None) -> None:
        """Validated before anything is dropped — a dataset with no time axis is not
        a way to smuggle a bad value past the usual check."""
        async with _client() as client:
            response = await client.get(
                "/stac/search",
                params={"collections": NO_TIME_AXIS.dataset_id, "datetime": "not-a-date"},
            )
        assert response.status_code == 400


class TestPostSearch:
    async def test_ignores_an_unrelated_window(self, datasets_loaded: None) -> None:
        async with _client() as client:
            response = await client.post(
                "/stac/search",
                json={"collections": [NO_TIME_AXIS.dataset_id], "datetime": _UNRELATED_WINDOW},
            )
        assert response.status_code == 200
        body = response.json()
        assert [item["id"] for item in body["features"]] == ["a"]
        assert body["ignored_filters"] == ["datetime"]


class TestItemCollection:
    async def test_ignores_an_unrelated_window(self, datasets_loaded: None) -> None:
        async with _client() as client:
            response = await client.get(
                f"/stac/collections/{NO_TIME_AXIS.dataset_id}/items",
                params={"datetime": _UNRELATED_WINDOW},
            )
        assert response.status_code == 200
        body = response.json()
        assert [item["id"] for item in body["features"]] == ["a"]
        assert body["ignored_filters"] == ["datetime"]

    async def test_a_malformed_datetime_is_still_a_400(self, datasets_loaded: None) -> None:
        async with _client() as client:
            response = await client.get(
                f"/stac/collections/{NO_TIME_AXIS.dataset_id}/items",
                params={"datetime": "not-a-date"},
            )
        assert response.status_code == 400
