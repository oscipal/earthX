"""The tile route over a file placed by ground control points: a picture where the registry names ``gcp_tps``, a 502
where it names a geotransform (DS-04a, adr/0018 F1, Auslegung A3)."""

from __future__ import annotations

import warnings
from collections.abc import Iterator
from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from rasterio.errors import NotGeoreferencedWarning
from rio_tiler.constants import WEB_MERCATOR_TMS

from earthx.api.tiler import build_app
from earthx.catalog.registry import DatasetRegistry, Georeferencing
from earthx.gateway import check_url
from tests.catalog.entries import SENTINEL_2_L2A
from tests.catalog.synthetic_zarr import without_cloud_share
from tests.earthx.readers import mini_gcp
from tests.earthx.readers.mini_cog import serve_cog
from tests.earthx.readers.mini_zarr import HOST, from_memory

ITEM = "S1_SYNTHETIC"
ASSET = "vv"
HREF = f"https://{HOST}/products/{ITEM}/{ASSET}.tif"

PLAIN = replace(
    without_cloud_share(SENTINEL_2_L2A),
    dataset_id="synthetic-plain",
    source=replace(SENTINEL_2_L2A.source, asset_hosts=(HOST,)),
)
GCP = replace(PLAIN, dataset_id="synthetic-gcp", georeferencing=Georeferencing.GCP_TPS)
REGISTRY = DatasetRegistry((PLAIN, GCP))

ITEM_JSON: dict[str, Any] = {
    "id": ITEM,
    "type": "Feature",
    "properties": {"datetime": "2026-11-07T05:00:00Z"},
    "assets": {ASSET: {"href": HREF}},
}


@pytest.fixture(scope="module")
def gcp_file(tmp_path_factory: pytest.TempPathFactory) -> Path:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", NotGeoreferencedWarning)
        return mini_gcp.build_mini_gcp(tmp_path_factory.mktemp("gcp") / "gcp.tif")


@pytest.fixture
def client(gcp_file: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    serve_cog(gcp_file, monkeypatch)
    monkeypatch.setattr(
        "earthx.readers.cog.check_url", lambda url, policy, **_: check_url(url, policy, resolve=from_memory)
    )

    async def item_source(dataset_id: str, item_id: str) -> dict[str, Any]:
        return ITEM_JSON

    @asynccontextmanager
    async def lifespan(app):
        app.state.earthx_item_source = item_source
        yield

    app = build_app(REGISTRY, lifespan=lifespan)
    app.state.earthx_resolver = from_memory
    with TestClient(app) as test_client, warnings.catch_warnings():
        warnings.simplefilter("ignore", NotGeoreferencedWarning)
        yield test_client


def tile_url(dataset: str) -> str:
    lon, lat = mini_gcp.position(mini_gcp.SIZE / 2, mini_gcp.SIZE / 2)
    tile = WEB_MERCATOR_TMS.tile(lon, lat, 16)
    return (
        f"/collections/{dataset}/items/{ITEM}/tiles/WebMercatorQuad/{tile.z}/{tile.x}/{tile.y}.png"
        f"?asset={ASSET}&rescale=0,{mini_gcp.SIZE * mini_gcp.SIZE}"
    )


def test_the_registrys_spline_gives_a_picture(client: TestClient) -> None:
    response = client.get(tile_url(GCP.dataset_id))
    assert response.status_code == 200, response.text
    assert response.content.startswith(b"\x89PNG")


def test_a_geotransform_in_the_registry_is_a_502_that_names_no_address(client: TestClient) -> None:
    response = client.get(tile_url(PLAIN.dataset_id))
    assert response.status_code == 502
    detail = response.json()["detail"]
    assert detail == "the asset is not placed the way the platform expects"
    assert HOST not in detail and ITEM not in detail
