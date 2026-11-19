"""The MeteoSwiss grids per unit against a real pgstac (M5-58 PR 2, plan §4.6, §11).

The source is the synthetic item list of `tests/earthx/discovery/mini_archive.py` behind the real ``gateway``; the run is
the whole command path of ``discovery.materialize`` (core, adapter, run log). Nothing reaches a network.
"""

from __future__ import annotations

import copy
from datetime import date
from pathlib import Path
from typing import Any

import psycopg
import pytest

from earthx.catalog.pgstac import load_collection, upsert_items, use_pgstac_search_path
from earthx.catalog.schema import apply_migrations
from earthx.discovery.materialize import MaterializeResult, run_materialize
from tests.catalog.entries import METEOSWISS_DAILY_PRECIP_1KM
from tests.earthx.discovery.mini_archive import (
    LIST_PATH,
    Archive,
    annual_file,
    day_name,
    entry,
    materialized_items,
    month_name,
    name,
    netcdf_file,
)

pytestmark = pytest.mark.anyio

CONFIG = entry(METEOSWISS_DAILY_PRECIP_1KM)
GRID = "ch01h"
NOV_16, NOV_17 = date(2026, 11, 16), date(2026, 11, 17)


@pytest.fixture
def db(conn: psycopg.Connection) -> psycopg.Connection:
    apply_migrations(conn)
    use_pgstac_search_path(conn)
    load_collection(conn, CONFIG)
    return conn


@pytest.fixture
def archive(tmp_path: Path) -> Archive:
    """Three days of the archive, two of a month item and two provisional days."""
    return Archive(
        {name("RhiresD", GRID, 2025): annual_file(tmp_path, 2025)},
        items={
            "month-10": {month_name("RhiresD", GRID, 2026, 10): netcdf_file(tmp_path, date(2026, 10, 1), [0, 1])},
            "day-16": {day_name("RprelimD", GRID, NOV_16): netcdf_file(tmp_path, NOV_16, [0])},
            "day-17": {day_name("RprelimD", GRID, NOV_17): netcdf_file(tmp_path, NOV_17, [0])},
        },
        expires={"day-16": "2027-01-15T00:00:00Z", "day-17": "2027-01-16T00:00:00Z"},
    )


async def run(conn: psycopg.Connection, archive: Archive) -> MaterializeResult:
    archive.seen.clear()
    async with archive.gateway() as gateway:
        return await run_materialize(conn, CONFIG, gateway=gateway, force=False)


