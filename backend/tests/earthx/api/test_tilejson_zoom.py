"""M3-04: the TileJSON's zoom range is the registry's, not the reader's.

Before this task ``/tilejson.json`` advertised whatever rio-tiler computed from the
asset (`_check_zoom_released`'s documented gap): a client that follows the document
rather than building tile URLs itself could be sent to a level the tile route then
refuses with a 400. The chain fixture from ``test_onboarding_endtoend.py`` gives a
real registry entry with a real, if synthetic, asset behind it, so both the
document and the boundary it now matches can be checked against the real route —
for both of the platform's datasets.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from earthx.api.tiler import build_app
from earthx.catalog.datasets import REGISTRY, SENTINEL_2_L2A_ZARR3
from tests.catalog import synthetic_chain
from tests.catalog.synthetic_chain import Chain

ENTRIES = list(REGISTRY)
ENTRY_IDS = [config.dataset_id for config in ENTRIES]


@pytest.fixture(params=ENTRIES, ids=ENTRY_IDS)
def chain(request: pytest.FixtureRequest, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Chain:
    return synthetic_chain.build(request.param, tmp_path, monkeypatch)


@pytest.fixture
def client(chain: Chain) -> TestClient:
    return _client_for(chain)


def _client_for(chain: Chain) -> TestClient:
    async def item_source(dataset_id: str, item_id: str) -> dict[str, Any]:
        return chain.item

    app = build_app(chain.registry)
    app.state.earthx_item_source = item_source
    app.state.earthx_cache_pool = None
    app.state.earthx_resolver = synthetic_chain.mini_zarr.from_memory
    return TestClient(app)


def _tilejson(client: TestClient, chain: Chain, **params: Any) -> dict[str, Any]:
    response = client.get(
        f"/collections/{chain.dataset_id}/items/{synthetic_chain.ITEM_ID}/WebMercatorQuad/tilejson.json",
        params={"asset": chain.render_asset, **params},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _tilejson_rejected(client: TestClient, chain: Chain, **params: Any) -> None:
    response = client.get(
        f"/collections/{chain.dataset_id}/items/{synthetic_chain.ITEM_ID}/WebMercatorQuad/tilejson.json",
        params={"asset": chain.render_asset, **params},
    )
    assert response.status_code == 400, response.text


def _ancestor_tile(tile: tuple[int, int, int], target_zoom: int) -> tuple[int, int, int]:
    """The tile at ``target_zoom`` that contains ``tile`` (or its finer descendant).

    WebMercatorQuad is a quadtree with the same origin at every level, so the tile
    that contains a given one at a coarser zoom is found by dividing its ``x``/``y``
    by ``2 ** (zoom difference)`` — no new geometry has to be picked to test a level
    other than the one :func:`synthetic_chain._covering_tile` chose.
    """
    zoom, x, y = tile
    factor = 2 ** (zoom - target_zoom)
    return target_zoom, x // factor, y // factor


def test_the_tilejson_zoom_range_is_the_registrys(client: TestClient, chain: Chain) -> None:
    viewer = chain.config.viewer
    assert viewer is not None, "an entry without earthx:viewer has no display step at all"

    body = _tilejson(client, chain)

    assert body["minzoom"] == viewer.min_zoom
    assert body["maxzoom"] == viewer.max_zoom


def test_a_tile_at_the_advertised_boundary_is_served(client: TestClient, chain: Chain) -> None:
    """The boundary the document names is one the tile route actually serves."""
    viewer = chain.config.viewer
    assert viewer is not None
    body = _tilejson(client, chain)
    assert body["maxzoom"] == viewer.max_zoom

    zoom, x, y = chain.tile
    assert zoom == viewer.max_zoom, "the chain's covering tile is at the finest released level"
    response = client.get(
        f"/collections/{chain.dataset_id}/items/{synthetic_chain.ITEM_ID}"
        f"/tiles/WebMercatorQuad/{zoom}/{x}/{y}.png",
        params={"asset": chain.render_asset},
    )

    assert response.status_code == 200, response.text


def test_one_level_above_the_advertised_boundary_is_refused(client: TestClient, chain: Chain) -> None:
    """The document's own boundary is where the tile route actually stops."""
    viewer = chain.config.viewer
    assert viewer is not None
    zoom, x, y = chain.tile

    response = client.get(
        f"/collections/{chain.dataset_id}/items/{synthetic_chain.ITEM_ID}"
        f"/tiles/WebMercatorQuad/{zoom + 1}/{x * 2}/{y * 2}.png",
        params={"asset": chain.render_asset},
    )

    assert response.status_code == 400, response.text


