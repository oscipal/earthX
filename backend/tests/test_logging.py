"""Tests for earthx.logging (M1-01, M3-16): JSON format, request ID, geometry
redaction, and the one access-log line `RequestIdMiddleware` writes per request."""

from __future__ import annotations

import asyncio
import json
import logging
import re

import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from earthx.logging import (
    REQUEST_ID_HEADER,
    JsonFormatter,
    RequestIdMiddleware,
    bind_request_id,
    configure_logging,
    get_request_id,
    reset_request_id,
    summarize_geometry,
)

# A distinctive, high-precision coordinate pair. If this exact value (or its
# repr as a bare float) ever shows up in a log line, the redaction failed.
_EXACT_LON = 13.377476
_EXACT_LAT = 52.516275

_VALID_POLYGON = {
    "type": "Polygon",
    "coordinates": [
        [
            [_EXACT_LON, _EXACT_LAT],
            [_EXACT_LON + 0.5, _EXACT_LAT],
            [_EXACT_LON + 0.5, _EXACT_LAT + 0.5],
            [_EXACT_LON, _EXACT_LAT],
        ]
    ],
}


def _make_record(message: str, **extra: object) -> logging.LogRecord:
    record = logging.LogRecord(
        name="earthx.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=(),
        exc_info=None,
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return record


class TestConfigureLogging:
    """M3-16: turning the root logger to INFO must not turn on a third-party
    library's own "HTTP Request: <url>" line — `httpx`/`httpx2` log the full URL,
    query string included, which is exactly where an AOI travels."""

    def test_httpx_and_httpx2_are_raised_above_info(self) -> None:
        for name in ("httpx", "httpx2"):
            logging.getLogger(name).setLevel(logging.NOTSET)
        try:
            configure_logging()
            for name in ("httpx", "httpx2"):
                assert logging.getLogger(name).getEffectiveLevel() > logging.INFO
        finally:
            for name in ("httpx", "httpx2"):
                logging.getLogger(name).setLevel(logging.NOTSET)


class TestJsonFormatter:
    def test_output_is_one_json_object_with_the_expected_fields(self) -> None:
        token = bind_request_id("req-abc123")
        try:
            line = JsonFormatter().format(_make_record("hello"))
        finally:
            reset_request_id(token)

        payload = json.loads(line)  # raises if not valid JSON
        assert payload["message"] == "hello"
        assert payload["level"] == "INFO"
        assert payload["logger"] == "earthx.test"
        assert payload["request_id"] == "req-abc123"
        assert "timestamp" in payload

    def test_request_id_is_null_outside_a_bound_context(self) -> None:
        assert get_request_id() is None
        payload = json.loads(JsonFormatter().format(_make_record("no request")))
        assert payload["request_id"] is None

    def test_extra_fields_are_included(self) -> None:
        record = _make_record("with extra", dataset_id="sentinel-2-c1-l2a", count=3)
        payload = json.loads(JsonFormatter().format(record))
        assert payload["dataset_id"] == "sentinel-2-c1-l2a"
        assert payload["count"] == 3

    def test_a_geometry_passed_raw_as_extra_never_appears_with_exact_coordinates(self) -> None:
        # Guards against a future caller bypassing summarize_geometry and
        # logging a raw geometry directly as an extra field.
        record = _make_record("aoi received", aoi=summarize_geometry(_VALID_POLYGON))
        line = JsonFormatter().format(record)
        assert str(_EXACT_LON) not in line
        assert str(_EXACT_LAT) not in line


class TestSummarizeGeometry:
    def test_valid_polygon_is_reduced_to_a_coarse_bbox_without_exact_coordinates(self) -> None:
        result = summarize_geometry(_VALID_POLYGON)
        rendered = json.dumps(result)
        assert str(_EXACT_LON) not in rendered
        assert str(_EXACT_LAT) not in rendered
        assert result["geometry_type"] == "Polygon"
        assert len(result["geometry_bbox"]) == 4

    def test_bbox_covers_the_original_geometry(self) -> None:
        result = summarize_geometry(_VALID_POLYGON)
        min_lon, min_lat, max_lon, max_lat = result["geometry_bbox"]
        assert min_lon <= _EXACT_LON <= max_lon
        assert min_lat <= _EXACT_LAT <= max_lat

    @pytest.mark.parametrize(
        "bad_geometry",
        [
            None,
            "not a geometry",
            42,
            {},
            {"type": "Polygon"},  # missing coordinates
            {"type": "Polygon", "coordinates": "banana"},
            {"type": "Polygon", "coordinates": [[[float("nan"), 1.0]]]},
            {"type": "Polygon", "coordinates": [[["x", "y"]]]},
            {"coordinates": [[[_EXACT_LON, _EXACT_LAT, "extra", None]]]},
            [_EXACT_LON, _EXACT_LAT],  # bare coordinate pair, not a GeoJSON object
        ],
    )
    def test_malformed_geometry_never_raises_and_never_leaks_coordinates(self, bad_geometry: object) -> None:
        result = summarize_geometry(bad_geometry)  # must not raise
        rendered = json.dumps(result)
        assert str(_EXACT_LON) not in rendered
        assert str(_EXACT_LAT) not in rendered

    def test_geometry_collection_is_summarized_from_its_members(self) -> None:
        collection = {"type": "GeometryCollection", "geometries": [_VALID_POLYGON]}
        result = summarize_geometry(collection)
        assert len(result["geometry_bbox"]) == 4


def _echo_app() -> Starlette:
    async def handler(request):
        return JSONResponse({"request_id_seen_by_handler": get_request_id()})

    return Starlette(routes=[Route("/echo", handler)])


class TestRequestIdMiddleware:
    def test_generates_a_request_id_and_returns_it_in_the_response_header(self) -> None:
        client = TestClient(RequestIdMiddleware(_echo_app()))
        response = client.get("/echo")
        assert response.status_code == 200
        request_id = response.headers.get(REQUEST_ID_HEADER)
        assert request_id
        assert response.json()["request_id_seen_by_handler"] == request_id

    def test_an_incoming_request_id_is_kept_not_replaced(self) -> None:
        client = TestClient(RequestIdMiddleware(_echo_app()))
        response = client.get("/echo", headers={REQUEST_ID_HEADER: "caller-supplied-id"})
        assert response.headers[REQUEST_ID_HEADER] == "caller-supplied-id"
        assert response.json()["request_id_seen_by_handler"] == "caller-supplied-id"

    @pytest.mark.parametrize(
        "bad_incoming_id",
        [
            "",
            "a" * 65,  # one over the limit
            "has spaces",
            "has/slash",
            "has\nnewline",
            "has\"quote",
            "<script>alert(1)</script>",
            "req;drop table x",
        ],
    )
    def test_an_incoming_request_id_that_does_not_match_the_allowed_shape_is_replaced(
        self, bad_incoming_id: str
    ) -> None:
        client = TestClient(RequestIdMiddleware(_echo_app()))
        response = client.get("/echo", headers={REQUEST_ID_HEADER: bad_incoming_id})
        request_id = response.headers[REQUEST_ID_HEADER]
        assert request_id != bad_incoming_id
        assert re.fullmatch(r"[A-Za-z0-9-]{1,64}", request_id)
        assert response.json()["request_id_seen_by_handler"] == request_id

    def test_a_non_ascii_incoming_request_id_is_replaced(self) -> None:
        # httpx (used by TestClient) refuses to even send a non-ASCII header
        # value, so this drives the ASGI app directly with a raw byte header
        # the way a non-conforming client could send one.
        seen: dict[str, object] = {}

        async def app(scope, receive, send):
            seen["request_id"] = get_request_id()
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b""})

        middleware = RequestIdMiddleware(app)
        scope = {
            "type": "http",
            "path": "/echo",
            "headers": [(REQUEST_ID_HEADER.encode(), "hat-ümlaut".encode("utf-8"))],
        }
        sent: list[dict] = []

        async def receive():
            return {"type": "http.request"}

        async def send(message):
            sent.append(message)

        asyncio.run(middleware(scope, receive, send))

        start = next(m for m in sent if m["type"] == "http.response.start")
        header_value = next(v for k, v in start["headers"] if k == REQUEST_ID_HEADER.encode()).decode()
        assert header_value != "hat-ümlaut"
        assert re.fullmatch(r"[A-Za-z0-9-]{1,64}", header_value)
        assert seen["request_id"] == header_value

    def test_two_requests_without_a_supplied_id_get_different_ids(self) -> None:
        client = TestClient(RequestIdMiddleware(_echo_app()))
        first = client.get("/echo").headers[REQUEST_ID_HEADER]
        second = client.get("/echo").headers[REQUEST_ID_HEADER]
        assert first != second

    def test_request_id_is_unbound_again_after_the_request(self) -> None:
        client = TestClient(RequestIdMiddleware(_echo_app()))
        client.get("/echo")
        assert get_request_id() is None


