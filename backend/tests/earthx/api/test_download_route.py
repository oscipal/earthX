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

    def feature(
        self, geometry: dict[str, Any], *, width: int | None = None, height: int | None = None
    ) -> ImageData:
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
    monkeypatch.setattr("earthx.api.tiler.open_asset", lambda src_path, **_: FakeReader(src_path))
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

    def test_more_than_the_item_cap_is_413(self, client: TestClient) -> None:
        """F4 (M3-18): a mosaic capped at 25 scenes, independent of the output size."""
        response = _download(client, items=[ITEM_ID] * 26, assets=["visual"])
        assert response.status_code == 413
        assert "26 scenes" in response.json()["detail"]

    def test_an_asset_without_size_metadata_falls_back_to_the_worst_case_and_is_413(
        self, client: TestClient
    ) -> None:
        """`thumbnail` has neither `gsd` nor `raster:bands` on this item (F1/F2): the
        estimate falls back to the conservative worst case M2-06 used for the whole
        request — big enough on its own to trip the 500 MB cap."""
        response = _download(client, assets=["thumbnail"])
        assert response.status_code == 413
        assert "MB" in response.json()["detail"]

    def test_over_the_cap_the_message_never_shrinks_the_request_itself(
        self, client: TestClient
    ) -> None:
        """Otto, 23.09.2026 (M3-18 §10): over the cap is always a refusal, never a
        silent downscale — no zip is ever returned, whatever the message suggests."""
        response = _download(client, assets=["thumbnail"])
        assert response.status_code == 413
        assert response.headers["content-type"] != "application/zip"

    def test_over_the_cap_names_the_smallest_fitting_resolution_factor(
        self, client: TestClient
    ) -> None:
        """F10c (M3-18 §10): the rejection suggests a factor from
        `RESOLUTION_FACTORS` that would bring this same request under the cap,
        not just "smaller area or fewer layers"."""
        response = _download(client, assets=["thumbnail"])
        assert response.status_code == 413
        assert "x would fit" in response.json()["detail"]

    def test_an_unknown_resolution_factor_is_a_validation_error(self, client: TestClient) -> None:
        response = _download(client, resolution=3)
        assert response.status_code == 422

    def test_an_explicit_resolution_factor_is_honored_in_the_filename_and_notice(
        self, client: TestClient
    ) -> None:
        """F10c (M3-18 §10): an explicitly coarser resolution travels into the
        archive — the filename and the notice both name it, never silently."""
        response = _download(client, resolution=2)
        assert response.status_code == 200
        with zipfile.ZipFile(BytesIO(response.content)) as archive:
            names = set(archive.namelist())
            assert names == {"visual_2x.tif", "ATTRIBUTION.txt"}
            notice = archive.read("ATTRIBUTION.txt").decode("utf-8")
            assert "2x coarser than native" in notice

    def test_native_resolution_names_no_factor_in_filename_or_notice(self, client: TestClient) -> None:
        response = _download(client)
        assert response.status_code == 200
        with zipfile.ZipFile(BytesIO(response.content)) as archive:
            assert "visual.tif" in archive.namelist()
            notice = archive.read("ATTRIBUTION.txt").decode("utf-8")
            assert "Resolution: native" in notice

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
        monkeypatch.setattr("earthx.api.tiler.open_asset", lambda src_path, **_: FakeReader(src_path))
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

    def test_a_language_field_in_the_body_is_ignored_the_notice_stays_english(
        self, client: TestClient
    ) -> None:
        """Otto, 22.09.2026: the route offers no language choice at all."""
        response = _download(client, language="de")
        assert response.status_code == 200
        with zipfile.ZipFile(BytesIO(response.content)) as archive:
            notice = archive.read("ATTRIBUTION.txt").decode("utf-8")
        notice_en = SENTINEL_2_L2A.license.terms.notice["en"].format(
            terms_url=SENTINEL_2_L2A.license.terms.url
        )
        assert notice_en in notice

    def test_the_same_asset_asked_for_twice_is_one_file(self, client: TestClient) -> None:
        """`assets` is a caller's list and may repeat a key. Without deduplication the
        archive got two entries of the same name — legal in a ZIP, and untangleable by
        nobody (M2-10 review)."""
        response = _download(client, assets=["visual", "visual"])

        assert response.status_code == 200
        with zipfile.ZipFile(BytesIO(response.content)) as archive:
            assert archive.namelist().count("visual.tif") == 1

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

    def test_the_access_log_line_carries_no_aoi_and_a_request_id(
        self, client: TestClient, access_log_lines: list[str]
    ) -> None:
        """M3-16: `build_app` wires `RequestIdMiddleware` in — this is the one access-log
        line the process writes for this request, method/path/status/duration only.
        The AOI travels in the POST body (M2-06), which this line never reads either way.
        """
        response = _download(client)
        assert response.status_code == 200
        assert access_log_lines
        for line in access_log_lines:
            payload = json.loads(line)
            # Checked on the deserialised path, not the raw line: `duration_ms` is an
            # arbitrary float and can coincidentally contain a short digit sequence
            # like "7.1" — the field that could ever carry an AOI is `path`, and the
            # exact key set proves no further field (an `aoi`/`bbox` extra) ever joined it.
            for coordinate in ("7.1", "7.2", "46.1", "46.2"):
                assert coordinate not in payload["path"]
            assert set(payload) == {
                "timestamp",
                "level",
                "logger",
                "message",
                "request_id",
                "method",
                "path",
                "status",
                "duration_ms",
            }
            assert payload["request_id"]
            assert payload["method"] == "POST"
            assert payload["status"] == 200
            assert isinstance(payload["duration_ms"], int | float)

    def test_a_second_large_download_is_refused_with_503_and_retry_after(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """F10a (M3-18 §10): the process allows only one download near/above
        `LARGE_DOWNLOAD_THRESHOLD_BYTES` at a time — a second one gets a 503 with
        `Retry-After`, never queued and never silently downscaled."""

        class _AlreadyRunning:
            def locked(self) -> bool:
                return True

        monkeypatch.setattr("earthx.api.tiler.LARGE_DOWNLOAD_THRESHOLD_BYTES", 0)
        monkeypatch.setattr("earthx.api.tiler._LARGE_DOWNLOAD_LOCK", _AlreadyRunning())

        response = _download(client)
        assert response.status_code == 503
        assert response.headers["retry-after"] == "30"
        assert "another large download is running" in response.json()["detail"]

    def test_a_small_download_is_never_refused_by_the_concurrency_gate(
        self, client: TestClient
    ) -> None:
        """The concurrency gate only applies once the process-wide lock is
        actually held — an ordinary small request always goes through."""
        response = _download(client)
        assert response.status_code == 200
