"""Tests for earthx.logging (M1-01, M3-16): JSON format, request ID, geometry
redaction, and the one access-log line `RequestIdMiddleware` writes per request."""

from __future__ import annotations

import asyncio
import contextlib
import io
import json
import logging
import re
import sys
from datetime import datetime, timezone

import httpx
import pytest
import uvicorn
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
from tests.conftest import format_without_timestamp, log_line_without_timestamp, own_log_fields, own_log_text

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

    @pytest.mark.parametrize("level", [logging.INFO, logging.DEBUG])
    def test_the_client_libraries_are_raised_to_warning(self, level: int) -> None:
        """`botocore`/`urllib3` since M4-06: key id and signature at DEBUG (adr/0015 §9.2)."""
        names = ("httpx", "httpx2", "botocore", "urllib3")
        root = logging.getLogger()
        previous = root.level
        for name in names:
            logging.getLogger(name).setLevel(logging.NOTSET)
        try:
            configure_logging(level)
            for name in names:
                assert logging.getLogger(name).getEffectiveLevel() == logging.WARNING
        finally:
            root.setLevel(previous)
            for name in names:
                logging.getLogger(name).setLevel(logging.NOTSET)


class TestUvicornAccessLogIsDisabledInCode:
    """M3-16 review: the guarantee must not depend on `--no-access-log` on the
    command line — a process started any other way (a bare `uvicorn earthx.jobs
    .main:app`, following the README without the flag) has to be exactly as
    safe, because the code closes it, not the invocation.
    """

    def test_a_live_server_started_without_the_flag_still_logs_no_query_string(self) -> None:
        from earthx.jobs.main import app

        async def run_request() -> tuple[int, bytes]:
            # Reproduces uvicorn's own startup order: `Config.__init__` runs uvicorn's
            # own `configure_logging()` — giving `uvicorn.access` its own handler,
            # exactly as it would be left *without* `--no-access-log` (`access_log=True`
            # is the default) — before `Config.load()` imports the ASGI app string and
            # this module's own `configure_logging()` gets its turn. `earthx.jobs.main`
            # is typically already imported by the time this test runs, so that second
            # call is reproduced explicitly, in the same order.
            # `lifespan="off"`: since M4-06 the worker's start checks the object store
            # (tests/earthx/jobs/test_startup.py); this test is about the access log.
            config = uvicorn.Config(
                app, host="127.0.0.1", port=0, access_log=True, log_level="info", lifespan="off"
            )
            configure_logging()
            server = uvicorn.Server(config)
            task = asyncio.create_task(server.serve())
            try:
                while not server.started:
                    await asyncio.sleep(0.01)
                port = server.servers[0].sockets[0].getsockname()[1]
                async with httpx.AsyncClient() as client:
                    response = await client.get(
                        f"http://127.0.0.1:{port}/health",
                        params={"bbox": f"{_EXACT_LON},{_EXACT_LAT},1,2"},
                    )
            finally:
                server.should_exit = True
                await task
            return response.status_code, response.content

        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            status_code, _ = asyncio.run(run_request())
        assert status_code == 200

        output = buffer.getvalue()
        assert "?" not in output
        assert str(_EXACT_LON) not in output
        assert str(_EXACT_LAT) not in output

        lines = [line for line in output.splitlines() if line.strip()]
        assert len(lines) == 1  # not two: uvicorn's own access-log line never joins it
        payload = json.loads(lines[0])
        assert payload["logger"] == "earthx.request"
        assert payload["path"] == "/health"
        assert payload["status"] == 200


class TestFormatWithoutTimestamp:
    def _record_at_a_time_containing(self, digits: str, message: str, **extra: object) -> logging.LogRecord:
        record = _make_record(message, **extra)
        record.created = datetime(2026, 10, 7, 13, 26, 39, 3729, tzinfo=timezone.utc).timestamp()
        assert digits in JsonFormatter().format(record)  # the raw line matches by chance
        return record

    def test_digits_that_only_the_timestamp_holds_are_not_in_the_rendered_line(self) -> None:
        record = self._record_at_a_time_containing("9.0", "run ended", run="r1")
        assert "9.0" not in format_without_timestamp(record)

    def test_a_coordinate_in_the_message_is_still_in_the_rendered_line(self) -> None:
        record = self._record_at_a_time_containing("9.0", "read window at 47.0,9.0")
        assert "9.0" in format_without_timestamp(record)

    def test_a_coordinate_in_an_extra_field_is_still_in_the_rendered_line(self) -> None:
        record = self._record_at_a_time_containing("9.0", "run ended", bbox="9.0,47.0")
        assert "47.0" in format_without_timestamp(record)

    def test_a_line_without_a_timestamp_is_refused_rather_than_passed_on(self) -> None:
        with pytest.raises(KeyError):
            log_line_without_timestamp(json.dumps({"message": "no time"}))


