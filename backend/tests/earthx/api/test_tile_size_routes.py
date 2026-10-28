"""Every route of the three tile routers of the tiler refuses a ``tilesize`` other than 256 or 512 (NM4-29 §15).

The check itself is tested on a bare factory (`tests/earthx/access/test_tile_size.py`); this is the app as it is
built, so that a router added later or built another way cannot leave it out. The routes come from the app's own
schema, and each is asked with placeholder path values: the check runs before the path is looked at, so even a
dataset or a result that does not exist answers ``400``, without a database and without a source.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from earthx.api.tiler import MOSAIC_ROUTER_PREFIX, RESULT_ROUTER_PREFIX, ROUTER_PREFIX, build_app

PLACEHOLDERS = {
    "{dataset}": "no-such-dataset",
    "{item}": "NO_SUCH_ITEM",
    "{result_id}": "no-such-result",
    "{tileMatrixSetId}": "WebMercatorQuad",
    "{z}": "10",
    "{x}": "545",
    "{y}": "358",
    "{format}": "png",
    "{lon}": "11.05",
    "{lat}": "47.35",
}


def _routes() -> list[str]:
    paths = build_app().openapi()["paths"]
    return [path for path in paths if path.startswith((ROUTER_PREFIX, MOSAIC_ROUTER_PREFIX, RESULT_ROUTER_PREFIX))]


def test_the_three_routers_have_tile_and_tilejson_routes() -> None:
    routes = _routes()
    for prefix in (ROUTER_PREFIX, MOSAIC_ROUTER_PREFIX, RESULT_ROUTER_PREFIX):
        assert any(path.startswith(prefix + "/tiles/") for path in routes), prefix
        assert f"{prefix}/{{tileMatrixSetId}}/tilejson.json" in routes, prefix


@pytest.mark.parametrize("path", _routes())
def test_each_route_answers_a_size_of_4096_with_a_400_before_anything_else(path: str) -> None:
    url = path
    for placeholder, value in PLACEHOLDERS.items():
        url = url.replace(placeholder, value)
    assert "{" not in url, url
    response = TestClient(build_app()).get(url, params={"tilesize": "4096"})
    assert response.status_code == 400, (url, response.text)
    assert response.json() == {"detail": "tilesize is 256 or 512"}
