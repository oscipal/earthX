"""The true total of a search over this platform's own collections (M5-56, Otto 18.11.2026).

GLO-30 over Russia found 300 tiles and said "300/300": pgstac named no ``numberMatched`` (its ``context`` was off), so the
list stopped at what it had loaded and could not say there were thousands. Synthetic 1-degree tiles of a GLO-30-shaped
collection, on both sides of the antimeridian; the area is a MultiPolygon cut at 180 degrees, as a place search gives it.
"""

from __future__ import annotations

from typing import Any

import psycopg
import pytest

from earthx.api.main import PGSTAC_COUNT_SETTINGS, postgres_settings
from earthx.catalog.pgstac import load_collection, upsert_items, use_pgstac_search_path
from tests.catalog.entries import COP_DEM_GLO_30
from tests.integration.test_materialize_command import _client, _dem_item

pytestmark = pytest.mark.anyio

COLUMNS = 30
TILES = 330
# From 165 E over the antimeridian to 165 W, eleven rows from 60 N.
TOP = 60 + TILES // COLUMNS
ACROSS = {
    "type": "MultiPolygon",
    "coordinates": [
        [[[165, 60], [180, 60], [180, TOP], [165, TOP], [165, 60]]],
        [[[-180, 60], [-165, 60], [-165, TOP], [-180, TOP], [-180, 60]]],
    ],
}
# Only the part east of the antimeridian, and an area no tile meets.
EAST = {"type": "Polygon", "coordinates": [[[165, 60], [179.5, 60], [179.5, TOP], [165, TOP], [165, 60]]]}
NOWHERE = {"type": "Polygon", "coordinates": [[[0, -10], [1, -10], [1, -9], [0, -9], [0, -10]]]}


def _tiles() -> list[dict[str, Any]]:
    tiles = []
    for i in range(TILES):
        west = float((165 + i % COLUMNS + 180) % 360 - 180)
        south = float(60 + i // COLUMNS)
        tiles.append(_dem_item(f"SYNTH_TILE_{i:04d}", [west, south, west + 1, south + 1]))
    return tiles


@pytest.fixture
def tiles_loaded(require_postgres_env: None):
    with psycopg.connect(autocommit=True) as conn:
        load_collection(conn, COP_DEM_GLO_30)
        upsert_items(conn, COP_DEM_GLO_30, _tiles())
    yield
    with psycopg.connect(autocommit=True) as conn:
        use_pgstac_search_path(conn)
        conn.execute("SELECT pgstac.delete_collection(%s)", (COP_DEM_GLO_30.dataset_id,))


async def _walk(area: dict[str, Any]) -> tuple[list[str], list[int | None]]:
    """Every page of a ``POST`` search over ``area`` (100 a page): the ids found and the ``numberMatched`` of each page."""
    found: list[str] = []
    totals: list[int | None] = []
    token = None
    async with _client() as client:
        for _ in range(20):
            body: dict[str, Any] = {"collections": [COP_DEM_GLO_30.dataset_id], "intersects": area, "limit": 100}
            if token is not None:
                body["token"] = token
            response = await client.post("/stac/search", json=body)
            assert response.status_code == 200, response.text
            page = response.json()
            found += [feature["id"] for feature in page["features"]]
            totals.append(page.get("numberMatched"))
            nxt = [link for link in page.get("links", []) if link.get("rel") == "next"]
            token = nxt[0].get("body", {}).get("token") if nxt else None
            if token is None:
                return found, totals
    raise AssertionError("the search did not end within 20 pages")


async def test_an_area_over_the_antimeridian_finds_every_tile_and_names_the_total(tiles_loaded: None) -> None:
    found, totals = await _walk(ACROSS)
    assert sorted(found) == sorted(tile["id"] for tile in _tiles())
    assert totals == [TILES] * 4


async def test_the_total_is_that_of_the_area_not_of_the_collection(tiles_loaded: None) -> None:
    found, totals = await _walk(EAST)
    east = [tile["id"] for tile in _tiles() if tile["bbox"][0] >= 0]
    assert sorted(found) == sorted(east)
    assert set(totals) == {len(east)}


async def test_an_area_without_tiles_names_a_total_of_none_found(tiles_loaded: None) -> None:
    found, totals = await _walk(NOWHERE)
    assert found == []
    assert totals == [0]


def test_every_connection_of_pgstac_counts_and_keeps_no_count() -> None:
    server = postgres_settings().server_settings.model_dump()
    assert server["pgstac.context"] == "on"
    assert server["pgstac.context_stats_ttl"] == "0 seconds"
    assert PGSTAC_COUNT_SETTINGS.items() <= server.items()
    # pgstac's own search path stays.
    assert server["search_path"] == "pgstac,public"
