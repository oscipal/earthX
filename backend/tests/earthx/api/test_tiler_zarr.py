"""The tile route serves a Zarr dataset through the same URLs as a COG one (M2-09a).

"Kachelroute aus M2-04 für das Format erweitert, ohne Sonderfall im Frontend": the
client asks for ``…/tiles/{tileMatrixSetId}/{z}/{x}/{y}?asset=…`` and does not learn
what the data is stored as. What decides is the registry's ``format``, in the one
place that reads the registry — and this file goes the whole way, from the route
down to the bytes of the synthetic store, to show that it does.

The store is the synthetic one of `mini_zarr.py`, reached through the reader's own
gateway; no source, no database, no GDAL.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from rasterio.warp import transform_bounds
from rio_tiler.constants import WEB_MERCATOR_TMS, WGS84_CRS

from earthx.api.tiler import build_app, dataset_asset_path
from earthx.catalog.datasets import SENTINEL_2_L2A
from earthx.catalog.registry import DataFormat, DatasetRegistry
from earthx.gateway import check_url
from earthx.readers.cog import AssetPath
from earthx.readers.zarr_reader import ZarrAsset
from tests.earthx.readers import mini_zarr
from tests.earthx.readers.mini_zarr import BASE_URL, HOST, build_mini_zarr, serve_store

DATASET = "synthetic-zarr"
ITEM = "SYNTH_20260102T100000"
ASSET = "b04"
GROUP = "r20m"
BASE = f"/collections/{DATASET}/items/{ITEM}"

ZARR_DATASET = replace(
    SENTINEL_2_L2A,
    dataset_id=DATASET,
    format=DataFormat.ZARR,
    source=replace(SENTINEL_2_L2A.source, asset_hosts=(HOST,)),
)
COG_DATASET = replace(ZARR_DATASET, dataset_id="synthetic-cog", format=DataFormat.COG)
LEGACY_DATASET = replace(ZARR_DATASET, dataset_id="synthetic-legacy", format=DataFormat.LEGACY)
REGISTRY = DatasetRegistry((ZARR_DATASET, COG_DATASET, LEGACY_DATASET))

ITEM_JSON: dict[str, Any] = {
    "id": ITEM,
    "type": "Feature",
    # The store carries no CRS of its own (adr/0007 §3.4), so this field is the only
    # thing that says where the data is.
    "properties": {"proj:code": mini_zarr.ITEM_CRS, "datetime": f"{mini_zarr.TIMES[0]}Z"},
    "assets": {
        ASSET: {"href": f"{BASE_URL}/{GROUP}/{ASSET}"},
        "missing": {"href": f"{BASE_URL}/{mini_zarr.MISSING_GROUP}/{ASSET}"},
        "unknown-variable": {"href": f"{BASE_URL}/{GROUP}/b99"},
    },
}


@pytest.fixture(scope="module")
def store_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return build_mini_zarr(tmp_path_factory.mktemp("zarr") / "mini.zarr")


@pytest.fixture
def requests(store_root: Path, monkeypatch: pytest.MonkeyPatch) -> list[httpx.Request]:
    return serve_store(store_root, monkeypatch)


@pytest.fixture
def without_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    """Resolve from memory in both readers. ``tests/conftest.py`` refuses a real lookup."""
    for module in ("earthx.readers.zarr_reader", "earthx.readers.cog"):
        monkeypatch.setattr(
            f"{module}.check_url",
            lambda url, policy, **_: check_url(url, policy, resolve=mini_zarr.from_memory),
        )


@pytest.fixture
def client(
    requests: list[httpx.Request], without_dns: None, monkeypatch: pytest.MonkeyPatch
) -> TestClient:
    """The real app over the synthetic store, with a lifespan that opens no pool."""

    async def item_source(dataset_id: str, item_id: str) -> dict[str, Any]:
        return ITEM_JSON

    @asynccontextmanager
    async def lifespan(app):
        app.state.earthx_item_source = item_source
        yield

    app = build_app(REGISTRY, lifespan=lifespan)
    app.state.earthx_resolver = mini_zarr.from_memory
    with TestClient(app) as test_client:
        yield test_client


def covering_tile() -> tuple[int, int, int]:
    """A tile over the middle of the store, at a zoom its resolution supports."""
    west, south, east, north = transform_bounds(
        mini_zarr.ITEM_CRS, WGS84_CRS, *mini_zarr.store_bounds()
    )
    tile = WEB_MERCATOR_TMS.tile((west + east) / 2, (south + north) / 2, 13)
    return tile.z, tile.x, tile.y


def tile_url(asset: str = ASSET, dataset: str = DATASET) -> str:
    z, x, y = covering_tile()
    return f"/collections/{dataset}/items/{ITEM}/tiles/WebMercatorQuad/{z}/{x}/{y}.png?asset={asset}"


class TestTheRegistryPicksTheReader:
    @pytest.mark.anyio
    @pytest.mark.parametrize(
        ("dataset", "expected"),
        [(DATASET, ZarrAsset), (COG_DATASET.dataset_id, AssetPath)],
    )
    async def test_the_format_of_the_entry_decides_what_the_path_dependency_builds(
        self, client: TestClient, dataset: str, expected: type
    ) -> None:
        built = await dataset_asset_path(
            _RequestWithApp(client.app), dataset=dataset, item=ITEM, asset=ASSET
        )
        assert isinstance(built, expected)

    def test_a_format_no_reader_opens_is_a_501_rather_than_a_wrong_picture(
        self, client: TestClient
    ) -> None:
        response = client.get(tile_url(dataset=LEGACY_DATASET.dataset_id))
        assert response.status_code == 501
        assert "legacy" in response.json()["detail"]


class TestTheRouteServesTheStore:
    def test_a_tile_is_a_png_built_from_the_synthetic_store(
        self, client: TestClient, requests: list[httpx.Request]
    ) -> None:
        response = client.get(tile_url())
        assert response.status_code == 200, response.text
        assert response.headers["content-type"] == "image/png"
        assert response.content.startswith(b"\x89PNG")
        assert requests, "the tile came from somewhere other than the gateway"

    def test_the_statistics_endpoint_answers_for_a_zarr_asset_too(
        self, client: TestClient
    ) -> None:
        response = client.get(f"{BASE}/statistics?asset={ASSET}")
        assert response.status_code == 200, response.text
        assert response.json(), "a statistic of no bands is not a statistic"

    def test_the_url_a_client_builds_is_the_same_for_both_formats(self, client: TestClient) -> None:
        """The client sends the same URL either way — that is what "no special case" means."""
        zarr_url = tile_url(dataset=DATASET).replace(DATASET, "{dataset}")
        cog_url = tile_url(dataset=COG_DATASET.dataset_id).replace(COG_DATASET.dataset_id, "{dataset}")
        assert zarr_url == cog_url


class TestWhatTheSourceGetsWrong:
    """A store that does not match its item is the source's problem, and says which."""

    @pytest.mark.parametrize(
        ("asset", "expected"),
        [("missing", "does not have"), ("unknown-variable", "b99")],
    )
    def test_a_group_or_variable_the_store_lacks_is_a_502_that_names_it(
        self, client: TestClient, asset: str, expected: str
    ) -> None:
        response = client.get(tile_url(asset))
        assert response.status_code == 502
        assert expected in response.json()["detail"]

    def test_no_answer_repeats_the_address(self, client: TestClient) -> None:
        response = client.get(tile_url("missing"))
        assert HOST not in response.text


class _RequestWithApp:
    """Just enough of a request for the path dependency: the app state hangs off it,
    plus what ``_target_gsd`` reads off a real one (no tile route here, so neither
    ever names a level to pick — the fallback of ``target_gsd=None`` applies)."""

    def __init__(self, app: Any) -> None:
        self.app = app
        self.url = SimpleNamespace(path="")
        self.path_params: dict[str, Any] = {}