def stored(conn: psycopg.Connection) -> dict[str, dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute("SELECT id, pgstac.get_item(id, collection) FROM pgstac.items WHERE collection = %s", (CONFIG.dataset_id,))
        return {item_id[-8:]: item for item_id, item in cur.fetchall()}


def requests(archive: Archive) -> list[str]:
    return [f"{r.method} {'list' if r.url.path == LIST_PATH else r.url.path.rsplit('/', 1)[1]}" for r in archive.seen]


class TestRuns:
    async def test_a_first_run_writes_every_day_with_its_state(self, db: psycopg.Connection, archive: Archive) -> None:
        result = await run(db, archive)
        assert result.units is not None and (result.units.status, result.units.units_new) == ("loaded", 4)
        items = stored(db)
        assert {day: item["properties"]["earthx:state"] for day, item in items.items()} == {
            "20250101": "final", "20250102": "final", "20250103": "final",
            "20261001": "final", "20261002": "final",
            "20261116": "provisional", "20261117": "provisional",
        }
        provisional = items["20261116"]
        assert provisional["assets"]["RhiresD"]["earthx:source_product"] == "RprelimD"
        assert provisional["assets"]["RhiresD"]["earthx:state"] == "provisional"
        assert provisional["properties"]["expires"] == "2027-01-15T00:00:00Z"
        assert provisional["properties"]["start_datetime"] == "2026-11-16T06:00:00Z"

    async def test_a_daily_run_without_change_is_one_request(self, db: psycopg.Connection, archive: Archive) -> None:
        await run(db, archive)
        before = stored(db)
        result = await run(db, archive)
        assert result.outcome.status == "unchanged" and result.items_written == 0
        assert requests(archive) == ["GET list"]
        assert stored(db) == before
        with db.cursor() as cur:
            cur.execute(
                "SELECT status FROM earthx_materialize_runs WHERE dataset_id = %s ORDER BY started_at DESC LIMIT 1",
                (CONFIG.dataset_id,),
            )
            assert cur.fetchone() == ("unchanged",)

    async def test_a_new_day_reads_only_its_file(self, db: psycopg.Connection, archive: Archive, tmp_path: Path) -> None:
        await run(db, archive)
        later = date(2026, 11, 18)
        archive.items["day-18"] = {day_name("RprelimD", GRID, later): netcdf_file(tmp_path, later, [0])}
        result = await run(db, archive)
        assert result.units is not None and (result.units.units_new, result.items_written) == (1, 1)
        assert archive.files_read() == {day_name("RprelimD", GRID, later)}

    async def test_the_final_month_replaces_the_provisional_day_under_the_same_id(
        self, db: psycopg.Connection, archive: Archive, tmp_path: Path
    ) -> None:
        await run(db, archive)
        old = stored(db)["20261116"]
        archive.items["month-11"] = {month_name("RhiresD", GRID, 2026, 11): netcdf_file(tmp_path, date(2026, 11, 1), [15])}
        archive.updated[month_name("RhiresD", GRID, 2026, 11)] = "2026-12-10T08:00:00Z"
        result = await run(db, archive)
        assert result.units is not None and result.units.items_replaced == 1
        new = stored(db)["20261116"]
        assert new["id"] == old["id"] and new["properties"]["earthx:state"] == "final"
        asset = new["assets"]["RhiresD"]
        assert "earthx:source_product" not in asset and "expires" not in new["properties"]
        assert asset["href"].endswith(month_name("RhiresD", GRID, 2026, 11))
        assert stored(db)["20261117"]["properties"]["earthx:state"] == "provisional"

    async def test_a_month_overwritten_on_the_26th_rewrites_only_its_days(
        self, db: psycopg.Connection, archive: Archive, tmp_path: Path
    ) -> None:
        await run(db, archive)
        before = stored(db)
        key = month_name("RhiresD", GRID, 2026, 10)
        archive.items["month-10"][key] = netcdf_file(tmp_path, date(2026, 10, 1), [0, 1], seed=1)
        result = await run(db, archive)
        assert result.units is not None and result.units.units_changed == 1
        assert archive.files_read() == {key}
        after = stored(db)
        assert {day for day in after if after[day] != before[day]} == {"20261001", "20261002"}

    async def test_the_archive_reprocessed_in_february_holds_over_the_month(
        self, db: psycopg.Connection, archive: Archive, tmp_path: Path
    ) -> None:
        await run(db, archive)
        annual = name("RhiresD", GRID, 2026)
        archive.files[annual] = annual_file(tmp_path, 2026, days=[273, 274])
        archive.updated[annual] = "2027-02-05T08:00:00Z"
        await run(db, archive)
        assert stored(db)["20261001"]["assets"]["RhiresD"]["href"].endswith(annual)

    async def test_a_provisional_day_gone_without_a_final_one_is_deleted(self, db: psycopg.Connection, archive: Archive) -> None:
        await run(db, archive)
        del archive.items["day-17"]
        result = await run(db, archive)
        assert result.items_deleted == 1 and "20261117" not in stored(db)


class TestTakeOver:
    """M5-58 F9: the items a run of `detect: whole` wrote (M5-11) are kept after one conditional HEAD per file."""

    async def m5_11_items(self, db: psycopg.Connection, archive: Archive) -> None:
        only_archive = Archive(dict(archive.files))
        items = await materialized_items(only_archive, CONFIG)
        for item in items:
            item["properties"].pop("earthx:state")
            for asset in item["assets"].values():
                asset.pop("earthx:state")
                asset.pop("updated")
        upsert_items(db, CONFIG, copy.deepcopy(items))

    async def test_an_unchanged_annual_file_is_kept_after_a_304(self, db: psycopg.Connection, archive: Archive) -> None:
        await self.m5_11_items(db, archive)
        result = await run(db, archive)
        assert result.units is not None
        assert (result.units.units_unchanged, result.units.units_new) == (1, 3)
        annual = name("RhiresD", GRID, 2025)
        asked = [request for request in archive.seen if request.url.path.endswith(annual)]
        assert [(request.method, "if-none-match" in request.headers) for request in asked] == [("HEAD", True)]
        items = stored(db)
        assert items["20250101"]["properties"]["earthx:state"] == "final"
        assert items["20250101"]["assets"]["RhiresD"]["earthx:state"] == "final"
        assert items["20261116"]["properties"]["earthx:state"] == "provisional"

    async def test_an_annual_file_changed_since_is_referenced_anew(
        self, db: psycopg.Connection, archive: Archive, tmp_path: Path
    ) -> None:
        await self.m5_11_items(db, archive)
        annual = name("RhiresD", GRID, 2025)
        archive.files[annual] = annual_file(tmp_path, 2025, days=[0, 1])
        result = await run(db, archive)
        assert result.units is not None and result.units.units_changed == 1
        assert "20250103" not in stored(db)
