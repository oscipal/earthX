"""The items of a materialized dataset in a rectangle, out of a real pgstac (M5-30b part 1, `api.measure_tiles`)."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

import psycopg
import pytest

from earthx.catalog.pgstac import (
    load_collection,
    search_items_in_bbox,
    search_items_in_bbox_async,
    upsert_items,
    use_pgstac_search_path,
)
from earthx.catalog.registry import CoverageProvider, ItemHolding, SearchCapabilities
from tests.catalog.entries import SENTINEL_2_L2A

MATERIALIZED = replace(
    SENTINEL_2_L2A,
    dataset_id="earthx-test-search-bbox",
    source=replace(
        SENTINEL_2_L2A.source,
        item_holding=ItemHolding.MATERIALIZED,
        source_collection_id="earthx-test-search-bbox",
        asset_hosts=("assets.example.invalid",),
    ),
    coverage=replace(SENTINEL_2_L2A.coverage, provider=CoverageProvider.LOCAL_SQL),
    search_filters=(),
    search_capabilities=SearchCapabilities(evaluate=False, aoi_coverage=False),
)


def _item(item_id: str, west: float, day: str = "2026-01-01") -> dict[str, Any]:
    ring = [[west, 0.0], [west + 1.0, 0.0], [west + 1.0, 1.0], [west, 1.0], [west, 0.0]]
    return {
        "id": item_id,
        "type": "Feature",
        "stac_version": "1.0.0",
        "collection": MATERIALIZED.dataset_id,
        "bbox": [west, 0.0, west + 1.0, 1.0],
        "geometry": {"type": "Polygon", "coordinates": [ring]},
        "properties": {"datetime": f"{day}T00:00:00Z"},
        "assets": {"visual": {"href": f"https://assets.example.invalid/{item_id}.tif"}},
        "links": [],
    }


@pytest.fixture
def loaded(require_postgres_env: None) -> None:
    with psycopg.connect(autocommit=True) as conn:
        load_collection(conn, MATERIALIZED)
        upsert_items(conn, MATERIALIZED, [_item(f"t{n}", float(n)) for n in range(5)])
        # Three days over the same ground, as a series of a fixed grid has them (M5-11).
        upsert_items(conn, MATERIALIZED, [_item(f"d{n}", 10.0, f"2024-07-0{n}") for n in (1, 2, 3)])
    yield
    with psycopg.connect(autocommit=True) as conn:
        use_pgstac_search_path(conn)
        conn.execute("SELECT pgstac.delete_collection(%s)", (MATERIALIZED.dataset_id,))


def test_the_items_meeting_the_rectangle_come_back_whole(loaded: None) -> None:
    with psycopg.connect() as conn:
        found = search_items_in_bbox(conn, MATERIALIZED.dataset_id, (1.5, 0.2, 3.5, 0.8), 100)
    assert sorted(item["id"] for item in found) == ["t1", "t2", "t3"]
    assert all(item["assets"]["visual"]["href"].endswith(f"{item['id']}.tif") for item in found)


def test_the_limit_holds_and_a_rectangle_elsewhere_finds_nothing(loaded: None) -> None:
    with psycopg.connect() as conn:
        assert len(search_items_in_bbox(conn, MATERIALIZED.dataset_id, (0.0, 0.0, 5.0, 1.0), 2)) == 2
        assert search_items_in_bbox(conn, MATERIALIZED.dataset_id, (40.0, 40.0, 41.0, 41.0), 10) == []
        with pytest.raises(ValueError):
            search_items_in_bbox(conn, MATERIALIZED.dataset_id, (0.0, 0.0, 1.0, 1.0), 0)


def test_a_period_keeps_only_the_items_of_its_days(loaded: None) -> None:
    ground = (10.2, 0.2, 10.8, 0.8)
    with psycopg.connect() as conn:
        everything = search_items_in_bbox(conn, MATERIALIZED.dataset_id, ground, 100)
        one_day = search_items_in_bbox(
            conn, MATERIALIZED.dataset_id, ground, 100, (datetime(2024, 7, 2, tzinfo=UTC), datetime(2024, 7, 2, 23, 59, 59, tzinfo=UTC))
        )
        from_then_on = search_items_in_bbox(conn, MATERIALIZED.dataset_id, ground, 100, (datetime(2024, 7, 2, tzinfo=UTC), None))
    assert sorted(item["id"] for item in everything) == ["d1", "d2", "d3"]
    assert [item["id"] for item in one_day] == ["d2"]
    assert sorted(item["id"] for item in from_then_on) == ["d2", "d3"]


@pytest.mark.anyio
async def test_the_async_search_gives_the_same_items_on_a_connection_that_keeps_its_search_path(loaded: None) -> None:
    """The tile of a substitute reads through the pool of the tiler: shared connections, so no ``search_path`` is left on one."""
    async with await psycopg.AsyncConnection.connect(autocommit=True) as conn:
        before = await (await conn.execute("SHOW search_path")).fetchone()
        found = await search_items_in_bbox_async(conn, MATERIALIZED.dataset_id, (1.5, 0.2, 3.5, 0.8), 100)
        assert await (await conn.execute("SHOW search_path")).fetchone() == before
        assert len(await search_items_in_bbox_async(conn, MATERIALIZED.dataset_id, (0.0, 0.0, 5.0, 1.0), 2)) == 2
        assert await search_items_in_bbox_async(conn, MATERIALIZED.dataset_id, (40.0, 40.0, 41.0, 41.0), 10) == []
        with pytest.raises(ValueError):
            await search_items_in_bbox_async(conn, MATERIALIZED.dataset_id, (0.0, 0.0, 1.0, 1.0), 0)
    assert sorted(item["id"] for item in found) == ["t1", "t2", "t3"]
