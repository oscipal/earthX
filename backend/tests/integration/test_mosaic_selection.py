"""T-C: the selection of a mosaic against a real Postgres and a real pgstac (M5-30b part 3, adr/0032 §10.2).

What a unit test cannot show is what the table does: that a row survives a write, that an expired row reads as gone
for the tile, that creating a selection again moves its end seven days out, and that the items of a materialized
dataset really come out of pgstac by id in one query. The first half is the table and the store over it, inside the
transaction that is rolled back; the second is the real app with its real lifespan, in the way
``test_tiler_materialized.py`` runs it.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from dataclasses import replace
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient

from earthx.api.mosaic_selection import Selection, SelectionStore
from earthx.api.tiler import build_app
from earthx.catalog import mosaic_selection as stored
from earthx.catalog.pgstac import load_collection, search_items_by_ids, upsert_items, use_pgstac_search_path
from earthx.catalog.registry import CoverageProvider, DatasetRegistry, ItemHolding, SearchCapabilities
from earthx.catalog.schema import apply_migrations, discover_migrations
from tests.catalog.entries import SENTINEL_2_L2A

from .conftest import SHIPPED_TABLES

DATASET = "earthx-test-mosaic-selection"
ASSETS = ("visual",)
ITEMS = ("a", "b", "c")


class OneConnection:
    """A pool of the one connection of the test, which the transaction of the test rolls back."""

    def __init__(self, conn: psycopg.AsyncConnection) -> None:
        self._conn = conn

    @asynccontextmanager
    async def connection(self) -> AsyncIterator[psycopg.AsyncConnection]:
        yield self._conn


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def _selection(selection_id: str, dataset: str = DATASET, items: tuple[str, ...] = ITEMS) -> Selection:
    sources = {item_id: {"bbox": [float(n), 0.0, float(n) + 1.0, 1.0]} for n, item_id in enumerate(items)}
    described = {asset: {"stored": asset} for asset in ASSETS}
    return Selection.build(selection_id, dataset, ASSETS, sources, list(items), described)


@pytest.fixture
async def aconn_migrated(aconn: psycopg.AsyncConnection) -> psycopg.AsyncConnection:
    """The migrated tables, inside the transaction that gets rolled back."""
    for table in SHIPPED_TABLES:
        await aconn.execute(f"DROP TABLE IF EXISTS {table}")
    for migration in discover_migrations():
        await aconn.execute(migration.sql)
    return aconn


async def _expire(conn: psycopg.AsyncConnection, selection_id: str, *, minutes: int = 1) -> None:
    await conn.execute(
        f"UPDATE {stored.TABLE} SET expires_at = now() - make_interval(mins => %s) WHERE selection_id = %s",
        (minutes, selection_id),
    )


async def _term(conn: psycopg.AsyncConnection, selection_id: str) -> Any:
    async with conn.cursor() as cur:
        await cur.execute(f"SELECT expires_at - now() FROM {stored.TABLE} WHERE selection_id = %s", (selection_id,))
        row = await cur.fetchone()
    return row[0]


@pytest.mark.anyio
class TestTheTable:
    async def test_what_goes_in_comes_back_out(self, aconn_migrated: psycopg.AsyncConnection) -> None:
        await stored.save(aconn_migrated, "a" * 32, DATASET, {"items": ["x"], "order": ["x"]})
        assert await stored.load(aconn_migrated, "a" * 32) == (DATASET, {"items": ["x"], "order": ["x"]})

    async def test_an_id_never_written_is_missing(self, aconn_migrated: psycopg.AsyncConnection) -> None:
        assert await stored.load(aconn_migrated, "b" * 32) is None
        assert await stored.renew(aconn_migrated, "b" * 32) is False

    async def test_the_term_is_seven_days(self, aconn_migrated: psycopg.AsyncConnection) -> None:
        await stored.save(aconn_migrated, "a" * 32, DATASET, {})
        term = await _term(aconn_migrated, "a" * 32)
        assert term.days == 7 and term.total_seconds() == stored.TERM_S

    async def test_an_expired_row_reads_as_gone_and_cannot_be_renewed(self, aconn_migrated: psycopg.AsyncConnection) -> None:
        await stored.save(aconn_migrated, "a" * 32, DATASET, {})
        await _expire(aconn_migrated, "a" * 32)
        assert await stored.load(aconn_migrated, "a" * 32) is None
        assert await stored.renew(aconn_migrated, "a" * 32) is False

    async def test_renewing_moves_the_end_to_seven_days_from_now(self, aconn_migrated: psycopg.AsyncConnection) -> None:
        await stored.save(aconn_migrated, "a" * 32, DATASET, {})
        await aconn_migrated.execute(
            f"UPDATE {stored.TABLE} SET expires_at = now() + interval '1 day' WHERE selection_id = %s", ("a" * 32,)
        )
        assert await stored.renew(aconn_migrated, "a" * 32) is True
        assert (await _term(aconn_migrated, "a" * 32)).total_seconds() == stored.TERM_S

    async def test_saving_again_replaces_a_row_that_has_expired(self, aconn_migrated: psycopg.AsyncConnection) -> None:
        await stored.save(aconn_migrated, "a" * 32, DATASET, {"v": 1})
        await _expire(aconn_migrated, "a" * 32)
        await stored.save(aconn_migrated, "a" * 32, DATASET, {"v": 2})
        assert await stored.load(aconn_migrated, "a" * 32) == (DATASET, {"v": 2})

    async def test_the_row_holds_no_area(self, aconn_migrated: psycopg.AsyncConnection) -> None:
        async with aconn_migrated.cursor() as cur:
            await cur.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name = 'earthx_mosaic_selection' "
                "ORDER BY ordinal_position"
            )
            columns = [row[0] for row in await cur.fetchall()]
        assert columns == ["selection_id", "dataset_id", "content", "created_at", "expires_at"]


@pytest.mark.anyio
class TestTheStore:
    async def test_a_selection_comes_back_with_its_order_outlines_and_extent(
        self, aconn_migrated: psycopg.AsyncConnection
    ) -> None:
        store = SelectionStore(OneConnection(aconn_migrated))
        await store.put(_selection("a" * 32))
        reader = SelectionStore(OneConnection(aconn_migrated))  # another process: nothing in memory
        loaded = await reader.get("a" * 32)
        assert loaded is not None
        assert (loaded.dataset_id, loaded.assets, loaded.items, loaded.order) == (DATASET, ASSETS, ITEMS, ITEMS)
        assert loaded.bounds == (0.0, 0.0, 3.0, 1.0)
        assert sorted(loaded.outlines) == list(ITEMS)
        assert loaded.described == {asset: {"stored": asset} for asset in ASSETS}

    async def test_an_expired_row_is_gone_for_a_process_that_has_not_seen_it(
        self, aconn_migrated: psycopg.AsyncConnection
    ) -> None:
        await SelectionStore(OneConnection(aconn_migrated)).put(_selection("a" * 32))
        await _expire(aconn_migrated, "a" * 32)
        assert await SelectionStore(OneConnection(aconn_migrated)).get("a" * 32) is None

    async def test_memory_may_keep_a_selection_for_a_few_minutes_and_no_longer(
        self, aconn_migrated: psycopg.AsyncConnection
    ) -> None:
        clock = Clock()
        store = SelectionStore(OneConnection(aconn_migrated), clock=clock, kept_s=120.0)
        await store.put(_selection("a" * 32))
        await _expire(aconn_migrated, "a" * 32)
        clock.now += 119.0
        assert await store.get("a" * 32) is not None  # content never changes, so memory is safe for a while
        clock.now += 2.0
        assert await store.get("a" * 32) is None  # then the row is asked, and it has expired

    async def test_memory_holds_a_bounded_number_of_selections_and_scenes(
        self, aconn_migrated: psycopg.AsyncConnection
    ) -> None:
        store = SelectionStore(OneConnection(aconn_migrated), max_entries=2, max_items=100)
        for character in "abc":
            await store.put(_selection(character * 32))
        for character in "abc":
            await _expire(aconn_migrated, character * 32)
        assert await store.get("a" * 32) is None  # the oldest left memory, and the row has expired
        assert await store.get("b" * 32) is not None and await store.get("c" * 32) is not None
        heavy = SelectionStore(OneConnection(aconn_migrated), max_items=4)
        await heavy.put(_selection("d" * 32))  # three scenes
        await heavy.put(_selection("e" * 32))  # three more: over the four, so the first leaves
        await _expire(aconn_migrated, "d" * 32)
        assert await heavy.get("d" * 32) is None

    async def test_renewing_asks_the_row(self, aconn_migrated: psycopg.AsyncConnection) -> None:
        store = SelectionStore(OneConnection(aconn_migrated))
        assert await store.renew("a" * 32) is False
        await store.put(_selection("a" * 32))
        assert await store.renew("a" * 32) is True


@pytest.mark.anyio
async def test_pgstac_gives_the_items_with_these_ids_in_one_query(require_postgres_env: None) -> None:
    with psycopg.connect(autocommit=True) as sync:
        load_collection(sync, MATERIALIZED)
        upsert_items(sync, MATERIALIZED, [_item(item_id) for item_id in ITEMS])
    try:
        async with await psycopg.AsyncConnection.connect(autocommit=True) as conn:
            found = await search_items_by_ids(conn, DATASET, ["a", "c", "nowhere"])
            assert sorted(item["id"] for item in found) == ["a", "c"]
            assert await search_items_by_ids(conn, DATASET, []) == []
            assert await search_items_by_ids(conn, "another-collection", ["a"]) == []
            # the search path was set for that transaction only: the connection is as it was found
            async with conn.cursor() as cur:
                await cur.execute("SHOW search_path")
                row = await cur.fetchone()
            assert row is not None and "pgstac" not in row[0]
    finally:
        with psycopg.connect(autocommit=True) as sync:
            use_pgstac_search_path(sync)
            sync.execute("SELECT pgstac.delete_collection(%s)", (DATASET,))


MATERIALIZED = replace(
    SENTINEL_2_L2A,
    dataset_id=DATASET,
    source=replace(
        SENTINEL_2_L2A.source,
        item_holding=ItemHolding.MATERIALIZED,
        source_collection_id=DATASET,
        asset_hosts=("assets.example.invalid",),
    ),
    coverage=replace(SENTINEL_2_L2A.coverage, provider=CoverageProvider.LOCAL_SQL),
    search_filters=(),
    search_capabilities=SearchCapabilities(evaluate=False, aoi_coverage=False),
)
BASE = f"/collections/{DATASET}/mosaic"


def _item(item_id: str) -> dict[str, Any]:
    west = float(ITEMS.index(item_id)) if item_id in ITEMS else 0.0
    return {
        "id": item_id,
        "type": "Feature",
        "stac_version": "1.0.0",
        "collection": DATASET,
        "bbox": [west, 0.0, west + 1.0, 1.0],
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[west, 0.0], [west + 1.0, 0.0], [west + 1.0, 1.0], [west, 1.0], [west, 0.0]]],
        },
        "properties": {"datetime": "2026-01-01T00:00:00Z", "proj:code": "EPSG:32632", "s2:datatake_id": "D1"},
        "assets": {"visual": {"href": f"https://assets.example.invalid/{item_id}.tif"}},
        "links": [],
    }


@pytest.fixture
def materialized_loaded(require_postgres_env: None) -> Iterator[None]:
    with psycopg.connect(autocommit=True) as conn:
        apply_migrations(conn)
        load_collection(conn, MATERIALIZED)
        upsert_items(conn, MATERIALIZED, [_item(item_id) for item_id in ITEMS])
        conn.execute(f"DELETE FROM {stored.TABLE} WHERE dataset_id = %s", (DATASET,))
    yield
    with psycopg.connect(autocommit=True) as conn:
        conn.execute(f"DELETE FROM {stored.TABLE} WHERE dataset_id = %s", (DATASET,))
        use_pgstac_search_path(conn)
        conn.execute("SELECT pgstac.delete_collection(%s)", (DATASET,))


@pytest.fixture
def app_client(materialized_loaded: None) -> Iterator[TestClient]:
    """The real tiler app with its real lifespan (a real pool), over a registry of one materialized dataset."""
    with TestClient(build_app(DatasetRegistry((MATERIALIZED,)))) as client:
        yield client


def _row(selection_id: str) -> tuple[str, Any] | None:
    with psycopg.connect(autocommit=True) as conn:
        row = conn.execute(
            f"SELECT dataset_id, expires_at - now() FROM {stored.TABLE} WHERE selection_id = %s", (selection_id,)
        ).fetchone()
    return None if row is None else (row[0], row[1])


class TestThroughTheRealApp:
    def test_a_selection_of_materialized_scenes_is_made_from_pgstac_stored_and_read_by_its_id(
        self, app_client: TestClient
    ) -> None:
        created = app_client.post(BASE, json={"items": ["c", "a", "b"], "assets": list(ASSETS)})
        assert created.status_code == 201, created.text
        selection = created.json()["id"]
        assert selection == stored.selection_id(DATASET, ASSETS, ITEMS)
        row = _row(selection)
        assert row is not None and row[0] == DATASET and row[1].days == 6  # seven days, less the moments gone since
        body = app_client.get(created.json()["tilejson"]).json()
        assert body["earthx:order"] == ["a", "b", "c"]
        assert body["bounds"][0] <= 0.0 and body["bounds"][2] >= 3.0

    def test_creating_it_again_moves_the_end_seven_days_out(self, app_client: TestClient) -> None:
        selection = app_client.post(BASE, json={"items": ["a", "b"], "assets": list(ASSETS)}).json()["id"]
        with psycopg.connect(autocommit=True) as conn:
            conn.execute(
                f"UPDATE {stored.TABLE} SET expires_at = now() + interval '1 day' WHERE selection_id = %s", (selection,)
            )
        again = app_client.post(BASE, json={"items": ["b", "a"], "assets": list(ASSETS)})
        assert again.status_code == 200 and again.json()["id"] == selection
        row = _row(selection)
        assert row is not None and row[1].days == 6

    def test_a_scene_pgstac_does_not_have_is_a_404_that_names_it(self, app_client: TestClient) -> None:
        response = app_client.post(BASE, json={"items": ["a", "nowhere"], "assets": list(ASSETS)})
        assert response.status_code == 404 and "nowhere" in response.json()["detail"]

    def test_an_expired_row_is_a_410_for_a_process_that_has_not_seen_it_and_creating_it_again_revives_it(
        self, app_client: TestClient
    ) -> None:
        selection = app_client.post(BASE, json={"items": ["a", "b"], "assets": list(ASSETS)}).json()["id"]
        with psycopg.connect(autocommit=True) as conn:
            conn.execute(
                f"UPDATE {stored.TABLE} SET expires_at = now() - interval '1 minute' WHERE selection_id = %s",
                (selection,),
            )
        tilejson = f"{BASE}/{selection}/WebMercatorQuad/tilejson.json"
        with TestClient(build_app(DatasetRegistry((MATERIALIZED,)))) as fresh:
            gone = fresh.get(tilejson)
            assert gone.status_code == 410 and "POST" in gone.json()["detail"]
            again = fresh.post(BASE, json={"items": ["a", "b"], "assets": list(ASSETS)})
            assert again.status_code == 201 and again.json()["id"] == selection
            assert fresh.get(tilejson).status_code == 200

    def test_an_id_that_was_never_stored_is_a_410_and_another_datasets_selection_is_a_404(
        self, app_client: TestClient
    ) -> None:
        assert app_client.get(f"{BASE}/{'0' * 32}/WebMercatorQuad/tilejson.json").status_code == 410
        selection = app_client.post(BASE, json={"items": ["a", "b"], "assets": list(ASSETS)}).json()["id"]
        with psycopg.connect(autocommit=True) as conn:
            conn.execute(f"UPDATE {stored.TABLE} SET dataset_id = 'another' WHERE selection_id = %s", (selection,))
        with TestClient(build_app(DatasetRegistry((MATERIALIZED,)))) as fresh:
            assert fresh.get(f"{BASE}/{selection}/WebMercatorQuad/tilejson.json").status_code == 404