class TestOwnLogText:
    def _record(self, message: str, **extra: object) -> logging.LogRecord:
        record = _make_record(message, **extra)
        record.relativeCreated = 25239.017
        record.msecs = 9.01
        assert "9.01" in str(record.__dict__)  # the standard attributes match by chance
        return record

    def test_digits_that_only_a_standard_attribute_holds_are_not_in_the_text(self) -> None:
        assert "9.01" not in own_log_text(self._record("run ended", run="r1"))

    def test_a_coordinate_in_the_message_is_still_in_the_text(self) -> None:
        assert "9.01" in own_log_text(self._record("read window at 47.01,9.01"))

    def test_a_coordinate_in_an_own_field_is_still_in_the_text(self) -> None:
        assert "9.01" in own_log_text(self._record("run ended", bbox="9.01,47.01"))

    def test_only_the_callers_fields_are_listed(self) -> None:
        assert own_log_fields(self._record("run ended", run="r1", count=2)) == {"run": "r1", "count": 2}

    def test_a_value_that_is_not_json_is_written_out_not_dropped(self) -> None:
        assert "9.01" in own_log_text(self._record("run ended", where=(9.01, 47.01), when=datetime(2026, 1, 1)))

    def test_the_measured_duration_of_the_access_log_is_not_in_the_text(self) -> None:
        """NM4-23: "9.5" matched inside `duration_ms` 59.5; the other fields of the line stay."""
        text = own_log_text(self._record("request handled", path="/x/9.5", duration_ms=59.5))
        assert "59.5" not in text and "/x/9.5" in text

    def test_a_duration_that_is_not_a_number_is_not_left_out_quietly(self) -> None:
        with pytest.raises(AssertionError):
            own_log_text(self._record("request handled", duration_ms="9.01,47.01"))


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
        line = format_without_timestamp(record)
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
        for record in caplog.records:
            line = format_without_timestamp(record)
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
        for record in caplog.records:
            line = format_without_timestamp(record)
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


class TestAJobIdentifierIsNotLogged:
    """M4-08b F6: `/processing/jobs/{jobID}` is the way to a job's result; the log names the route, not the job."""

    @pytest.mark.parametrize(
        ("path", "logged"),
        [
            ("/processing/jobs/AAAAAAAAAAAAAAAAAAAAAA", "/processing/jobs/{jobID}"),
            ("/processing/jobs/AAAAAAAAAAAAAAAAAAAAAA/results", "/processing/jobs/{jobID}/results"),
            ("/processing/jobs/AAAAAAAAAAAAAAAAAAAAAA/results/result.tif", "/processing/jobs/{jobID}/results/result.tif"),
            ("/processing/jobs/AAAAAAAAAAAAAAAAAAAAAA/events", "/processing/jobs/{jobID}/events"),
            ("/processing/jobs/not-an-identifier-but-secret/results", "/processing/jobs/{jobID}/results"),
            ("/earthx/processing/jobs/AAAAAAAAAAAAAAAAAAAAAA/results", "/earthx/processing/jobs/{jobID}/results"),
            ("/processing/jobs//AAAAAAAAAAAAAAAAAAAAAA", "/processing/jobs/{jobID}"),
            ("/processing/jobs///AAAAAAAAAAAAAAAAAAAAAA/events", "/processing/jobs/{jobID}/events"),
            ("/processing/jobs/", "/processing/jobs/"),
            ("/processing/jobs", "/processing/jobs"),
            ("/processing/processes/recipe", "/processing/processes/recipe"),
            ("/stac/collections/x/items/AAAAAAAAAAAAAAAAAAAAAA", "/stac/collections/x/items/AAAAAAAAAAAAAAAAAAAAAA"),
            ("/health", "/health"),
            ("", ""),
            (None, None),
        ],
    )  # fmt: skip
    def test_the_path_as_the_access_log_writes_it(self, path: str | None, logged: str | None) -> None:
        from earthx.logging import loggable_path

        assert loggable_path(path) == logged

    def test_the_middleware_writes_it_so(self, access_log_lines: list[str]) -> None:
        async def endpoint(request):
            return JSONResponse({})

        app = Starlette(routes=[Route("/processing/jobs/{job_id}/results", endpoint)])
        client = TestClient(RequestIdMiddleware(app))
        assert client.get("/processing/jobs/AAAAAAAAAAAAAAAAAAAAAA/results").status_code == 200
        (line,) = access_log_lines
        assert json.loads(line)["path"] == "/processing/jobs/{jobID}/results"
        assert "AAAAAAAAAAAAAAAAAAAAAA" not in line


