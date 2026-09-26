"""T-C: writing and reading the items of a materialized dataset (M3-11a §3.3, §3.5).

``upsert_items`` is what M3-11b's one-off command will call to load the Copernicus
DEM's tiles; ``fetch_item`` is what the tiler's item source reads a materialized
item back through. Both are exercised here against a real pgstac, with a synthetic
collection this file owns end to end — nothing here touches a real registry entry.
"""

from __future__ import annotations

import json
from dataclasses import replace
from typing import Any

import psycopg
import pytest

from earthx.catalog.collection import to_stac_collection
from earthx.catalog.datasets import SENTINEL_2_L2A
from earthx.catalog.pgstac import PgstacError, fetch_item, load_collection, upsert_items
from earthx.catalog.registry import CoverageProvider, ItemHolding

pytestmark = pytest.mark.anyio

# A synthetic materialized entry, never a real registry one — the whole point of
# this file is to exercise the pgstac side without a real dataset having to exist
# yet (M3-11b brings the first one).
MATERIALIZED = replace(
    SENTINEL_2_L2A,
    dataset_id="earthx-test-materialized",
    source=replace(
        SENTINEL_2_L2A.source,
        item_holding=ItemHolding.MATERIALIZED,
        source_collection_id="earthx-test-materialized",
        harvest_run=None,
    ),
    coverage=replace(SENTINEL_2_L2A.coverage, provider=CoverageProvider.LOCAL_SQL),
)

FEDERATED = SENTINEL_2_L2A

_COLLECTION_JSON = json.dumps(to_stac_collection(MATERIALIZED))


def _item(item_id: str, *, collection_id: str = MATERIALIZED.dataset_id) -> dict[str, Any]:
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
        "properties": {"datetime": "2026-01-01T00:00:00Z"},
        "assets": {},
        "links": [],
    }


def _item_count(conn: psycopg.Connection, collection_id: str) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM pgstac.items WHERE collection = %s", (collection_id,))
        return cur.fetchone()[0]


class TestUpsertItemsRefusesTheWrongInput:
    def test_a_federated_dataset_is_refused(self, conn: psycopg.Connection) -> None:
        """KLAERUNGEN B13 point 3: a federated collection's items are never a
        second stored truth."""
        load_collection(conn, FEDERATED)
        with pytest.raises(PgstacError, match="federated"):
            upsert_items(conn, FEDERATED, [_item("some-item", collection_id=FEDERATED.dataset_id)])

    def test_an_item_naming_a_different_collection_is_refused(self, conn: psycopg.Connection) -> None:
        load_collection(conn, MATERIALIZED)
        with pytest.raises(PgstacError, match="not this dataset"):
            upsert_items(conn, MATERIALIZED, [_item("some-item", collection_id="not-this-dataset")])
        assert _item_count(conn, MATERIALIZED.dataset_id) == 0


class TestUpsertItemsWrites:
    def test_the_items_land_in_pgstac(self, conn: psycopg.Connection) -> None:
        load_collection(conn, MATERIALIZED)
        count = upsert_items(conn, MATERIALIZED, [_item("a"), _item("b"), _item("c")])
        assert count == 3
        assert _item_count(conn, MATERIALIZED.dataset_id) == 3

    def test_an_empty_iterable_writes_nothing(self, conn: psycopg.Connection) -> None:
        load_collection(conn, MATERIALIZED)
        assert upsert_items(conn, MATERIALIZED, []) == 0
        assert _item_count(conn, MATERIALIZED.dataset_id) == 0

    def test_running_it_twice_leaves_the_same_rows(self, conn: psycopg.Connection) -> None:
        """Idempotent (``upsert``), the same acceptance criterion `load_collection`
        already has to meet (`test_pgstac_load.py::test_loading_twice_leaves_one_row`)."""
        load_collection(conn, MATERIALIZED)
        upsert_items(conn, MATERIALIZED, [_item("a"), _item("b")])
        upsert_items(conn, MATERIALIZED, [_item("a"), _item("b")])
        assert _item_count(conn, MATERIALIZED.dataset_id) == 2

    def test_a_changed_item_replaces_the_stored_one(self, conn: psycopg.Connection) -> None:
        load_collection(conn, MATERIALIZED)
        upsert_items(conn, MATERIALIZED, [_item("a")])
        changed = _item("a")
        changed["properties"]["datetime"] = "2026-02-02T00:00:00Z"
        upsert_items(conn, MATERIALIZED, [changed])
        with conn.cursor() as cur:
            cur.execute("SELECT pgstac.get_item(%s, %s)", ("a", MATERIALIZED.dataset_id))
            stored = cur.fetchone()[0]
        assert stored["properties"]["datetime"] == "2026-02-02T00:00:00Z"

    def test_writing_goes_in_batches(self, conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch) -> None:
        """M3-11b will load 26,450 DEM tiles through this function — this proves the
        batching without needing that many rows here."""
        import earthx.catalog.pgstac as pgstac_module

        monkeypatch.setattr(pgstac_module, "ITEM_BATCH_SIZE", 2)
        batches: list[int] = []
        original = pgstac_module._upsert_item_batch

        def spy(conn: psycopg.Connection, items: list[dict[str, Any]]) -> None:
            batches.append(len(items))
            original(conn, items)

        monkeypatch.setattr(pgstac_module, "_upsert_item_batch", spy)
        load_collection(conn, MATERIALIZED)
        count = upsert_items(conn, MATERIALIZED, [_item(str(i)) for i in range(5)])

        assert count == 5
        assert batches == [2, 2, 1]
        assert _item_count(conn, MATERIALIZED.dataset_id) == 5


class TestFetchItem:
    async def test_a_missing_item_is_none(self, aconn: psycopg.AsyncConnection) -> None:
        await aconn.execute("SELECT pgstac.upsert_collection(%s::jsonb)", (_COLLECTION_JSON,))
        assert await fetch_item(aconn, MATERIALIZED.dataset_id, "no-such-item") is None

    async def test_a_written_item_comes_back(self, aconn: psycopg.AsyncConnection) -> None:
        await aconn.execute("SELECT pgstac.upsert_collection(%s::jsonb)", (_COLLECTION_JSON,))
        await aconn.execute("SELECT pgstac.upsert_items(%s::jsonb)", (json.dumps([_item("a")]),))

        item = await fetch_item(aconn, MATERIALIZED.dataset_id, "a")

        assert item is not None
        assert item["id"] == "a"
        assert item["collection"] == MATERIALIZED.dataset_id

    async def test_an_item_of_a_different_collection_is_not_found(self, aconn: psycopg.AsyncConnection) -> None:
        """`pgstac.get_item` takes the collection as a filter, not just a hint."""
        await aconn.execute("SELECT pgstac.upsert_collection(%s::jsonb)", (_COLLECTION_JSON,))
        await aconn.execute("SELECT pgstac.upsert_items(%s::jsonb)", (json.dumps([_item("a")]),))

        assert await fetch_item(aconn, "some-other-dataset", "a") is None
