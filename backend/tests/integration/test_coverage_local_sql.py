"""T-C: the `local-sql` area way against a real pgstac (M3-11c plan step §5).

Proves what `tests/earthx/api/test_coverage_route.py` mocks out: the union really
comes from a materialized collection's own items in pgstac, through the process's
real `earthx_cache_pool` (the same pool `test_tiler_materialized.py` already proves
for a single item) — not from a stand-in for either.

The test collection carries four shapes at once, all in one dataset, so that "the
area is the union of its footprints" is checked against something that is not
already one connected blob: a 2x2 block, an isolated island, a ring of eight tiles
around a one-tile hole, and two tiles that only touch across the antimeridian if the
query's own clip stitches them there. All synthetic, on an invented grid — no real
coordinates, real dataset id, or the DEM (`CLAUDE.md`: fixtures only synthetic).
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from typing import Any

import psycopg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from earthx.api.coverage_route import build_router
from earthx.api.dependencies import cache_pool
from earthx.catalog.datasets import SENTINEL_2_L2A
from earthx.catalog.load import main as load_catalog
from earthx.catalog.pgstac import load_collection, upsert_items, use_pgstac_search_path
from earthx.catalog.registry import CoverageProvider, DatasetRegistry, ItemHolding
from earthx.gateway import Policy
from earthx.gateway.client import Gateway

DATASET_ID = "earthx-test-local-sql-area"

# `time_range=True` here (unlike the real DEM, M3-11b): this dataset carries a
# genuine time filter test, which needs an axis to filter on at all. The
# `time_range=False` behaviour (ignore `datetime` outright) is a different entry,
# `NO_TIME_AXIS` below.
AREA_DATASET = replace(
    SENTINEL_2_L2A,
    dataset_id=DATASET_ID,
    capabilities=replace(SENTINEL_2_L2A.capabilities, single_coverage_product=True),
    coverage=replace(SENTINEL_2_L2A.coverage, provider=CoverageProvider.LOCAL_SQL),
    source=replace(
        SENTINEL_2_L2A.source,
        item_holding=ItemHolding.MATERIALIZED,
        source_collection_id=DATASET_ID,
        harvest_run=None,
        asset_hosts=("assets.example.invalid",),
    ),
)

NO_TIME_DATASET_ID = "earthx-test-local-sql-area-no-time-axis"
NO_TIME_AXIS = replace(
    AREA_DATASET,
    dataset_id=NO_TIME_DATASET_ID,
    capabilities=replace(AREA_DATASET.capabilities, time_range=False),
    source=replace(AREA_DATASET.source, source_collection_id=NO_TIME_DATASET_ID),
)

# Two time windows, so "outside the item time" and "inside" are two different,
# checkable answers rather than one dataset that always matches.
WINDOW_A = ("2020-01-01T00:00:00Z", "2020-06-30T00:00:00Z")
WINDOW_B = ("2021-01-01T00:00:00Z", "2021-06-30T00:00:00Z")


def _tile(
    item_id: str,
    west: float,
    south: float,
    east: float,
    north: float,
    window: tuple[str, str],
    *,
    collection: str = DATASET_ID,
) -> dict[str, Any]:
    start, end = window
    return {
        "id": item_id,
        "type": "Feature",
        "stac_version": "1.0.0",
        "collection": collection,
        "bbox": [west, south, east, north],
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[west, south], [east, south], [east, north], [west, north], [west, south]]],
        },
        "properties": {"datetime": None, "start_datetime": start, "end_datetime": end},
        "assets": {},
        "links": [],
    }


def _block() -> list[dict[str, Any]]:
    """A 2x2 block of unit tiles (window A) — its union is one 2 degree square."""
    return [
        _tile("block-sw", 0, 0, 1, 1, WINDOW_A),
        _tile("block-se", 1, 0, 2, 1, WINDOW_A),
        _tile("block-nw", 0, 1, 1, 2, WINDOW_A),
        _tile("block-ne", 1, 1, 2, 2, WINDOW_A),
    ]


def _island() -> dict[str, Any]:
    """One tile, far from everything else, in window B — the time filter's other case."""
    return _tile("island", 10, 10, 11, 11, WINDOW_B)


def _ring_with_hole() -> list[dict[str, Any]]:
    """Eight unit tiles around a missing centre (window A) — a 3x3 square with a
    one-tile hole once unioned."""
    tiles = []
    for x in (20, 21, 22):
        for y in (20, 21, 22):
            if (x, y) == (21, 21):
                continue
            tiles.append(_tile(f"ring-{x}-{y}", x, y, x + 1, y + 1, WINDOW_A))
    return tiles