class TestAPermalinkIdentifierIsNotLogged:
    """M4-19e: the identifier of a permalink is the way to an order with its area."""

    @pytest.mark.parametrize(
        ("path", "logged"),
        [
            ("/processing/permalinks/AAAAAAAAAAAAAAAAAAAAAA", "/processing/permalinks/{permalinkID}"),
            ("/processing/permalinks//AAAAAAAAAAAAAAAAAAAAAA", "/processing/permalinks/{permalinkID}"),
            ("/processing/permalinks/not-an-identifier-but-secret", "/processing/permalinks/{permalinkID}"),
            ("/earthx/processing/permalinks/AAAAAAAAAAAAAAAAAAAAAA", "/earthx/processing/permalinks/{permalinkID}"),
            ("/processing/permalinks", "/processing/permalinks"),
            ("/processing/permalinks/", "/processing/permalinks/"),
        ],
    )  # fmt: skip
    def test_the_path_as_the_access_log_writes_it(self, path: str, logged: str) -> None:
        from earthx.logging import loggable_path

        assert loggable_path(path) == logged


class TestABundleIdentifierIsNotLogged:
    """UI-01e: the identifier of a bundle is the way to the results of several jobs."""

    @pytest.mark.parametrize(
        ("path", "logged"),
        [
            ("/processing/bundles/AAAAAAAAAAAAAAAAAAAAAA", "/processing/bundles/{bundleID}"),
            ("/processing/bundles//AAAAAAAAAAAAAAAAAAAAAA", "/processing/bundles/{bundleID}"),
            ("/processing/bundles/not-an-identifier-but-secret", "/processing/bundles/{bundleID}"),
            ("/earthx/processing/bundles/AAAAAAAAAAAAAAAAAAAAAA", "/earthx/processing/bundles/{bundleID}"),
            ("/processing/bundles", "/processing/bundles"),
            ("/processing/bundles/", "/processing/bundles/"),
        ],
    )  # fmt: skip
    def test_the_path_as_the_access_log_writes_it(self, path: str, logged: str) -> None:
        from earthx.logging import loggable_path

        assert loggable_path(path) == logged


class TestAResultIdentifierIsNotLogged:
    """M4-13c-5: `/results/{result_id}` of the tiler is the way to a result's tiles, as the job's identifier is to its files."""

    ID = "ZyXwVuTsRqPoNmLkJiHg_-"

    @pytest.mark.parametrize(
        ("path", "logged"),
        [
            (f"/results/{ID}/tiles/WebMercatorQuad/1/2/3", "/results/{resultID}/tiles/WebMercatorQuad/1/2/3"),
            (f"/results/{ID}/WebMercatorQuad/tilejson.json", "/results/{resultID}/WebMercatorQuad/tilejson.json"),
            (f"//results//{ID}/WebMercatorQuad/tilejson.json", "//results/{resultID}/WebMercatorQuad/tilejson.json"),
            ("/results/not-an-identifier-but-secret/tiles/x", "/results/{resultID}/tiles/x"),
            (f"/tiler/results/{ID}/tiles/x", "/tiler/results/{resultID}/tiles/x"),
            (f"/processing/jobs/{ID}/results/result.tif", "/processing/jobs/{jobID}/results/result.tif"),
            (f"/processing/jobs/{ID}/results", "/processing/jobs/{jobID}/results"),
            ("/results/", "/results/"),
            ("/results", "/results"),
            ("/collections/a/items/b/tiles/WebMercatorQuad/1/2/3", "/collections/a/items/b/tiles/WebMercatorQuad/1/2/3"),
        ],
    )  # fmt: skip
    def test_the_path_as_the_access_log_writes_it(self, path: str, logged: str) -> None:
        from earthx.logging import loggable_path

        assert loggable_path(path) == logged

    def test_the_middleware_writes_it_so(self, access_log_lines: list[str]) -> None:
        async def endpoint(request):
            return JSONResponse({})

        app = Starlette(routes=[Route("/results/{result_id}/tiles", endpoint)])
        assert TestClient(RequestIdMiddleware(app)).get(f"/results/{self.ID}/tiles").status_code == 200
        (line,) = access_log_lines
        assert json.loads(line)["path"] == "/results/{resultID}/tiles"
        assert self.ID not in line