def test_the_tilejson_route_still_declares_no_free_url_parameter(client: TestClient) -> None:
    """M2-04's guarantee is not weakened by the new dependency (adr/0006 §10.1)."""
    schema = client.app.openapi()
    parameters = {
        (parameter["in"], parameter["name"])
        for operations in schema["paths"].values()
        for operation in operations.values()
        if isinstance(operation, dict)
        for parameter in operation.get("parameters", [])
    }
    assert ("query", "url") not in parameters


class TestTheLowerBoundary:
    """Review of #78: the range has two ends, and only ``sentinel-2-l2a-zarr3``'s
    (``min_zoom`` 8) has room below it to test — the other entry's ``min_zoom`` is 0,
    where "one level below" is not a tile address at all.
    """

    @pytest.fixture
    def chain(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Chain:
        return synthetic_chain.build(SENTINEL_2_L2A_ZARR3, tmp_path, monkeypatch)

    @pytest.fixture
    def client(self, chain: Chain) -> TestClient:
        return _client_for(chain)

    def test_one_level_below_min_zoom_is_refused(self, client: TestClient, chain: Chain) -> None:
        viewer = chain.config.viewer
        assert viewer is not None and viewer.min_zoom == 8
        zoom, x, y = _ancestor_tile(chain.tile, viewer.min_zoom - 1)
        assert zoom == 7

        response = client.get(
            f"/collections/{chain.dataset_id}/items/{synthetic_chain.ITEM_ID}"
            f"/tiles/WebMercatorQuad/{zoom}/{x}/{y}.png",
            params={"asset": chain.render_asset},
        )

        assert response.status_code == 400, response.text

    def test_min_zoom_itself_is_served(self, client: TestClient, chain: Chain) -> None:
        viewer = chain.config.viewer
        assert viewer is not None and viewer.min_zoom == 8
        zoom, x, y = _ancestor_tile(chain.tile, viewer.min_zoom)
        assert zoom == 8

        response = client.get(
            f"/collections/{chain.dataset_id}/items/{synthetic_chain.ITEM_ID}"
            f"/tiles/WebMercatorQuad/{zoom}/{x}/{y}.png",
            params={"asset": chain.render_asset},
        )

        assert response.status_code == 200, response.text


class TestAnExplicitZoomOverride:
    """Review of #78: an explicit ``minzoom``/``maxzoom`` may narrow the registry's
    range, never leave it — the deliberate departure from TiTiler's own precedence
    documented on ``EarthxTilerFactory.tilejson``.
    """

    def test_a_minzoom_within_the_range_is_taken_over(self, client: TestClient, chain: Chain) -> None:
        viewer = chain.config.viewer
        assert viewer is not None
        narrowed = viewer.min_zoom + 1

        body = _tilejson(client, chain, minzoom=narrowed)

        assert body["minzoom"] == narrowed
        assert body["maxzoom"] == viewer.max_zoom

    def test_a_maxzoom_within_the_range_is_taken_over(self, client: TestClient, chain: Chain) -> None:
        viewer = chain.config.viewer
        assert viewer is not None
        narrowed = viewer.max_zoom - 1

        body = _tilejson(client, chain, maxzoom=narrowed)

        assert body["minzoom"] == viewer.min_zoom
        assert body["maxzoom"] == narrowed

    def test_a_minzoom_below_the_range_is_refused(self, client: TestClient, chain: Chain) -> None:
        viewer = chain.config.viewer
        assert viewer is not None

        _tilejson_rejected(client, chain, minzoom=viewer.min_zoom - 1)

    def test_a_maxzoom_above_the_range_is_refused(self, client: TestClient, chain: Chain) -> None:
        viewer = chain.config.viewer
        assert viewer is not None

        _tilejson_rejected(client, chain, maxzoom=viewer.max_zoom + 1)

    def test_a_minzoom_above_the_given_maxzoom_is_refused(self, client: TestClient, chain: Chain) -> None:
        """Both values can each sit inside the range and still cross each other."""
        viewer = chain.config.viewer
        assert viewer is not None and viewer.min_zoom < viewer.max_zoom

        _tilejson_rejected(client, chain, minzoom=viewer.max_zoom, maxzoom=viewer.min_zoom)