def _dateline_tiles() -> list[dict[str, Any]]:
    """Two tiles that touch only if a query's clip crosses the antimeridian
    (`local_coverage._clip_sql`'s two-envelope branch)."""
    return [
        _tile("dateline-east", 179, -60, 180, -59, WINDOW_A),
        _tile("dateline-west", -180, -60, -179, -59, WINDOW_A),
    ]


def _all_items() -> list[dict[str, Any]]:
    return [*_block(), _island(), *_ring_with_hole(), *_dateline_tiles()]


@pytest.fixture
def area_dataset_loaded(require_postgres_env: None) -> Any:
    # `catalog.load`'s own migrations (`002_search_cache.sql` and friends) are what
    # actually create `public.earthx_search_cache` outside of the one rolled-back
    # transaction `test_search_cache.py` runs it in for itself
    # (`test_api_federating.py::require_catalog_loaded` takes the same route for
    # the same reason): this route's real pool commits with `autocommit=True`, so
    # the table has to exist for real, not just inside a transaction this test
    # would roll back. Idempotent (`catalog.load`'s own docstring).
    assert load_catalog() == 0
    with psycopg.connect(autocommit=True) as conn:
        load_collection(conn, AREA_DATASET)
        load_collection(conn, NO_TIME_AXIS)
        upsert_items(conn, AREA_DATASET, _all_items())
        upsert_items(
            conn, NO_TIME_AXIS, [_tile("only-tile", 0, 0, 1, 1, WINDOW_A, collection=NO_TIME_DATASET_ID)]
        )
        # A cache row an earlier run of this file left behind would answer a later
        # test's request without ever running the SQL under test — same caution
        # `test_api_federating.py::require_catalog_loaded` takes for its own cache.
        conn.execute("DELETE FROM public.earthx_search_cache WHERE dataset_id = ANY(%s)", ([DATASET_ID, NO_TIME_DATASET_ID],))
    yield
    with psycopg.connect(autocommit=True) as conn:
        use_pgstac_search_path(conn)
        conn.execute("SELECT pgstac.delete_collection(%s)", (DATASET_ID,))
        conn.execute("SELECT pgstac.delete_collection(%s)", (NO_TIME_DATASET_ID,))


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    async with cache_pool() as pool:
        app.state.earthx_cache_pool = pool
        yield


@pytest.fixture
def app_client(area_dataset_loaded: None) -> Any:
    """The real coverage route, its real lifespan (a real `cache_pool()`), against
    a registry of the two entries above — the same pattern
    `test_tiler_materialized.py::app_client` already uses for the tiler."""
    registry = DatasetRegistry((AREA_DATASET, NO_TIME_AXIS))
    app = FastAPI(lifespan=_lifespan)
    app.include_router(build_router(registry=registry))
    # No coverage answer here ever calls a gateway (the whole point of the area
    # way), but the route still reads `request.app.state.earthx_gateway`
    # unconditionally before deciding which path to take.
    app.state.earthx_gateway = Gateway(Policy(allowed_hosts=frozenset()))
    with TestClient(app) as client:
        yield client


def get(client: Any, dataset_id: str = DATASET_ID, **params: Any) -> Any:
    params.setdefault("zoom", 5)
    return client.get(f"/coverage/{dataset_id}", params=params)


def _multipolygon_area(geojson: dict[str, Any]) -> float:
    from shapely.geometry import shape

    return shape(geojson).area


class TestAreaIsTheUnionOfFootprints:
    def test_the_unfiltered_area_covers_exactly_the_four_shapes(self, app_client: Any) -> None:
        response = get(app_client)

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["completeness"] == "complete"
        assert body["cells"] == []
        assert body["total_count"] is None
        # 4 (block) + 1 (island) + 8 (ring) + 2 (dateline tiles) unit squares, none
        # overlapping — the union's area is exactly their sum, holes included (a
        # hole is missing from the *ring* piece, not from the block or the island).
        assert _multipolygon_area(body["area"]) == pytest.approx(4 + 1 + 8 + 2)
        assert body["extent"] is not None

    def test_the_ring_keeps_its_hole(self, app_client: Any) -> None:
        response = get(app_client, bbox="19,19,24,24")

        assert response.status_code == 200
        area = response.json()["area"]
        from shapely.geometry import Point, shape

        polygon = shape(area)
        assert polygon.area == pytest.approx(8.0)
        assert not polygon.contains(Point(21.5, 21.5))  # the missing centre tile

    def test_the_island_stays_disconnected_from_the_block(self, app_client: Any) -> None:
        response = get(app_client)
        from shapely.geometry import shape

        polygon = shape(response.json()["area"])
        assert polygon.geom_type == "MultiPolygon"
        assert len(polygon.geoms) >= 3  # block, island, ring — at least three parts


