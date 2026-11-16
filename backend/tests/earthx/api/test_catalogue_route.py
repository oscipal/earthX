"""``GET /catalogue/categories`` and ``GET /catalogue/regions`` (M5-40 H3, H4): what the filters of the Data catalogue
offer, from the files of the image, without the database and without the outlines."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from earthx.api.catalogue_route import router
from earthx.catalog.categories import load_categories
from earthx.catalog.listed import load_regions


@pytest.fixture(scope="module")
def client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_the_categories_come_in_the_order_of_the_file_with_their_titles(client: TestClient) -> None:
    response = client.get("/catalogue/categories")
    assert response.status_code == 200
    categories = load_categories()
    assert response.json() == {"categories": [{"id": c, "title": categories.titles[c]} for c in categories.ids]}
    assert response.json()["categories"][-1] == {"id": "other", "title": "Other"}


def test_every_region_comes_once_without_its_outline(client: TestClient) -> None:
    regions = client.get("/catalogue/regions").json()["regions"]
    assert sorted(r["code"] for r in regions) == sorted(r.code for r in load_regions())
    assert all(set(r) <= {"code", "name", "level", "state"} for r in regions)
    assert len(client.get("/catalogue/regions").content) < 20_000


def test_the_subdivisions_follow_their_state(client: TestClient) -> None:
    regions = client.get("/catalogue/regions").json()["regions"]
    codes = [r["code"] for r in regions]
    germany = codes.index("DE")
    following = codes[germany + 1 : germany + 17]
    assert sorted(following) == sorted(r.code for r in load_regions() if r.code.startswith("DE-"))
    assert all(r["state"] == "DE" for r in regions if r["code"].startswith("DE-"))
    states = [r["name"] for r in regions if r["level"] == "state"]
    assert states == sorted(states, key=str.casefold)


def test_the_answers_may_be_kept_for_an_hour(client: TestClient) -> None:
    for path in ("/catalogue/categories", "/catalogue/regions"):
        assert client.get(path).headers["cache-control"] == "public, max-age=3600"


@pytest.mark.parametrize("method", ["post", "put", "delete"])
def test_nothing_but_get(client: TestClient, method: str) -> None:
    assert getattr(client, method)("/catalogue/categories").status_code == 405
