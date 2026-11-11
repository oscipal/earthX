"""An auxiliary file that is no raster is refused by the tile and the download route before anything is read (M5-08c, question 4)."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from earthx.access.resolve import NotARaster, check_is_raster, resolve_asset
from earthx.api.tiler import build_app
from earthx.gateway import check_url
from tests.catalog.entries import REGISTRY, SENTINEL_2_L2A, SWISSALTI3D

COG = "image/tiff; application=geotiff; profile=cloud-optimized"
ZIP = "application/x.ascii-xyz+zip"
HREF = "https://data.geo.admin.ch/ch.swisstopo.swissalti3d/swissalti3d_2026_2600-1200/{}"
AOI = {"type": "Polygon", "coordinates": [[[7.4, 46.9], [7.41, 46.9], [7.41, 46.91], [7.4, 46.91], [7.4, 46.9]]]}


def _item(**types: str | None) -> dict[str, Any]:
    kinds = {"dtm": COG, "xyz": ZIP, **types}
    assets = {key: {"href": HREF.format(key), **({"type": kind} if kind else {})} for key, kind in kinds.items()}
    return {
        "id": "2026-2600-1200",
        "bbox": [7.39, 46.89, 7.42, 46.92],
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[7.39, 46.89], [7.42, 46.89], [7.42, 46.92], [7.39, 46.92], [7.39, 46.89]]],
        },
        "properties": {"datetime": "2026-01-01T00:00:00Z"},
        "assets": assets,
    }


class TestTheRule:
    def test_a_zip_the_registry_calls_auxiliary_is_refused(self) -> None:
        with pytest.raises(NotARaster, match="xyz.*no raster.*application/x.ascii-xyz\\+zip"):
            check_is_raster(_item(), SWISSALTI3D, "xyz")

    def test_resolve_asset_refuses_it_too(self) -> None:
        with pytest.raises(NotARaster):
            resolve_asset(_item(), SWISSALTI3D, "xyz")

    def test_the_cog_is_a_raster(self) -> None:
        check_is_raster(_item(), SWISSALTI3D, "dtm")
        assert resolve_asset(_item(), SWISSALTI3D, "dtm").asset == "dtm"

    def test_an_auxiliary_picture_stays_readable(self) -> None:
        # `visual` of Sentinel-2 is auxiliary and a raster: a tile may show it.
        assert "visual" in SENTINEL_2_L2A.auxiliary_assets
        item = {
            "id": "x",
            "assets": {"visual": {"href": "https://e.example/v.tif", "type": "image/tiff; application=geotiff"}},
        }
        check_is_raster(item, SENTINEL_2_L2A, "visual")

    def test_a_file_the_registry_does_not_call_auxiliary_is_left_to_the_reader(self) -> None:
        check_is_raster(_item(dtm=ZIP), SWISSALTI3D, "dtm")

    @pytest.mark.parametrize("kind", [None, "", 3])
    def test_an_auxiliary_file_without_a_usable_media_type_is_left_to_the_reader(self, kind: Any) -> None:
        item = _item()
        item["assets"]["xyz"]["type"] = kind
        check_is_raster(item, SWISSALTI3D, "xyz")

    def test_an_item_without_assets_is_left_to_the_reader(self) -> None:
        check_is_raster({"id": "x"}, SWISSALTI3D, "xyz")
        check_is_raster({"id": "x", "assets": None}, SWISSALTI3D, "xyz")

    def test_the_media_type_is_compared_without_case_and_blanks(self) -> None:
        item = _item(xyz="  IMAGE/TIFF")
        check_is_raster(item, SWISSALTI3D, "xyz")


@pytest.fixture
def opened(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    calls: list[Any] = []

    def refusing(src_path: Any, **_: Any) -> Any:
        calls.append(src_path)
        raise RuntimeError("the reader was opened")

    monkeypatch.setattr("earthx.api.tiler.open_asset", refusing)
    monkeypatch.setattr("earthx.access.tiles.open_asset", refusing)
    monkeypatch.setattr(
        "earthx.readers.cog.check_url",
        lambda url, policy, **_: check_url(url, policy, resolve=lambda host, port: ("93.184.216.34",)),
    )
    return calls


@pytest.fixture
def client(opened: list[Any]) -> TestClient:
    async def item_source(dataset_id: str, item_id: str) -> dict[str, Any]:
        return _item()

    app = build_app(REGISTRY)
    app.state.earthx_item_source = item_source
    app.state.earthx_cache_pool = None
    return TestClient(app)


class TestTheRoutes:
    TILE = "/collections/swissalti3d/items/2026-2600-1200/tiles/WebMercatorQuad/14/8506/5748.png"

    def test_a_tile_of_the_zip_is_a_400_before_the_reader_opens(self, client: TestClient, opened: list[Any]) -> None:
        response = client.get(self.TILE, params={"asset": "xyz"})
        assert response.status_code == 400, response.text
        assert "no raster" in response.json()["detail"]
        assert opened == []

    def test_the_tilejson_of_the_zip_is_a_400(self, client: TestClient, opened: list[Any]) -> None:
        response = client.get(
            "/collections/swissalti3d/items/2026-2600-1200/WebMercatorQuad/tilejson.json", params={"asset": "xyz"}
        )
        assert response.status_code == 400, response.text
        assert opened == []

    def test_the_cog_is_not_refused(self, client: TestClient, opened: list[Any]) -> None:
        with pytest.raises(RuntimeError, match="the reader was opened"):
            client.get(self.TILE, params={"asset": "dtm"})
        assert len(opened) == 1

    def test_a_download_of_the_zip_is_a_400_before_the_reader_opens(
        self, client: TestClient, opened: list[Any]
    ) -> None:
        response = client.post(
            "/collections/swissalti3d/download", json={"groups": [["2026-2600-1200"]], "assets": ["xyz"], "aoi": AOI}
        )
        assert response.status_code == 400, response.text
        assert "no raster" in response.json()["detail"]
        assert opened == []

    def test_a_download_of_the_zip_next_to_the_cog_is_refused_whole(
        self, client: TestClient, opened: list[Any]
    ) -> None:
        response = client.post(
            "/collections/swissalti3d/download",
            json={"groups": [["2026-2600-1200"]], "assets": ["dtm", "xyz"], "aoi": AOI},
        )
        assert response.status_code == 400, response.text
        assert opened == []