class TestAnAddressIsNotLogged:
    """M4-13c-5, NM4-57: GDAL names the address of a file it could not read, and for a source with signed URLs it holds the token."""

    ID = "ZyXwVuTsRqPoNmLkJiHg_-"
    URL = (
        f"http://objectstore:3900/earthx/results/{ID}/result.tif?X-Amz-Algorithm=AWS4-HMAC-SHA256"
        "&X-Amz-Credential=GKabc123%2F20261020%2Fgarage%2Fs3%2Faws4_request&X-Amz-Date=20261020T120000Z"
        "&X-Amz-Expires=900&X-Amz-SignedHeaders=host&X-Amz-Signature=deadbeefdeadbeef"
    )

    def test_the_message_loses_the_address_with_the_signature_and_the_result_id(self) -> None:
        payload = json.loads(
            JsonFormatter().format(_make_record(f"CPLE_AppDefined in HTTP response code on {self.URL}: 403"))
        )
        assert payload["message"] == "CPLE_AppDefined in HTTP response code on <address>: 403"

    def test_a_traceback_loses_it_too(self) -> None:
        try:
            raise OSError(f"'/vsicurl/{self.URL}' not recognized")
        except OSError:
            record = logging.LogRecord("x", logging.WARNING, __file__, 1, "read failed", None, sys.exc_info())
        payload = json.loads(JsonFormatter().format(record))
        assert "deadbeefdeadbeef" not in payload["exc_info"] and self.ID not in payload["exc_info"]
        assert "OSError: '<address>' not recognized" in payload["exc_info"]

    def test_a_field_added_by_the_caller_loses_it_too(self) -> None:
        payload = json.loads(JsonFormatter().format(_make_record("read failed", href=self.URL, attempts=3)))
        assert payload["href"] == "<address>" and payload["attempts"] == 3

    @pytest.mark.parametrize(
        ("text", "hidden"),
        [
            (
                "HTTP response code on https://host.example/a/b.tif?sig=abc&se=2026-10-30: 0",
                "HTTP response code on <address>: 0",
            ),
            ("'/vsicurl/https://host.example/a/b.tif' not recognized", "'<address>' not recognized"),
            ("`/vsicurl/http://127.0.0.1:9/a/b.tif?sig=abc' not recognized", "`<address>' not recognized"),
            ("could not open /vsis3/bucket/key/scene.tif.", "could not open <address>."),
            ("could not open /vsigs/bucket/key/scene.tif", "could not open <address>"),
            ("in /vsizip//vsicurl/https://host.example/a.zip/b.tif (twice)", "in <address> (twice)"),
            ("store s3://bucket/prefix/key and gs://bucket/key", "store <address> and <address>"),
            ("see (https://host.example/x?token=abc), then", "see (<address>), then"),
            ("retrying ftp://host.example:21/x", "retrying <address>"),
            ("the query X-Amz-Signature=deadbeef stands alone", "the query X-Amz-Signature=<hidden> stands alone"),
            ("sas sig=abc%2Fdef= and access_token=xyz", "sas sig=<hidden> and access_token=<hidden>"),
        ],
    )
    def test_every_form_of_address_goes(self, text: str, hidden: str) -> None:
        from earthx.logging import hide_addresses

        assert hide_addresses(text) == hidden

    @pytest.mark.parametrize(
        "text",
        [
            "request handled",
            "/results/ short",
            "ordinary query ?x=y&X-Other=1",
            "/home/user/earthx/backend/earthx/api/tiler.py line 12",
            "opened /vsimem/in-memory-name.tif",
            "ratio=0.5 size=3/4",
            "",
        ],
    )
    def test_any_other_text_is_left_alone(self, text: str) -> None:
        from earthx.logging import hide_addresses

        assert hide_addresses(text) == text

    def test_a_result_id_stands_in_no_path_either(self) -> None:
        from earthx.logging import hide_addresses

        assert hide_addresses(f"file /results/{self.ID}/result.tif gone") == "file /results/{resultID}/result.tif gone"

    def test_the_traceback_on_uvicorns_own_handler_is_cleaned_before_its_formatter_reads_it(self) -> None:
        """The handler uvicorn writes its own lines with is not ours: its formatter sees what the filter left."""
        from earthx.logging import _hide_addresses_in_uvicorn

        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
        logger = logging.getLogger("uvicorn")
        before, level = list(logger.handlers), logger.level
        logger.handlers, logger.level = [handler], logging.INFO
        try:
            _hide_addresses_in_uvicorn()
            _hide_addresses_in_uvicorn()  # once is enough
            assert len(handler.filters) == 1
            logging.getLogger("uvicorn.error").info("Uvicorn running on %s://%s:%d", "http", "0.0.0.0", 8000)
            try:
                raise OSError(f"'/vsicurl/{self.URL}' not recognized")
            except OSError:
                logging.getLogger("uvicorn.error").error("Exception in ASGI application", exc_info=True)
        finally:
            logger.handlers, logger.level = before, level
        output = stream.getvalue()
        assert "INFO Uvicorn running on http://0.0.0.0:8000" in output
        assert "deadbeefdeadbeef" not in output and "objectstore" not in output
        assert "OSError: '<address>' not recognized" in output