class TestAccessLogLine:
    """M3-16 (K-01/K-02): one access-log line per request, never a query string."""

    def test_a_request_with_a_query_string_writes_one_line_without_it(
        self, access_log_lines: list[str]
    ) -> None:
        client = TestClient(RequestIdMiddleware(_echo_app()))
        response = client.get(f"/echo?bbox={_EXACT_LON},{_EXACT_LAT},1,2")
        assert response.status_code == 200

        assert len(access_log_lines) == 1
        line = access_log_lines[0]
        assert str(_EXACT_LON) not in line
        assert str(_EXACT_LAT) not in line
        assert "?" not in line

        payload = json.loads(line)
        assert payload["path"] == "/echo"
        assert payload["method"] == "GET"
        assert payload["status"] == 200
        assert isinstance(payload["duration_ms"], int | float)
        assert payload["duration_ms"] >= 0
        assert payload["request_id"] == response.headers[REQUEST_ID_HEADER]

    def test_a_failing_request_still_writes_one_line(self, access_log_lines: list[str]) -> None:
        async def broken(request):
            raise ValueError("boom")

        app = Starlette(routes=[Route("/broken", broken)])
        client = TestClient(RequestIdMiddleware(app), raise_server_exceptions=False)
        response = client.get("/broken")
        assert response.status_code == 500

        assert len(access_log_lines) == 1
        payload = json.loads(access_log_lines[0])
        assert payload["status"] == 500
        assert payload["path"] == "/broken"


