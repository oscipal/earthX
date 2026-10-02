"""An item the source delivers under another id, or with none, is refused (Otto's
review of M4-01a): a tile or a crop must not show another scene under the name it
asked for. Checked for each registry entry — a COG, a Zarr and a materialized
item — on the tile path and on the download.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from earthx.api.tiler import build_app
from earthx.catalog.datasets import REGISTRY
from tests.catalog import synthetic_chain
from tests.catalog.synthetic_chain import Chain

ENTRIES = list(REGISTRY)


@pytest.fixture(params=ENTRIES, ids=[config.dataset_id for config in ENTRIES])
def chain(request: pytest.FixtureRequest, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Chain:
    return synthetic_chain.build(request.param, tmp_path, monkeypatch)


@pytest.fixture
def opened(monkeypatch: pytest.MonkeyPatch) -> list[object]:
    calls: list[object] = []

    def recording(ref: object, *args: object, **kwargs: object) -> None:
        calls.append(ref)
        raise AssertionError("nothing may be opened for a refused item")

    monkeypatch.setattr("earthx.api.tiler.open_asset_ref", recording)
    return calls


def _client(chain: Chain, delivered: dict[str, Any]) -> TestClient:
    async def item_source(dataset_id: str, item_id: str) -> dict[str, Any]:
        return delivered

    app = build_app(chain.registry)
    app.state.earthx_item_source = item_source
    app.state.earthx_cache_pool = None
    app.state.earthx_resolver = synthetic_chain.mini_zarr.from_memory
    return TestClient(app)


def _delivered(chain: Chain, case: str) -> dict[str, Any]:
    if case == "other id":
        return {**chain.item, "id": f"{chain.item['id']}-OTHER"}
    return {key: value for key, value in chain.item.items() if key != "id"}


@pytest.mark.parametrize("case", ["other id", "no id"])
def test_a_tile_of_a_wrong_item_is_a_502(chain: Chain, opened: list[object], case: str) -> None:
    z, x, y = chain.tile
    response = _client(chain, _delivered(chain, case)).get(
        f"/collections/{chain.dataset_id}/items/{chain.item['id']}/tiles/WebMercatorQuad/{z}/{x}/{y}",
        params={"asset": chain.render_asset},
    )
    assert response.status_code == 502, response.text
    assert response.json()["detail"] == f"the source did not deliver item {chain.item['id']!r} intact"
    assert opened == []


@pytest.mark.parametrize("case", ["other id", "no id"])
def test_a_download_of_a_wrong_item_is_a_502(chain: Chain, opened: list[object], case: str) -> None:
    response = _client(chain, _delivered(chain, case)).post(
        f"/collections/{chain.dataset_id}/download",
        json={"groups": [[chain.item["id"]]], "assets": [chain.render_asset], "aoi": chain.aoi},
    )
    assert response.status_code == 502, response.text
    assert response.json()["detail"] == f"the source did not deliver item {chain.item['id']!r} intact"
    assert opened == []


def test_the_right_item_still_opens(chain: Chain) -> None:
    """The check refuses only the wrong item: the delivered one passes through."""
    z, x, y = chain.tile
    response = _client(chain, chain.item).get(
        f"/collections/{chain.dataset_id}/items/{chain.item['id']}/tiles/WebMercatorQuad/{z}/{x}/{y}",
        params={"asset": chain.render_asset},
    )
    assert response.status_code == 200, response.text
