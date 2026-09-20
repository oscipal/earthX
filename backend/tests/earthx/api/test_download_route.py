"""``POST /collections/{dataset}/download`` (M2-06), against a fake item source
and a fake reader — no network, no GDAL read, no database (adr/0002 §2).

The acceptance criteria of M2-06, each as its own test: too large an AOI, an
AOI outside the item, a malformed geometry, an unknown item, no disk write
(covered at the module level in ``test_download.py``, exercised here through
the route once for the wiring), the notice file's content, and that no AOI
coordinate reaches the one log line the route writes.
"""

from __future__ import annotations

import json
import logging
import zipfile
from contextlib import asynccontextmanager
from dataclasses import replace
from io import BytesIO
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from fastapi.testclient import TestClient
from rio_tiler.models import ImageData

from earthx.api.tiler import build_app
from earthx.catalog.datasets import REGISTRY, SENTINEL_2_L2A
from earthx.catalog.registry import DatasetRegistry, LicenseInfo, LicenseTier
from earthx.gateway import UpstreamError, check_url

FIXTURE = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "earth_search" / "item_asset_hosts.json"
DATASET = SENTINEL_2_L2A.dataset_id
ITEM_ID = "SYNTH_T00AAA_20260724T100000_L2A"

GOOD_AOI = {"type": "Polygon", "coordinates": [[[7.1, 46.1], [7.2, 46.1], [7.2, 46.2], [7.1, 46.2], [7.1, 46.1]]]}
OUTSIDE_AOI = {"type": "Polygon", "coordinates": [[[50, 50], [51, 50], [51, 51], [50, 51], [50, 50]]]}
BAD_GEOMETRY = {"type": "Point", "coordinates": [1, 2]}


@pytest.fixture(scope="module")
def item() -> dict[str, Any]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class FakeReader:
    """No network: ``feature()`` hands back a tiny, fixed image."""

    def __init__(self, src_path: object) -> None:
        self.src_path = src_path

    def __enter__(self) -> "FakeReader":
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    def feature(self, geometry: dict[str, Any], max_size: int | None = None) -> ImageData:
        data = (np.random.default_rng(0).random((3, 8, 8)) * 255).astype("uint8")
        return ImageData(data, crs="EPSG:4326", bounds=(0, 0, 1, 1))


@pytest.fixture
def client(item: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> TestClient:
    async def item_source(dataset_id: str, item_id: str) -> dict[str, Any]:
        if item_id != ITEM_ID:
            raise UpstreamError(404, "not found")
        return item

    @asynccontextmanager
    async def lifespan(app):
        app.state.earthx_item_source = item_source
        yield

    # The name is resolved from memory, the same way test_tiler.py does it: the
    # network guard in tests/conftest.py rightly refuses a real DNS lookup, and
    # everything this route checks (catalogue, allowlist, path building) already
    # runs for real before that point.
    monkeypatch.setattr(
        "earthx.readers.cog.check_url",
        # `**_` swallows the resolver `asset_path` hands on (M2-14): these tests
        # answer from memory whatever the caller would have resolved with.
        lambda url, policy, **_: check_url(url, policy, resolve=lambda host, port: ("93.184.216.34",)),
    )
    monkeypatch.setattr("earthx.api.tiler.CogReader", FakeReader)
    app = build_app(REGISTRY, lifespan=lifespan)
    with TestClient(app) as test_client:
        yield test_client


def _download(client: TestClient, dataset: str = DATASET, **body: Any) -> Any:
    payload = {"items": [ITEM_ID], "assets": ["visual"], "aoi": GOOD_AOI, **body}
    return client.post(f"/collections/{dataset}/download", json=payload)


class TestAcceptanceCriteria:
    def test_an_unknown_dataset_is_404(self, client: TestClient) -> None:
        response = _download(client, dataset="no-such-dataset")
        assert response.status_code == 404

    def test_an_unknown_item_is_a_defined_error(self, client: TestClient) -> None:
        response = _download(client, items=["NOPE"])
        assert response.status_code == 404
        assert "NOPE" in response.json()["detail"]

    def test_a_malformed_geometry_is_400(self, client: TestClient) -> None:
        response = _download(client, aoi=BAD_GEOMETRY)
        assert response.status_code == 400

    def test_an_aoi_outside_every_item_is_a_defined_error(self, client: TestClient) -> None:
        response = _download(client, aoi=OUTSIDE_AOI)
        assert response.status_code == 400
        assert "does not touch" in response.json()["detail"]

    def test_an_aoi_too_large_for_the_cap_is_413(self, client: TestClient) -> None:
        response = _download(client, items=[ITEM_ID] * 22, assets=["visual"] * 13)
        assert response.status_code == 413

    def test_a_dataset_without_processing_tier_licence_is_refused(
        self, item: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        display_tier = replace(
            SENTINEL_2_L2A,
            license=LicenseInfo(
                spdx_id="CC-BY-4.0",
                name="CC BY 4.0",
                url="https://creativecommons.org/licenses/by/4.0/",
                commercial_use=True,
                distribution=True,
                derivatives=True,
                share_alike=False,
                attribution_required=False,
                tier=LicenseTier.DISPLAY,
                attribution_modified=None,
                attribution_unmodified=None,
                terms=None,
            ),
        )
        registry = DatasetRegistry((display_tier,))

        async def item_source(dataset_id: str, item_id: str) -> dict[str, Any]:
            return item

        @asynccontextmanager
        async def lifespan(app):
            app.state.earthx_item_source = item_source
            yield

        monkeypatch.setattr(
            "earthx.readers.cog.check_url",
            # `**_` swallows the resolver `asset_path` hands on (M2-14): these tests
        # answer from memory whatever the caller would have resolved with.
        lambda url, policy, **_: check_url(url, policy, resolve=lambda host, port: ("93.184.216.34",)),
        )
        monkeypatch.setattr("earthx.api.tiler.CogReader", FakeReader)
        app = build_app(registry, lifespan=lifespan)
        with TestClient(app) as test_client:
            response = _download(test_client)
        assert response.status_code == 403

    def test_a_successful_crop_is_a_zip_with_the_notice_file(self, client: TestClient) -> None:
        response = _download(client)
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/zip"
        assert "attachment" in response.headers["content-disposition"]
        with zipfile.ZipFile(BytesIO(response.content)) as archive:
            names = set(archive.namelist())
            assert names == {"visual.tif", "ATTRIBUTION.txt"}
            notice = archive.read("ATTRIBUTION.txt").decode("utf-8")
            assert "Contains modified Copernicus Sentinel data" in notice
            assert SENTINEL_2_L2A.license.terms.url in notice

    def test_the_language_of_the_notice_follows_the_request(self, client: TestClient) -> None:
        response = _download(client, language="en")
        with zipfile.ZipFile(BytesIO(response.content)) as archive:
            notice = archive.read("ATTRIBUTION.txt").decode("utf-8")
        notice_en = SENTINEL_2_L2A.license.terms.notice["en"].format(
            terms_url=SENTINEL_2_L2A.license.terms.url
        )
        assert notice_en in notice

    def test_an_empty_item_or_asset_list_is_a_validation_error(self, client: TestClient) -> None:
        assert _download(client, items=[]).status_code == 422
        assert _download(client, assets=[]).status_code == 422

    def test_no_aoi_coordinate_reaches_the_log(
        self, client: TestClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.INFO, logger="earthx.api.tiler"):
            response = _download(client)
        assert response.status_code == 200
        logged = "\n".join(record.getMessage() for record in caplog.records)
        for coordinate in ("7.1", "7.2", "46.1", "46.2"):
            assert coordinate not in logged
