"""A tile is 256 or 512 px, and the route says so before it reads anything (NM4-29 §9.6, §15 answer 2).

TiTiler takes any ``tilesize`` above 0; a tile of 4096 px held a thread for 12.6 s. The check is a dependency of the
factory's router, so it is tested here on a bare factory, without a reader: a refused size never gets that far.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from earthx.access.tiles import TILE_SIZES, EarthxTilerFactory
from earthx.readers.cog import AssetPath

PATH = AssetPath("/vsicurl/https://assets.example.invalid/x.tif", dataset_id="d", item_id="i", asset="visual")
TILE = "/tiles/WebMercatorQuad/10/545/358.png"


@pytest.fixture
def opened() -> list[object]:
    return []


@pytest.fixture
def client(opened: list[object]) -> TestClient:
    def path() -> AssetPath:
        opened.append(PATH)
        return PATH

    app = FastAPI()
    app.include_router(EarthxTilerFactory(path_dependency=path, environment_dependency=lambda: {}, name="t").router)
    return TestClient(app, raise_server_exceptions=False)


def test_the_two_sizes_are_256_and_512() -> None:
    assert TILE_SIZES == (256, 512)


@pytest.mark.parametrize("size", ["0", "-256", "128", "1024", "4096", "512.0", "0512", " 512", "big", ""])
@pytest.mark.parametrize("route", [TILE, "/WebMercatorQuad/tilejson.json", "/statistics", "/info"])
def test_another_size_is_a_400_and_nothing_is_opened(
    client: TestClient, opened: list[object], route: str, size: str
) -> None:
    response = client.get(route, params={"tilesize": size})
    assert response.status_code == 400, response.text
    assert response.json() == {"detail": "tilesize is 256 or 512"}
    assert opened == []


def test_two_sizes_in_one_request_are_a_400(client: TestClient, opened: list[object]) -> None:
    response = client.get(TILE, params=[("tilesize", "256"), ("tilesize", "512")])
    assert response.status_code == 400
    assert opened == []


@pytest.mark.parametrize("query", [{}, {"tilesize": "256"}, {"tilesize": "512"}])
def test_no_size_256_and_512_pass_the_check(client: TestClient, opened: list[object], query: dict[str, str]) -> None:
    """The path dependency runs: the request got past the check. The read fails, there is no file behind the path."""
    client.get(TILE, params=query)
    assert opened == [PATH]


def test_every_route_of_the_factory_checks_the_size_first() -> None:
    factory = EarthxTilerFactory(path_dependency=lambda: PATH, name="t")
    routes = [route for route in factory.router.routes if hasattr(route, "dependant")]
    assert routes
    for route in routes:
        assert route.dependant.dependencies[0].call.__name__ == "tile_size_allowed", route.path
