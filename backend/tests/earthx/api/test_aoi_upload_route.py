"""``POST /aoi/upload`` (M3-06a): the route's own job — reading the body, mapping
errors to status codes, and never touching disk — not the parsing itself, which
``tests/earthx/access/test_aoi_upload.py`` already covers per format.
"""

from __future__ import annotations

import io
import json
import logging
import tempfile
import zipfile

import pytest
import shapefile
from fastapi import FastAPI
from fastapi.testclient import TestClient

from earthx.access.aoi_upload import MAX_UPLOAD_BYTES
from earthx.api.aoi_upload_route import router

SQUARE = {"type": "Polygon", "coordinates": [[[0.0, 0.0], [0.0, 1.0], [1.0, 1.0], [1.0, 0.0], [0.0, 0.0]]]}


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _shapefile_zip() -> bytes:
    shp_buf, shx_buf, dbf_buf = io.BytesIO(), io.BytesIO(), io.BytesIO()
    writer = shapefile.Writer(shp=shp_buf, shx=shx_buf, dbf=dbf_buf, shapeType=shapefile.POLYGON)
    writer.field("name", "C")
    writer.poly([SQUARE["coordinates"][0]])
    writer.record("a")
    writer.close()
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w") as archive:
        archive.writestr("aoi.shp", shp_buf.getvalue())
        archive.writestr("aoi.shx", shx_buf.getvalue())
        archive.writestr("aoi.dbf", dbf_buf.getvalue())
        archive.writestr("aoi.prj", "EPSG:4326")
    return zip_buf.getvalue()


def test_valid_geojson_returns_the_geometry(client: TestClient) -> None:
    response = client.post("/aoi/upload", params={"filename": "aoi.geojson"}, content=json.dumps(SQUARE))
    assert response.status_code == 200
    assert response.json() == SQUARE


def test_valid_shapefile_returns_the_geometry(client: TestClient) -> None:
    response = client.post("/aoi/upload", params={"filename": "aoi.zip"}, content=_shapefile_zip())
    assert response.status_code == 200
    assert response.json()["type"] == "Polygon"


def test_missing_filename_extension_is_400(client: TestClient) -> None:
    response = client.post("/aoi/upload", params={"filename": "aoi.txt"}, content=b"whatever")
    assert response.status_code == 400


def test_invalid_geometry_is_400(client: TestClient) -> None:
    line = {"type": "LineString", "coordinates": [[0.0, 0.0], [1.0, 1.0]]}
    response = client.post("/aoi/upload", params={"filename": "aoi.geojson"}, content=json.dumps(line))
    assert response.status_code == 400
    assert "LineString" in response.json()["detail"]


def test_missing_filename_query_param_is_422(client: TestClient) -> None:
    response = client.post("/aoi/upload", content=json.dumps(SQUARE))
    assert response.status_code == 422


def test_upload_over_the_cap_is_413(client: TestClient) -> None:
    payload = b"0" * (MAX_UPLOAD_BYTES + 1)
    response = client.post("/aoi/upload", params={"filename": "aoi.geojson"}, content=payload)
    assert response.status_code == 413


def test_upload_at_exactly_the_cap_is_not_413(client: TestClient) -> None:
    # Not valid GeoJSON at this size, so it is a 400, not a 413 — the point is that
    # the size gate alone does not reject a body that is exactly at the cap.
    payload = b" " * (MAX_UPLOAD_BYTES - 2) + b"{}"
    response = client.post("/aoi/upload", params={"filename": "aoi.geojson"}, content=payload)
    assert response.status_code == 400


def test_never_spools_to_a_real_temp_file(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """The whole reason for reading the raw body ourselves (plan §6) is that a
    file's bytes never reach a real temp file. Patches `SpooledTemporaryFile.rollover`
    (Starlette's own multipart parser would call this once a part exceeds 1 MiB) and
    `tempfile.mkstemp` (the low-level primitive behind `NamedTemporaryFile`) to raise;
    a request at the cap must still succeed with neither ever firing."""

    def _boom(*args: object, **kwargs: object) -> None:
        raise AssertionError("a real temp file must never be created for this route")

    monkeypatch.setattr(tempfile.SpooledTemporaryFile, "rollover", _boom)
    monkeypatch.setattr(tempfile, "mkstemp", _boom)

    payload = json.dumps(SQUARE).encode()
    padded = payload + b" " * (MAX_UPLOAD_BYTES - len(payload))
    response = client.post("/aoi/upload", params={"filename": "aoi.geojson"}, content=padded)
    assert response.status_code in (200, 400)  # padding may or may not still parse; what matters is no temp file


def test_no_coordinate_or_content_in_the_log(client: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="earthx.api.aoi_upload"):
        client.post(
            "/aoi/upload",
            params={"filename": "aoi.geojson"},
            content=json.dumps({"type": "Point", "coordinates": [12.3456, 78.9012]}),
        )
    full_text = "\n".join(str(record.__dict__) for record in caplog.records)
    assert "12.3456" not in full_text
    assert "78.9012" not in full_text
