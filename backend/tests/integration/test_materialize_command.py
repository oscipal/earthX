"""T-C: the materialize command against a real pgstac (M3-11b plan §5).

``run_materialize`` is exercised directly, against a mocked bucket
(``httpx.MockTransport``) — the command's own network calls go nowhere near a
real source here (CLAUDE.md: external sources only through synthetic
fixtures); ``main``'s real-``Gateway`` wrapper is exercised in
``backend/tests_live`` instead (T-D).

The collection this file writes and reads is a synthetic *materialized* entry
of its own, not the real ``cop-dem-glo-30`` — ``TestSearchOverACopDemShapedCollection``
is the one exception, using the real registry entry (and real tile-name ids)
to prove the DEM specifically is findable end to end, per the plan's own T-C
bullet (§5).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from typing import Any

import httpx
import psycopg
import pytest

from earthx.adapters import NotMaterialized
from earthx.api.main import app
from earthx.catalog.datasets import COP_DEM_GLO_30, SENTINEL_2_L2A
from earthx.catalog.pgstac import (
    MaterializeRunRecord,
    delete_items_except,
    last_source_version,
    load_collection,
    record_materialize_run,
    upsert_items,
    use_pgstac_search_path,
)
from earthx.catalog.registry import AdapterKind, CoverageProvider, ItemHolding
from earthx.discovery.materialize import run_materialize
from earthx.gateway import Policy, UpstreamError
from earthx.gateway.client import Gateway

pytestmark = pytest.mark.anyio

HOST = "bucket.example.invalid"

MATERIALIZED = replace(
    SENTINEL_2_L2A,
    dataset_id="earthx-test-materialize-command",
    source=replace(
        SENTINEL_2_L2A.source,
        adapter=AdapterKind.COP_DEM_BUCKET,
        endpoint=f"https://{HOST}",
        asset_hosts=(HOST,),
        item_holding=ItemHolding.MATERIALIZED,
        source_collection_id="earthx-test-materialize-command",
        harvest_run=None,
    ),
    coverage=replace(SENTINEL_2_L2A.coverage, provider=CoverageProvider.LOCAL_SQL),
)

TILE_A = "Copernicus_DSM_COG_10_N46_00_E010_00_DEM"
TILE_B = "Copernicus_DSM_COG_10_S34_00_W058_00_DEM"


def _public(host: str, port: int) -> tuple[str, ...]:
    return ("93.184.216.34",)


def _bucket_gateway(*, tile_names: list[str], etag: str, blacklist: list[str] | None = None) -> Gateway:
    """Answers the three requests `materialize_items` makes for `MATERIALIZED`."""
    body = ("\r\n".join(tile_names) + "\r\n" if tile_names else "").encode()
    blacklist_body = "\n".join(blacklist or []).encode()

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/tileList.txt"):
            if request.headers.get("if-none-match") == etag:
                return httpx.Response(304)
            return httpx.Response(200, content=body, headers={"etag": etag})
        if path.endswith("/blacklist.txt"):
            return httpx.Response(200, content=blacklist_body)
        prefixes = "".join(f"<CommonPrefixes><Prefix>{name}/</Prefix></CommonPrefixes>" for name in tile_names)
        xml = (
            '<?xml version="1.0"?><ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
            f"{prefixes}</ListBucketResult>"
        ).encode()
        return httpx.Response(200, content=xml)

    async def sleep(seconds: float) -> None:
        return None

    policy = Policy(allowed_hosts=frozenset({HOST}))
    return Gateway(policy, transport=httpx.MockTransport(handler), resolve=_public, sleep=sleep)


def _item_count(conn: psycopg.Connection, collection_id: str) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM pgstac.items WHERE collection = %s", (collection_id,))
        return cur.fetchone()[0]


async def _run(conn: psycopg.Connection, *, tile_names: list[str], etag: str, force: bool = False):
    """`run_materialize` against `MATERIALIZED` and a bucket answering `tile_names`."""
    gateway = _bucket_gateway(tile_names=tile_names, etag=etag)
    return await run_materialize(conn, MATERIALIZED, gateway=gateway, force=force)


class TestRunMaterializeLoadsAndIsIdempotent:
    async def test_a_fresh_run_writes_every_item(self, conn: psycopg.Connection) -> None:
        load_collection(conn, MATERIALIZED)
        result = await _run(conn, tile_names=[TILE_A, TILE_B], etag='"v1"')

        assert result.outcome.status == "loaded"
        assert result.items_written == 2
        assert result.items_deleted == 0
        assert _item_count(conn, MATERIALIZED.dataset_id) == 2
        assert last_source_version(conn, MATERIALIZED.dataset_id) == '"v1"'

    async def test_a_second_run_with_the_same_version_changes_nothing(self, conn: psycopg.Connection) -> None:
        load_collection(conn, MATERIALIZED)
        first = await _run(conn, tile_names=[TILE_A], etag='"v1"')
        assert first.outcome.status == "loaded"

        second = await _run(conn, tile_names=[TILE_A], etag='"v1"')

        assert second.outcome.status == "unchanged"
        assert second.items_written == 0
        assert second.items_deleted == 0
        assert _item_count(conn, MATERIALIZED.dataset_id) == 1

    async def test_running_a_loaded_batch_twice_leaves_the_same_rows(self, conn: psycopg.Connection) -> None:
        """`upsert` (M3-11a): a repeated *load* (not just an unchanged skip) is
        idempotent too — a version bump that lists the same tiles again."""
        load_collection(conn, MATERIALIZED)
        await _run(conn, tile_names=[TILE_A, TILE_B], etag='"v1"')
        result = await _run(conn, tile_names=[TILE_A, TILE_B], etag='"v2"')

        assert result.outcome.status == "loaded"
        assert result.items_written == 2
        assert _item_count(conn, MATERIALIZED.dataset_id) == 2


class TestForce:
    async def test_force_reloads_even_though_the_version_is_unchanged(self, conn: psycopg.Connection) -> None:
        load_collection(conn, MATERIALIZED)
        await _run(conn, tile_names=[TILE_A], etag='"v1"')

        result = await _run(conn, tile_names=[TILE_A], etag='"v1"', force=True)

        assert result.outcome.status == "loaded"
        assert result.items_written == 1


class TestDeletesStaleItems:
    async def test_a_tile_no_longer_listed_is_removed(self, conn: psycopg.Connection) -> None:
        load_collection(conn, MATERIALIZED)
        await _run(conn, tile_names=[TILE_A, TILE_B], etag='"v1"')
        assert _item_count(conn, MATERIALIZED.dataset_id) == 2

        result = await _run(conn, tile_names=[TILE_A], etag='"v2"')

        assert result.items_written == 1
        assert result.items_deleted == 1
        assert _item_count(conn, MATERIALIZED.dataset_id) == 1
        with conn.cursor() as cur:
            cur.execute("SELECT pgstac.get_item(%s, %s)", (TILE_B, MATERIALIZED.dataset_id))
            assert cur.fetchone()[0] is None


class TestAbortLeavesTheDatabaseUnchanged:
    async def test_a_source_error_writes_nothing_and_records_no_run(self, conn: psycopg.Connection) -> None:
        load_collection(conn, MATERIALIZED)

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/tileList.txt"):
                return httpx.Response(500)
            raise AssertionError("should not be reached after tileList.txt fails")

        async def sleep(seconds: float) -> None:
            return None

        gateway = Gateway(
            Policy(allowed_hosts=frozenset({HOST})),
            transport=httpx.MockTransport(handler),
            resolve=_public,
            sleep=sleep,
        )

        with pytest.raises(UpstreamError):
            await run_materialize(conn, MATERIALIZED, gateway=gateway, force=False)

        assert _item_count(conn, MATERIALIZED.dataset_id) == 0
        assert last_source_version(conn, MATERIALIZED.dataset_id) is None


class TestRefusesAFederatedDataset:
    async def test_nothing_is_asked_of_the_source_or_written(self, conn: psycopg.Connection) -> None:
        load_collection(conn, SENTINEL_2_L2A)
        gateway = _bucket_gateway(tile_names=[TILE_A], etag='"v1"')
        with pytest.raises(NotMaterialized):
            await run_materialize(conn, SENTINEL_2_L2A, gateway=gateway, force=False)


class TestDeleteItemsExceptRefusesAFederatedEntry:
    def test_it_matches_upsert_items_own_guard(self, conn: psycopg.Connection) -> None:
        from earthx.catalog.pgstac import PgstacError

        load_collection(conn, SENTINEL_2_L2A)
        with pytest.raises(PgstacError, match="federated"):
            delete_items_except(conn, SENTINEL_2_L2A, [])


class TestRunLog:
    def test_last_source_version_is_none_before_any_run(self, conn: psycopg.Connection) -> None:
        assert last_source_version(conn, "no-run-has-ever-happened-for-this-id") is None

    def test_the_most_recent_run_wins(self, conn: psycopg.Connection) -> None:
        from datetime import datetime, timedelta, timezone

        now = datetime.now(timezone.utc)
        earlier = MaterializeRunRecord(
            dataset_id=MATERIALIZED.dataset_id,
            started_at=now - timedelta(hours=1),
            finished_at=now - timedelta(hours=1),
            status="loaded",
            source_version='"older"',
            items_written=1,
            items_deleted=0,
            listed=1,
            missing=0,
            withheld=0,
        )
        later = replace(earlier, started_at=now, finished_at=now, source_version='"newer"')
        record_materialize_run(conn, earlier)
        record_materialize_run(conn, later)
        assert last_source_version(conn, MATERIALIZED.dataset_id) == '"newer"'


# --------------------------------------------------------------------------------
# The real cop-dem-glo-30 entry, found over the STAC API (plan §5).
# --------------------------------------------------------------------------------


def _dem_item(name: str, bbox: list[float]) -> dict[str, Any]:
    west, south, east, north = bbox
    ring = [[west, south], [east, south], [east, north], [west, north], [west, south]]
    return {
        "id": name,
        "type": "Feature",
        "stac_version": "1.0.0",
        "collection": COP_DEM_GLO_30.dataset_id,
        "bbox": bbox,
        "geometry": {"type": "Polygon", "coordinates": [ring]},
        "properties": {
            "datetime": None,
            "start_datetime": "2010-12-01T00:00:00Z",
            "end_datetime": "2015-01-31T23:59:59Z",
            "gsd": 30.0,
            "proj:code": "EPSG:4326",
        },
        "assets": {"data": {"href": f"{COP_DEM_GLO_30.source.endpoint}/{name}/{name}.tif"}},
        "links": [],
    }


@pytest.fixture
def dem_loaded(require_postgres_env: None):
    with psycopg.connect(autocommit=True) as conn:
        load_collection(conn, COP_DEM_GLO_30)
        upsert_items(
            conn,
            COP_DEM_GLO_30,
            [_dem_item(TILE_A, [10.0, 46.0, 11.0, 47.0]), _dem_item(TILE_B, [-58.0, -34.0, -57.0, -33.0])],
        )
    yield
    with psycopg.connect(autocommit=True) as conn:
        use_pgstac_search_path(conn)
        conn.execute("SELECT pgstac.delete_collection(%s)", (COP_DEM_GLO_30.dataset_id,))


@asynccontextmanager
async def _client() -> AsyncIterator[httpx.AsyncClient]:
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


class TestSearchOverACopDemShapedCollection:
    async def test_a_bbox_over_one_tile_finds_only_that_tile(self, dem_loaded: None) -> None:
        async with _client() as client:
            response = await client.get(
                "/stac/search",
                params={"collections": COP_DEM_GLO_30.dataset_id, "bbox": "10,46,11,47"},
            )
        assert response.status_code == 200, response.text
        ids = [feature["id"] for feature in response.json()["features"]]
        assert ids == [TILE_A]

    async def test_the_item_is_reachable_by_id(self, dem_loaded: None) -> None:
        async with _client() as client:
            response = await client.get(f"/stac/collections/{COP_DEM_GLO_30.dataset_id}/items/{TILE_B}")
        assert response.status_code == 200, response.text
        assert response.json()["id"] == TILE_B