class TestSpatialCrop:
    def test_a_bbox_over_half_the_block_returns_exactly_that_half(self, app_client: Any) -> None:
        response = get(app_client, bbox="0,0,1,2")  # the western half of the 2x2 block

        assert response.status_code == 200
        assert _multipolygon_area(response.json()["area"]) == pytest.approx(2.0)

    def test_a_bbox_over_open_ocean_is_an_empty_area_with_no_extent(self, app_client: Any) -> None:
        response = get(app_client, bbox="-50,-50,-40,-40")

        assert response.status_code == 200
        body = response.json()
        assert body["area"] == {"type": "MultiPolygon", "coordinates": []}
        assert body["extent"] is None

    def test_a_bbox_crossing_the_antimeridian_reaches_both_dateline_tiles(self, app_client: Any) -> None:
        response = get(app_client, bbox="179,-61,-179,-58")  # west > east: wraps

        assert response.status_code == 200
        assert _multipolygon_area(response.json()["area"]) == pytest.approx(2.0)

    def test_an_intersecting_triangle_crops_to_exactly_its_overlap(self, app_client: Any) -> None:
        # A right triangle over the SW quarter of the block: half of one unit tile.
        triangle = json.dumps({"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [0, 1], [0, 0]]]})
        response = get(app_client, intersects=triangle)

        assert response.status_code == 200
        assert _multipolygon_area(response.json()["area"]) == pytest.approx(0.5)

    def test_a_self_intersecting_polygon_is_400_and_leaks_no_coordinate(
        self, app_client: Any, caplog: pytest.LogCaptureFixture
    ) -> None:
        import logging

        caplog.set_level(logging.WARNING, logger="earthx.api.coverage")
        bowtie = json.dumps({"type": "Polygon", "coordinates": [[[0, 0], [2, 2], [2, 0], [0, 2], [0, 0]]]})
        response = get(app_client, intersects=bowtie)

        assert response.status_code == 400
        for needle in ("0, 0", "2, 2", "(0", "(2"):
            assert needle not in response.text
            assert needle not in caplog.text


class TestTimeFilter:
    def test_outside_the_items_time_the_area_is_empty(self, app_client: Any) -> None:
        response = get(app_client, datetime="2019-01-01T00:00:00Z/2019-06-30T00:00:00Z")

        assert response.status_code == 200
        assert response.json()["area"] == {"type": "MultiPolygon", "coordinates": []}

    def test_inside_one_windows_time_only_that_windows_shapes_appear(self, app_client: Any) -> None:
        response = get(app_client, datetime=f"{WINDOW_B[0]}/{WINDOW_B[1]}")

        assert response.status_code == 200
        # Window B is only the island.
        assert _multipolygon_area(response.json()["area"]) == pytest.approx(1.0)

    def test_a_dataset_without_a_time_axis_ignores_the_filter_entirely(self, app_client: Any) -> None:
        response = get(
            app_client, dataset_id=NO_TIME_DATASET_ID, datetime="2026-01-01T00:00:00Z/2026-12-31T00:00:00Z"
        )

        assert response.status_code == 200
        body = response.json()
        assert body["ignored_filters"] == ["datetime"]
        assert _multipolygon_area(body["area"]) == pytest.approx(1.0)


class TestCacheAndIgnoredCloudFilter:
    def test_a_second_identical_request_answers_from_the_cache(self, app_client: Any) -> None:
        first = get(app_client, bbox="0,0,2,2")
        second = get(app_client, bbox="0,0,2,2")

        assert first.json()["from_cache"] is False
        assert second.json()["from_cache"] is True
        assert second.json()["area"] == first.json()["area"]

    def test_max_cloud_cover_is_ignored_and_named(self, app_client: Any) -> None:
        response = get(app_client, bbox="0,0,2,2", max_cloud_cover=10)

        assert response.status_code == 200
        body = response.json()
        assert body["ignored_filters"] == ["max_cloud_cover"]
        assert _multipolygon_area(body["area"]) == pytest.approx(4.0)


class TestNoCoordinateInTheLog:
    def test_a_bbox_query_logs_no_coordinate(self, app_client: Any, caplog: pytest.LogCaptureFixture) -> None:
        import logging

        caplog.set_level(logging.INFO, logger="earthx.api.coverage")
        get(app_client, bbox="0,0,2,2")

        for needle in ("0,0,2,2", "\"west\"", "0.0, 0.0"):
            assert needle not in caplog.text
