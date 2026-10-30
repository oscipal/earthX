"""The orders the panel sends, taken by the statistics route of the tiler (NM4-19b, Otto's answer 1 to #230).

The preview of the panel measures its range with ``POST /collections/{dataset}/statistics`` and, for any refusal, falls
back to the first whole scene. A refusal of an order the panel built wrongly would then pass unnoticed, so the
very files ``frontend/src/fixtures/orders`` holds (what ``processingContract.test.ts`` records of the panel: an index
with and without a mask, a DEM, a mosaic of a pass) go through the route here, and none may be a ``422``.

The route runs on the real intake and the real operators; only the read of the rasters is a stand-in, for the
files are held against the schema and the items are synthetic (``test_frontend_orders.py``): what is asked here is
whether the route takes the order, and the numbers are the business of ``test_tiler_area_statistics.py``.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from earthx.api.tiler import area_statistics_cache, build_app
from earthx.processing import core
from tests.catalog.synthetic_zarr import registry_with_zarr
from tests.earthx.api.test_frontend_orders import FILES, items_of, recipe_of

#: The orders with an area whose steps keep the grid: the ones the panel posts (a step that changes the grid is
#: refused by the core, KE6, which this stand-in does not run).
MEASURED = [f for f in FILES if "aoi" in recipe_of(f) and all(s["op"] != "reproject" for s in recipe_of(f)["steps"])]
WITHOUT_AREA = [f for f in FILES if "aoi" not in recipe_of(f)]


class NoCache:
    async def get(self, key: str) -> None:
        return None

    async def set(self, key: str, value: dict[str, Any], *, dataset_id: str, ttl_s: float = 0) -> None:
        return None


@pytest.fixture
def asked(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    """The recipes the route would have read: the read itself is a stand-in with a plausible answer."""
    recipes: list[Any] = []

    def area_statistics(recipe: Any, *, max_pixels: int) -> core.AreaStatistics:
        recipes.append(recipe)
        statistics = {"minimum": 0.0, "maximum": 1.0, "mean": 0.5, "count": 4, "valid_percent": 100.0}
        return core.AreaStatistics(bands=[{"name": "b1", "statistics": statistics}], factor=1, pixels_read=4)

    monkeypatch.setattr(core, "area_statistics", area_statistics)
    return recipes


def client_for(items: dict[tuple[str, str], dict[str, Any]]) -> Iterator[TestClient]:
    async def source(dataset_id: str, item_id: str) -> dict[str, Any]:
        return items[(dataset_id, item_id)]

    @asynccontextmanager
    async def lifespan(app):
        app.state.earthx_item_source = source
        yield

    app = build_app(registry_with_zarr(), lifespan=lifespan)
    app.dependency_overrides[area_statistics_cache] = NoCache
    with TestClient(app) as client:
        yield client


def post(client: TestClient, path: Path):
    recipe = recipe_of(path)
    return client.post(
        f"/collections/{recipe['inputs'][0]['dataset']}/statistics",
        content=json.dumps(recipe).encode(),
        headers={"content-type": "application/json"},
    )


def test_there_are_orders_to_check() -> None:
    """A filter that finds nothing would pass for the wrong reason: the cases of Otto's answer are all there."""
    assert {f.stem for f in MEASURED} >= {
        "ndvi-with-place-search-aoi",
        "masked-ndvi-with-drawn-aoi",
        "normalize-dem-with-drawn-aoi",
        "ndvi-on-a-mosaic-of-three-scenes",
    }
    assert len(MEASURED) >= 4 and WITHOUT_AREA


@pytest.mark.parametrize("path", MEASURED, ids=lambda p: p.stem)
def test_the_route_takes_the_order_the_panel_builds(path: Path, asked: list[Any]) -> None:
    recipe = recipe_of(path)
    for client in client_for(items_of(recipe)):
        response = post(client, path)
    assert response.status_code == 200, response.text
    answer = response.json()
    assert set(answer) == {"bands", "exact", "factor"} and answer["exact"] is True
    assert len(asked) == 1


@pytest.mark.parametrize("path", WITHOUT_AREA, ids=lambda p: p.stem)
def test_an_order_without_an_area_is_refused_before_any_item_is_asked(path: Path, asked: list[Any]) -> None:
    """ "Whole scene" measures the first scene as it did: the panel does not post such an order."""
    for client in client_for({}):  # an item asked for would be a KeyError
        response = post(client, path)
    assert response.status_code == 422 and asked == []


def test_the_check_would_have_found_an_order_built_wrongly(asked: list[Any]) -> None:
    """The member the first panel sent in the AOI (``properties``): the route turns the order away, and says where."""
    path = next(f for f in MEASURED if f.stem == "ndvi-with-place-search-aoi")
    recipe = recipe_of(path)
    recipe["aoi"]["properties"] = {"source": "x"}
    for client in client_for(items_of(recipe)):
        response = client.post(
            "/collections/sentinel-2-c1-l2a/statistics",
            content=json.dumps(recipe).encode(),
            headers={"content-type": "application/json"},
        )
    assert response.status_code in (400, 422) and "extra_forbidden" in response.json()["detail"], response.text
    assert asked == []