class TestEndToEndGeometryLogging:
    """A request carrying a polygon must never put its coordinates in the log."""

    def test_a_malformed_aoi_in_a_request_does_not_leak_coordinates_into_the_log(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        logger = logging.getLogger("earthx.aoi")

        async def handler(request):
            body = await request.json()
            logger.info("aoi received", extra=summarize_geometry(body.get("aoi")))
            return JSONResponse({"ok": True})

        app = RequestIdMiddleware(Starlette(routes=[Route("/aoi", handler, methods=["POST"])]))
        client = TestClient(app)

        malformed_aoi = {"type": "Polygon", "coordinates": [[[_EXACT_LON, "not-a-number"]]]}
        with caplog.at_level(logging.INFO, logger="earthx.aoi"):
            response = client.post("/aoi", json={"aoi": malformed_aoi})

        assert response.status_code == 200
        formatter = JsonFormatter()
        for record in caplog.records:
            line = formatter.format(record)
            assert str(_EXACT_LON) not in line

    def test_a_valid_aoi_in_a_request_does_not_leak_coordinates_into_the_log(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        logger = logging.getLogger("earthx.aoi")

        async def handler(request):
            body = await request.json()
            logger.info("aoi received", extra=summarize_geometry(body.get("aoi")))
            return JSONResponse({"ok": True})

        app = RequestIdMiddleware(Starlette(routes=[Route("/aoi", handler, methods=["POST"])]))
        client = TestClient(app)

        with caplog.at_level(logging.INFO, logger="earthx.aoi"):
            response = client.post("/aoi", json={"aoi": _VALID_POLYGON})

        assert response.status_code == 200
        formatter = JsonFormatter()
        for record in caplog.records:
            line = formatter.format(record)
            assert str(_EXACT_LON) not in line
            assert str(_EXACT_LAT) not in line


class TestProcessEntrypointsWireTheMiddleware:
    """M3-16 (K-02): each of the four HTTP processes calls `configure_logging` and
    wires `RequestIdMiddleware` in, not only `test_logging.py`'s own bare apps."""

    def test_api(self) -> None:
        from earthx.api.main import app

        assert RequestIdMiddleware in [middleware.cls for middleware in app.user_middleware]

    def test_tiler(self) -> None:
        from earthx.api.tiler import app

        assert RequestIdMiddleware in [middleware.cls for middleware in app.user_middleware]

    def test_worker(self) -> None:
        from earthx.jobs.main import app

        assert RequestIdMiddleware in [middleware.cls for middleware in app.user_middleware]

    def test_harvester(self) -> None:
        from earthx.discovery.main import app

        assert RequestIdMiddleware in [middleware.cls for middleware in app.user_middleware]
