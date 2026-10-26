"""Which GDAL profile each route of the tiler reads under (NM4-26 §10, §13, §18 point 1).

The tiles, their TileJSON, the statistics, the mosaic tile and the tiles of a result read serially into a
cache of 256 MiB (`gateway.gdal.tile_gdal_options`); the AOI crop of the download route keeps the parallel
range reads (`crop_gdal_options`). Each test looks at what GDAL is configured with *where the reader is
opened* — inside the ``rasterio.Env`` the route entered — rather than at a variable of the app, so a route
that took its options from another place would fail here.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from rasterio._env import get_gdal_config

from earthx.access import mosaic_tiles as mosaic_reading
from earthx.api import tiler
from earthx.api.dependencies import policy_from_registry
from earthx.api.result_tiles import result_environment
from earthx.api.tiler import build_app, gdal_environment
from earthx.catalog.datasets import REGISTRY, SENTINEL_2_L2A
from earthx.gateway.gdal import crop_gdal_options, gdal_options, tile_gdal_options
from tests.catalog import synthetic_chain
from tests.earthx.access.test_mosaic_tiles import SEAM_X
from tests.earthx.api.test_download_route import DATASET, FIXTURE, GOOD_AOI, ITEM_ID, _client_for
from tests.earthx.api.test_tiler_mosaic import ZONE_32, Scenes, _app, _query, _serve, _tile_path

POLICY = policy_from_registry(REGISTRY)
TILE_PROFILE = tile_gdal_options(POLICY)
SETTINGS = ("GDAL_HTTP_MULTIRANGE", "CPL_VSIL_CURL_CACHE_SIZE")


def seen_by_gdal() -> tuple[str, str]:
    """The two settings that differ between the profiles, as the calling thread's GDAL has them now."""
    return tuple(str(get_gdal_config(name)) for name in SETTINGS)  # type: ignore[return-value]


TILE_SEEN = ("SERIAL", str(256 * 1024 * 1024))
CROP_SEEN = ("YES", str(256 * 1024 * 1024))


def test_the_app_keeps_both_profiles_built_from_its_policy() -> None:
    app = build_app()
    assert app.state.earthx_gdal_options == tile_gdal_options(app.state.earthx_policy)
    assert app.state.earthx_crop_gdal_options == crop_gdal_options(app.state.earthx_policy)
    assert app.state.earthx_gdal_options != app.state.earthx_crop_gdal_options


def test_the_two_dependencies_of_the_tile_routes_hand_out_the_tile_profile() -> None:
    app = build_app()
    request = SimpleNamespace(app=app)
    assert gdal_environment(request) == app.state.earthx_gdal_options  # type: ignore[arg-type]
    environment = result_environment(request)  # type: ignore[arg-type]
    assert {name: environment[name] for name in app.state.earthx_gdal_options} == app.state.earthx_gdal_options
    assert environment["CPL_VSIL_CURL_USE_HEAD"] == "NO"


@pytest.fixture
def seen(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    """What GDAL was configured with each time a single item's reader was opened."""
    recorded: list[tuple[str, str]] = []
    original = tiler.open_asset

    def recording(src_path: Any, **options: Any) -> Any:
        recorded.append(seen_by_gdal())
        return original(src_path, **options)

    monkeypatch.setattr(tiler, "open_asset", recording)
    return recorded


@pytest.fixture
def chain(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> synthetic_chain.Chain:
    return synthetic_chain.build(SENTINEL_2_L2A, tmp_path, monkeypatch)


@pytest.fixture
def client(chain: synthetic_chain.Chain) -> TestClient:
    async def item_source(dataset_id: str, item_id: str) -> dict[str, Any]:
        return chain.item

    app = build_app(chain.registry)
    app.state.earthx_item_source = item_source
    app.state.earthx_cache_pool = None
    app.state.earthx_resolver = synthetic_chain.mini_zarr.from_memory
    return TestClient(app)


class TestSingleItemRoutes:
    def _base(self, chain: synthetic_chain.Chain) -> str:
        return f"/collections/{chain.dataset_id}/items/{chain.item['id']}"

    def test_a_tile_reads_under_the_tile_profile(
        self, client: TestClient, chain: synthetic_chain.Chain, seen: list[tuple[str, str]]
    ) -> None:
        zoom, x, y = chain.tile
        response = client.get(
            f"{self._base(chain)}/tiles/WebMercatorQuad/{zoom}/{x}/{y}.png", params={"asset": chain.render_asset}
        )
        assert response.status_code == 200, response.text
        assert seen and set(seen) == {TILE_SEEN}

    def test_the_tilejson_reads_under_the_tile_profile(
        self, client: TestClient, chain: synthetic_chain.Chain, seen: list[tuple[str, str]]
    ) -> None:
        response = client.get(
            f"{self._base(chain)}/WebMercatorQuad/tilejson.json", params={"asset": chain.render_asset}
        )
        assert response.status_code == 200, response.text
        assert seen and set(seen) == {TILE_SEEN}

    def test_the_statistics_read_under_the_tile_profile(
        self, client: TestClient, chain: synthetic_chain.Chain, seen: list[tuple[str, str]]
    ) -> None:
        response = client.get(f"{self._base(chain)}/statistics", params={"asset": chain.render_asset})
        assert response.status_code == 200, response.text
        assert seen and set(seen) == {TILE_SEEN}


class TestTheMosaicTile:
    def test_every_scene_of_a_portion_is_read_under_the_tile_profile(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The scenes are read in threads of their own, which enter the options of the route again."""
        scenes = Scenes(tmp_path)
        scenes.add("WEST", ZONE_32, SEAM_X - 4000.0, 4000.0, 100)
        scenes.add("EAST", ZONE_32, SEAM_X, 4000.0, 200)
        _serve(scenes, monkeypatch)
        recorded: list[tuple[str, str]] = []
        original = mosaic_reading.open_asset

        def recording(scene: Any, **options: Any) -> Any:
            recorded.append(seen_by_gdal())
            return original(scene, **options)

        monkeypatch.setattr(mosaic_reading, "open_asset", recording)
        with TestClient(_app(scenes)) as client:
            response = client.get(_tile_path(), params=_query(["WEST", "EAST"]))
        assert response.status_code == 200, response.text
        assert len(recorded) >= 2 and set(recorded) == {TILE_SEEN}


@pytest.fixture(scope="module")
def item() -> dict[str, Any]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture
def download_client(item: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    yield from _client_for(REGISTRY, item, monkeypatch)


class TestTheCrop:
    def test_the_download_route_hands_the_crop_profile_to_the_zip_builder(
        self, download_client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: list[dict[str, str]] = []

        def stop(**kwargs: Any) -> bytes:
            captured.append(kwargs["gdal_env"])
            return b"PK"

        monkeypatch.setattr(tiler, "build_download_zip", stop)
        response = download_client.post(
            f"/collections/{DATASET}/download", json={"groups": [[ITEM_ID]], "assets": ["visual"], "aoi": GOOD_AOI}
        )
        assert response.status_code == 200, response.text
        assert captured == [crop_gdal_options(POLICY)]
        assert captured[0]["GDAL_HTTP_MULTIRANGE"] == gdal_options(POLICY)["GDAL_HTTP_MULTIRANGE"] == "YES"
        assert captured[0]["CPL_VSIL_CURL_CACHE_SIZE"] == TILE_PROFILE["CPL_VSIL_CURL_CACHE_SIZE"]
        assert captured[0] != TILE_PROFILE
